"""
agents/roadmap_agent.py
────────────────────────
LangGraph agent that generates a personalised 12-week learning roadmap.

Graph nodes (executed in order):
    fetch_profile   → pull student document from MongoDB
    recall_memory   → cognee.recall() any prior context for this student
    generate_roadmap → call Groq (JSON mode) to build the weekly plan
    save_to_mongo   → upsert into the roadmaps collection
    save_to_cognee  → store roadmap summary in student's memory graph

Entrypoint:
    result = await run_roadmap_agent(student_id)
    # returns the roadmap dict on success, raises on error
"""

import json
import logging
from datetime import datetime, timezone
from typing import Optional

from bson import ObjectId
from langgraph.graph import END, StateGraph
from typing_extensions import TypedDict

from db.mongo import get_db
from services.cognee_service import remember_roadmap
from services.llm_service import chat_json

logger = logging.getLogger(__name__)

# ── Goal → topic weight mapping ───────────────────────────────────────────────
GOAL_WEIGHTS: dict[str, dict] = {
    "FAANG": {
        "description": "targeting FAANG / top-tier tech companies",
        "distribution": "60% DSA & Algorithms, 20% System Design, 20% Projects & CS Fundamentals",
        "focus_areas": ["DSA", "System Design", "Projects", "CS Fundamentals"],
    },
    "Startup": {
        "description": "targeting early-stage startup roles",
        "distribution": "40% Web/App Development, 30% DSA, 30% Projects & Product Thinking",
        "focus_areas": ["Web/App Development", "DSA", "Projects", "Product Thinking"],
    },
    "MS Abroad": {
        "description": "targeting Masters programs abroad",
        "distribution": "40% DSA, 30% Research/ML Fundamentals, 30% Projects & Publications",
        "focus_areas": ["DSA", "Machine Learning", "Research Projects", "Math Foundations"],
    },
    "Govt": {
        "description": "targeting government / PSU competitive exams",
        "distribution": "60% Aptitude & Reasoning, 20% CS Fundamentals, 20% DSA",
        "focus_areas": ["Aptitude", "Reasoning", "CS Fundamentals", "DSA"],
    },
    "Freelance": {
        "description": "targeting freelance / independent development work",
        "distribution": "50% Web/App Development, 30% Projects & Portfolio, 20% DSA",
        "focus_areas": ["Web Development", "App Development", "Portfolio Projects", "DSA"],
    },
}


# ── LangGraph State ───────────────────────────────────────────────────────────

class RoadmapState(TypedDict):
    student_id: str
    profile: dict
    memory_context: str
    roadmap: dict          # the generated 12-week plan
    error: Optional[str]


# ── Node 1: fetch_profile ─────────────────────────────────────────────────────

async def fetch_profile(state: RoadmapState) -> RoadmapState:
    """Pull the student document from MongoDB."""
    logger.info("[roadmap_agent] fetch_profile | student=%s", state["student_id"])
    db = get_db()

    try:
        student = await db.students.find_one({"_id": ObjectId(state["student_id"])})
        if student is None:
            return {**state, "error": f"Student {state['student_id']} not found."}
        # ObjectId is not JSON-serialisable — convert to str
        student["_id"] = str(student["_id"])
        return {**state, "profile": student}
    except Exception as exc:
        logger.error("[roadmap_agent] fetch_profile error: %s", exc)
        return {**state, "error": str(exc)}


# ── Node 2: recall_memory ─────────────────────────────────────────────────────

async def recall_memory(state: RoadmapState) -> RoadmapState:
    """Ask Cognee for any prior context about this student."""
    if state.get("error"):
        return state

    logger.info("[roadmap_agent] recall_memory | student=%s", state["student_id"])

    from services.cognee_service import recall
    context = await recall(
        state["student_id"],
        "student profile, skills, goals, previous roadmap, mastered topics, weak areas",
        include_ontology=True,   # pull in CS prerequisite relationships to inform topic ordering
    )
    return {**state, "memory_context": context or ""}


# ── Node 3: generate_roadmap ──────────────────────────────────────────────────

