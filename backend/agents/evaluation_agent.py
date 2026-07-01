"""
agents/evaluation_agent.py
──────────────────────────
LangGraph agent that runs when a mock technical interview is finished.
Evaluates the full transcript and writes results to MongoDB and Cognee.

Graph nodes (executed in order):
    fetch_transcript → pull the interview session and transcript from MongoDB
    evaluate         → call Groq (JSON mode) to grade the interview
    save_interview   → save evaluation report to interviews collection
    update_progress  → flag weak topics in the progress collection
    save_to_cognee   → store high-level interview summary in Cognee memory graph

State:
{
  session_id: str,
  student_id: str,
  transcript: list,
  evaluation: dict,
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
from services.cognee_service import remember_interview, remember_weak_topic
from services.llm_service import chat_json

logger = logging.getLogger(__name__)


# ── LangGraph State ───────────────────────────────────────────────────────────

class EvalState(TypedDict):
    session_id: str
    student_id: str
    transcript: list[dict]
    evaluation: dict
    error: Optional[str]


# ── Node 1: fetch_transcript ──────────────────────────────────────────────────

async def fetch_transcript(state: EvalState) -> EvalState:
    """Pull the interview transcript from MongoDB by session_id."""
    logger.info("[evaluation_agent] fetch_transcript | session=%s", state["session_id"])
    db = get_db()

    try:
        session = await db.interview_sessions.find_one({"_id": ObjectId(state["session_id"])})
        if not session:
            return {**state, "error": f"Interview session {state['session_id']} not found."}
        
        return {
            **state,
            "student_id": session.get("student_id", state["student_id"]),
            "transcript": session.get("transcript", [])
        }
    except Exception as exc:
        logger.error("[evaluation_agent] fetch_transcript error: %s", exc)
        return {**state, "error": str(exc)}


# ── Node 2: evaluate ──────────────────────────────────────────────────────────

async def evaluate(state: EvalState) -> EvalState:
    """Send transcript to Groq for mock technical interview evaluation."""
    if state.get("error"):
        return state

    transcript = state["transcript"]
    logger.info("[evaluation_agent] evaluate | student=%s | turns=%d", state["student_id"], len(transcript))

    if not transcript:
        return {**state, "error": "Cannot evaluate an empty interview transcript."}

    system_prompt = (
        "You are evaluating a mock technical software engineering interview.\n"
        "Analyze the transcript (exchanges between Assistant/Interviewer and User/Student) "
        "and score the student out of 100.\n"
        "Identify specific strong topics and weak topics (technologies, core concepts, or skills).\n"
        "Provide a high-level constructive feedback summary.\n"
        "Provide a question-by-question breakdown containing the question asked, a verdict on the student's answer, and a score out of 10 for each question.\n"
        "Return ONLY valid JSON. No markdown, no backticks, no explanation."
    )

    user_prompt = f"""
Evaluate this mock technical interview transcript:

Transcript:
{transcript}

