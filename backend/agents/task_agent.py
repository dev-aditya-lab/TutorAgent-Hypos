"""
agents/task_agent.py
────────────────────
LangGraph agent that generates a daily learning task for a student.

Graph nodes (executed in order):
    fetch_roadmap   → get the current week's topic based on roadmap date offset
    recall_memory   → cognee.recall() to check what the student struggled with recently
                      (if a weak topic is found, override today's topic for revision)
    generate_task   → call Groq to generate a resource + 5 MCQ questions
    save_task       → store the generated task in the daily_tasks collection

State:
{
  student_id: str,
  date: str,              # "YYYY-MM-DD"
  topic: str,             # today's topic
  task: dict,             # generated task content
  error: str | None
}
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from bson import ObjectId
from langgraph.graph import END, StateGraph
from typing_extensions import TypedDict

from db.mongo import get_db
from services.cognee_service import recall, recall_topic_prerequisites
from services.llm_service import chat_json

logger = logging.getLogger(__name__)


# ── LangGraph State ───────────────────────────────────────────────────────────

class TaskState(TypedDict):
    student_id: str
    date: str
    topic: str
    task: dict
    error: Optional[str]


# ── Node 1: fetch_roadmap ─────────────────────────────────────────────────────

async def fetch_roadmap(state: TaskState) -> TaskState:
    """Determine today's topic based on the student's 12-week roadmap."""
    logger.info("[task_agent] fetch_roadmap | student=%s", state["student_id"])
    db = get_db()

    try:
        # Fetch student's roadmap
        roadmap = await db.roadmaps.find_one({"student_id": state["student_id"]})
        if not roadmap:
            # Fallback topic if no roadmap generated yet
            logger.warning("[task_agent] No roadmap found for student. Using fallback topic 'CS Fundamentals'")
            return {**state, "topic": "CS Fundamentals"}

        # Calculate week offset
        gen_at = roadmap.get("generated_at")
        if not gen_at:
            gen_at = datetime.now(timezone.utc)
        elif gen_at.tzinfo is None:
            gen_at = gen_at.replace(tzinfo=timezone.utc)

        now = datetime.now(timezone.utc)
        days_diff = (now - gen_at).days
        week_num = (days_diff // 7) + 1
        week_num = max(1, min(12, week_num))  # Cap between 1 and 12

        # Find the week plan
        weeks = roadmap.get("weeks", [])
        week_plan = next((w for w in weeks if w.get("week") == week_num), None)
        if not week_plan or not week_plan.get("topics"):
            # Fallback if week index is missing
            week_plan = weeks[0] if weeks else {"topics": ["CS Fundamentals"]}

        topics = week_plan.get("topics", ["CS Fundamentals"])
        # Select topic deterministically using day offset
        topic_index = days_diff % len(topics)
        selected_topic = topics[topic_index]

        logger.info("[task_agent] Selected topic from roadmap: week=%d, topic='%s'", week_num, selected_topic)
        return {**state, "topic": selected_topic}

    except Exception as exc:
        logger.error("[task_agent] fetch_roadmap error: %s", exc)
        return {**state, "error": str(exc)}


# ── Node 2: recall_memory ─────────────────────────────────────────────────────

async def recall_memory(state: TaskState) -> TaskState:
    """Recall what topics the student has struggled with recently via Cognee."""
    if state.get("error"):
        return state

    student_id = state["student_id"]
    logger.info("[task_agent] recall_memory | student=%s", student_id)

    try:
        # Search for struggles or weak areas
        memory_result = await recall(student_id, "what has student struggled with recently, weak topics")
        if not memory_result:
            return state

        # Call LLM to quickly parse the memory and extract a specific revision topic if relevant
        prompt = [
            {
                "role": "system",
                "content": (
                    "You are a parser. Analyze the memory query results and determine if there is a specific technical topic "
                    "the student has struggled with recently that needs revision. "
                    "Return ONLY valid JSON. No markdown, no explanation."
                )
            },
            {
                "role": "user",
                "content": (
                    f"Memory Query Results:\n{memory_result}\n\n"
                    "If a clear weak topic is found, return {\"weak_topic\": \"<topic_name>\"}. "
                    "If no clear weak topic is found, return {\"weak_topic\": null}."
                )
            }
        ]

        parsed = await chat_json(prompt)
        weak_topic = parsed.get("weak_topic")

        if weak_topic:
            logger.info("[task_agent] Overriding topic '%s' with weak topic '%s' for revision", state["topic"], weak_topic)
            return {**state, "topic": f"Revision: {weak_topic}"}

        return state

    except Exception as exc:
        logger.error("[task_agent] recall_memory error: %s", exc)
        # Continue with roadmap topic if memory recall fails
        return state


# ── Node 3: generate_task ─────────────────────────────────────────────────────

async def generate_task(state: TaskState) -> TaskState:
    """Generate the study resource and 5 MCQs using Groq, enriched with Cognee ontology context."""
    if state.get("error"):
        return state

    topic = state["topic"]
    logger.info("[task_agent] generate_task | topic='%s'", topic)

    # ── Enrich with CS ontology (prerequisite/relationship graph) ─────────────
    # Query the shared Cognee ontology dataset to find prerequisite and related
    # topics. This means the quiz is aware of what the student should already
    # know, and can include bridging questions that connect concepts.
    prerequisite_context = ""
    try:
        prereqs = await recall_topic_prerequisites(topic)
        if prereqs:
            prerequisite_context = (
                f"\nTopic relationship context from knowledge graph:\n{prereqs}\n"
                "Use this to include 1-2 bridging questions that test prerequisite knowledge."
            )
            logger.info("[task_agent] Ontology context retrieved for topic '%s'", topic)
    except Exception as exc:
        logger.warning("[task_agent] Ontology recall failed (non-fatal): %s", exc)

    system_prompt = (
        "You are an expert tutor. Your task is to generate a comprehensive daily learning resource "
        "and a set of 5 multiple choice questions to test understanding of the topic.\n"
        "Return ONLY valid JSON. No markdown, no backticks, no explanation."
    )

    user_prompt = f"""