async def generate_roadmap(state: RoadmapState) -> RoadmapState:
    """Call Groq (JSON mode) to build the 12-week plan."""
    if state.get("error"):
        return state

    profile = state["profile"]
    goal = profile.get("goal", "FAANG")
    goal_info = GOAL_WEIGHTS.get(goal, GOAL_WEIGHTS["FAANG"])

    logger.info("[roadmap_agent] generate_roadmap | student=%s | goal=%s", state["student_id"], goal)

    memory_section = ""
    if state.get("memory_context"):
        memory_section = f"\nPrevious context about this student:\n{state['memory_context']}\n"

    system_prompt = (
        "You are an expert academic advisor and technical interview coach. "
        "Your task is to create a personalised 12-week learning roadmap for a college student. "
        "Return ONLY valid JSON. No markdown, no backticks, no explanation."
    )

    user_prompt = f"""
Create a 12-week personalised learning roadmap for this student:

Name: {profile.get("name")}
Year: {profile.get("year")} year of college
Goal: {goal} — {goal_info["description"]}
Target Role: {profile.get("target_role")}
Current Skills: {", ".join(profile.get("current_skills", [])) or "none listed"}
{memory_section}
Topic Distribution: {goal_info["distribution"]}
Focus Areas: {", ".join(goal_info["focus_areas"])}

Rules:
- Exactly 12 weeks.
- Each week has one primary "focus" (e.g. "DSA", "System Design") and 3-5 specific "topics".
- Topics must be concrete and actionable (e.g. "Arrays & Sliding Window", not just "Arrays").
- Progressively increase difficulty week over week.
- Align strongly with the student's goal and target role.
- If the student already knows some topics (current_skills), skip basics and start intermediate.

Return this exact JSON structure:
{{
  "weeks": [
    {{
      "week": 1,
      "focus": "DSA",
      "topics": ["Arrays & Two Pointers", "Binary Search", "Sliding Window", "Prefix Sums"]
    }},
    ...12 weeks total...
  ]
}}
"""

    try:
        data = await chat_json([
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_prompt},
        ])

        if "weeks" not in data or not isinstance(data["weeks"], list):
            return {**state, "error": "Model returned unexpected JSON structure."}

        # Normalise — ensure week numbers are correct
        for i, week in enumerate(data["weeks"], start=1):
            week["week"] = i

        return {**state, "roadmap": data}

    except Exception as exc:
        logger.error("[roadmap_agent] generate_roadmap error: %s", exc)
        return {**state, "error": str(exc)}


# ── Node 4: save_to_mongo ─────────────────────────────────────────────────────

async def save_to_mongo(state: RoadmapState) -> RoadmapState:
    """Upsert the roadmap into the roadmaps collection."""
    if state.get("error"):
        return state

    logger.info("[roadmap_agent] save_to_mongo | student=%s", state["student_id"])
    db = get_db()

    doc = {
        "student_id": state["student_id"],
        "weeks": state["roadmap"]["weeks"],
        "generated_at": datetime.now(timezone.utc),
    }

    try:
        await db.roadmaps.update_one(
            {"student_id": state["student_id"]},
            {"$set": doc},
            upsert=True,
        )
        logger.info("[roadmap_agent] save_to_mongo OK")
        return state
    except Exception as exc:
        logger.error("[roadmap_agent] save_to_mongo error: %s", exc)
        return {**state, "error": str(exc)}


# ── Node 5: save_to_cognee ────────────────────────────────────────────────────

async def save_to_cognee(state: RoadmapState) -> RoadmapState:
    """Store a roadmap summary in the student's Cognee memory graph."""
    if state.get("error"):
        return state

    logger.info("[roadmap_agent] save_to_cognee | student=%s", state["student_id"])

    weeks = state["roadmap"]["weeks"]
    # Build a compact text summary — don't dump the whole JSON into memory
    summary_lines = [f"Week {w['week']} [{w['focus']}]: {', '.join(w['topics'])}" for w in weeks]
    summary = " | ".join(summary_lines)

    await remember_roadmap(state["student_id"], summary)
    return state


# ── Route helper ──────────────────────────────────────────────────────────────

def _route(state: RoadmapState) -> str:
    """Stop the graph early if any node set an error."""
    return END if state.get("error") else "continue"


# ── Build graph ───────────────────────────────────────────────────────────────

def _build_graph() -> object:
    g = StateGraph(RoadmapState)

    g.add_node("fetch_profile",    fetch_profile)
    g.add_node("recall_memory",    recall_memory)
    g.add_node("generate_roadmap", generate_roadmap)
    g.add_node("save_to_mongo",    save_to_mongo)
    g.add_node("save_to_cognee",   save_to_cognee)

    g.set_entry_point("fetch_profile")
    g.add_edge("fetch_profile",    "recall_memory")
    g.add_edge("recall_memory",    "generate_roadmap")
    g.add_edge("generate_roadmap", "save_to_mongo")
    g.add_edge("save_to_mongo",    "save_to_cognee")
    g.add_edge("save_to_cognee",   END)

    return g.compile()


_graph = _build_graph()


# ── Public entrypoint ─────────────────────────────────────────────────────────

async def run_roadmap_agent(student_id: str) -> dict:
    """
    Run the full roadmap generation pipeline.

    Returns:
        The roadmap dict  { "weeks": [...] }

    Raises:
        ValueError: if any node reports an error.
    """
    initial: RoadmapState = {
        "student_id": student_id,
        "profile": {},
        "memory_context": "",
        "roadmap": {},
        "error": None,
    }

    final: RoadmapState = await _graph.ainvoke(initial)

    if final.get("error"):
        raise ValueError(final["error"])

    return final["roadmap"]