Return this exact JSON structure:
{{
  "score": 85,
  "strong_topics": ["Arrays", "Big-O Notation"],
  "weak_topics": ["Dynamic Programming", "Recursion"],
  "feedback": "Overall strong algorithmic thinking, but struggled to optimize recursion using memoization.",
  "per_question": [
    {{
      "question": "Question text...",
      "verdict": "Student answered correctly and optimized the solution.",
      "score": 9
    }}
  ]
}}
"""

    try:
        eval_data = await chat_json([
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_prompt}
        ])

        # Validate structure
        required_fields = ["score", "strong_topics", "weak_topics", "feedback", "per_question"]
        if not all(field in eval_data for field in required_fields):
            return {**state, "error": "Evaluation report is missing required evaluation fields."}

        return {**state, "evaluation": eval_data}

    except Exception as exc:
        logger.error("[evaluation_agent] evaluate error: %s", exc)
        return {**state, "error": str(exc)}


# ── Node 3: save_interview ────────────────────────────────────────────────────

async def save_interview(state: EvalState) -> EvalState:
    """Save the final interview report to the interviews collection."""
    if state.get("error"):
        return state

    student_id = state["student_id"]
    evaluation = state["evaluation"]
    logger.info("[evaluation_agent] save_interview | student=%s", student_id)
    db = get_db()

    # Determine current month index (1 to 12) for tracking
    month_idx = datetime.now(timezone.utc).month

    doc = {
        "student_id": student_id,
        "month": month_idx,
        "transcript": state["transcript"],
        "score": evaluation["score"],
        "strong_topics": evaluation["strong_topics"],
        "weak_topics": evaluation["weak_topics"],
        "feedback": evaluation["feedback"],
        "conducted_at": datetime.now(timezone.utc)
    }

    try:
        await db.interviews.insert_one(doc)
        
        # Clean up the temporary session
        await db.interview_sessions.delete_one({"_id": ObjectId(state["session_id"])})
        logger.info("[evaluation_agent] save_interview OK & session deleted")
        return state
    except Exception as exc:
        logger.error("[evaluation_agent] save_interview error: %s", exc)
        return {**state, "error": str(exc)}


# ── Node 4: update_progress ───────────────────────────────────────────────────

async def update_progress(state: EvalState) -> EvalState:
    """Flag all identified weak topics in the progress collection."""
    if state.get("error"):
        return state

    student_id = state["student_id"]
    weak_topics = state["evaluation"]["weak_topics"]
    logger.info("[evaluation_agent] update_progress | student=%s | weak_topics=%s", student_id, weak_topics)
    db = get_db()

    try:
        for topic in weak_topics:
            # We flag this topic as weak in the student's progress report
            progress_doc = await db.progress.find_one({"student_id": student_id, "topic": topic})
            attempts = 1
            best_score = 0
            if progress_doc:
                attempts = progress_doc.get("attempts", 0) + 1
                best_score = progress_doc.get("best_score", 0)

            # Update topic to weak=True since evaluation flagged it
            await db.progress.update_one(
                {"student_id": student_id, "topic": topic},
                {
                    "$set": {
                        "attempts": attempts,
                        "best_score": best_score,
                        "last_attempted": datetime.now(timezone.utc),
                        "weak": True
                    }
                },
                upsert=True
            )
            # Also tell Cognee directly that this topic is a weak area
            await remember_weak_topic(student_id, topic)

        return state
    except Exception as exc:
        logger.error("[evaluation_agent] update_progress error: %s", exc)
        return {**state, "error": str(exc)}


# ── Node 5: save_to_cognee ────────────────────────────────────────────────────

async def save_to_cognee(state: EvalState) -> EvalState:
    """Save the overall interview results to Cognee."""
    if state.get("error"):
        return state

    student_id = state["student_id"]
    evaluation = state["evaluation"]
    logger.info("[evaluation_agent] save_to_cognee | student=%s", student_id)

    month_idx = datetime.now(timezone.utc).month

    try:
        await remember_interview(
            student_id=student_id,
            month=month_idx,
            score=evaluation["score"],
            strong=evaluation["strong_topics"],
            weak=evaluation["weak_topics"],
            feedback=evaluation["feedback"]
        )
        logger.info("[evaluation_agent] save_to_cognee OK")
        return state
    except Exception as exc:
        logger.error("[evaluation_agent] save_to_cognee error: %s", exc)
        return state


# ── Build graph ───────────────────────────────────────────────────────────────

def _build_graph() -> object:
    g = StateGraph(EvalState)

    g.add_node("fetch_transcript", fetch_transcript)
    g.add_node("evaluate",         evaluate)
    g.add_node("save_interview",   save_interview)
    g.add_node("update_progress",  update_progress)
    g.add_node("save_to_cognee",   save_to_cognee)

    g.set_entry_point("fetch_transcript")
    g.add_edge("fetch_transcript", "evaluate")
    g.add_edge("evaluate",         "save_interview")
    g.add_edge("save_interview",   "update_progress")
    g.add_edge("update_progress",  "save_to_cognee")
    g.add_edge("save_to_cognee",   END)

    return g.compile()


_graph = _build_graph()


# ── Public entrypoint ─────────────────────────────────────────────────────────

async def run_evaluation_agent(session_id: str, student_id: str) -> dict:
    """
    Run the full interview evaluation pipeline.

    Returns:
        The detailed evaluation report dict.
    """
    initial: EvalState = {
        "session_id": session_id,
        "student_id": student_id,
        "transcript": [],
        "evaluation": {},
        "error": None
    }

    final: EvalState = await _graph.ainvoke(initial)

    if final.get("error"):
        raise ValueError(final["error"])

    return final["evaluation"]