Generate a daily task for the topic: "{topic}".
{prerequisite_context}
Your response must contain:
1. A resource with a clear title and a ~300 word detailed, high-quality, conceptual explanation of the topic.
2. A set of exactly 5 multiple choice questions (MCQ) testing different difficulty levels (easy to hard).
3. Each question must have exactly 4 options.
4. Each question must have a 'correct_index' (0 to 3) indicating the zero-indexed position of the correct answer.

Return this exact JSON structure:
{{
  "resource": {{
    "title": "Clear Topic Title",
    "content": "Detailed ~300-word explanation of the topic..."
  }},
  "questions": [
    {{
      "question": "Question text here?",
      "options": ["Option A", "Option B", "Option C", "Option D"],
      "correct_index": 0
    }},
    ...4 more questions...
  ]
}}
"""

    try:
        task_data = await chat_json([
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_prompt},
        ])

        # Validate structure
        if "resource" not in task_data or "questions" not in task_data:
            return {**state, "error": "Generated task is missing resource or questions."}
        if len(task_data.get("questions", [])) != 5:
            return {**state, "error": f"Generated {len(task_data.get('questions', []))} questions, expected 5."}

        return {**state, "task": task_data}

    except Exception as exc:
        logger.error("[task_agent] generate_task error: %s", exc)
        return {**state, "error": str(exc)}


# ── Node 4: save_task ─────────────────────────────────────────────────────────

async def save_task(state: TaskState) -> TaskState:
    """Save the generated task to MongoDB daily_tasks collection."""
    if state.get("error"):
        return state

    logger.info("[task_agent] save_task | student=%s | date=%s", state["student_id"], state["date"])
    db = get_db()

    doc = {
        "student_id": state["student_id"],
        "date": state["date"],
        "topic": state["topic"],
        "resource": state["task"]["resource"],
        "questions": state["task"]["questions"],
        "submitted": False,
        "score": None,
        "struggled": False
    }

    try:
        # Upsert by student_id and date
        result = await db.daily_tasks.update_one(
            {"student_id": state["student_id"], "date": state["date"]},
            {"$set": doc},
            upsert=True
        )
        if result.upserted_id:
            state["task"]["task_id"] = str(result.upserted_id)
        else:
            existing = await db.daily_tasks.find_one({"student_id": state["student_id"], "date": state["date"]})
            if existing:
                state["task"]["task_id"] = str(existing["_id"])
        
        return state

    except Exception as exc:
        logger.error("[task_agent] save_task error: %s", exc)
        return {**state, "error": str(exc)}


# ── Build graph ───────────────────────────────────────────────────────────────

def _build_graph() -> object:
    g = StateGraph(TaskState)

    g.add_node("fetch_roadmap", fetch_roadmap)
    g.add_node("recall_memory", recall_memory)
    g.add_node("generate_task", generate_task)
    g.add_node("save_task",     save_task)

    g.set_entry_point("fetch_roadmap")
    g.add_edge("fetch_roadmap", "recall_memory")
    g.add_edge("recall_memory", "generate_task")
    g.add_edge("generate_task", "save_task")
    g.add_edge("save_task",     END)

    return g.compile()


_graph = _build_graph()


# ── Public entrypoint ─────────────────────────────────────────────────────────

async def run_task_agent(student_id: str, date: str) -> dict:
    """
    Run the task generation pipeline.

    Returns:
        The generated task dict containing resource, questions, and task_id.
    """
    initial: TaskState = {
        "student_id": student_id,
        "date": date,
        "topic": "",
        "task": {},
        "error": None
    }

    final: TaskState = await _graph.ainvoke(initial)

    if final.get("error"):
        raise ValueError(final["error"])

    return final["task"]
