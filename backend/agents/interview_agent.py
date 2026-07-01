"""
agents/interview_agent.py
─────────────────────────
LangGraph agent that conducts a mock technical interview turn by turn.
Stateless per invocation: receives transcript, context, and session details in the state.

Graph nodes (executed in order):
    recall_memory     → on first question, queries Cognee for the student's background/weak areas
    build_prompt      → construct the interviewer system prompt from memory context
    generate_question → call Groq to produce the next question (or mark as done after 6 questions)
    return_response   → packages the final output

State:
{
  student_id: str,
  session_id: str,
  transcript: [{ role, content }],
  question_number: int,
  context: str,         # cognee recall result
  done: bool,
  next_question: str | None
}
"""

import logging
from typing import Optional

from langgraph.graph import END, StateGraph
from typing_extensions import TypedDict

from services.cognee_service import recall
from services.llm_service import chat

logger = logging.getLogger(__name__)


# ── LangGraph State ───────────────────────────────────────────────────────────

class InterviewState(TypedDict):
    student_id: str
    session_id: str
    transcript: list[dict]
    question_number: int
    context: str
    done: bool
    next_question: Optional[str]
    error: Optional[str]


# ── Node 1: recall_memory ─────────────────────────────────────────────────────

async def recall_memory(state: InterviewState) -> InterviewState:
    """Recall student profile, strong, and weak areas on the first turn."""
    if state.get("error"):
        return state

    # Only recall memory on the first question to shape the interview
    if state["question_number"] > 1:
        return {**state, "context": ""}

    student_id = state["student_id"]
    logger.info("[interview_agent] recall_memory | student=%s", student_id)

    try:
        memory_context = await recall(student_id, "student profile, skills, weak topics, learning progress")
        return {**state, "context": memory_context or ""}
    except Exception as exc:
        logger.error("[interview_agent] recall_memory error: %s", exc)
        return {**state, "context": ""}


# ── Node 2: build_prompt ──────────────────────────────────────────────────────

async def build_prompt(state: InterviewState) -> InterviewState:
    """Prepare system prompt context based on retrieved memory."""
    return state


# ── Node 3: generate_question ─────────────────────────────────────────────────

async def generate_question(state: InterviewState) -> InterviewState:
    """Generate the next interview question using Groq."""
    if state.get("error"):
        return state

    question_num = state["question_number"]
    transcript = state["transcript"]

    logger.info(
        "[interview_agent] generate_question | student=%s | question_number=%d",
        state["student_id"],
        question_num
    )

    # If the user has already answered 6 questions, the interview is done
    if question_num > 6:
        return {**state, "done": True, "next_question": None}

    # Build the system message for the interviewer
    memory_context = state.get("context", "")
    student_context_str = ""
    if memory_context:
        student_context_str = (
            f"\nUse this background context about the student to personalize the interview "
            f"(focus on testing their skills and probing their weak areas if relevant):\n{memory_context}\n"
        )

    system_prompt = (
        "You are an expert technical interviewer conducting a mock interview for a software engineering position.\n"
        "Rules:\n"
        "1. Ask exactly ONE question at a time.\n"
        "2. Do not reveal if the student's previous answer was right or wrong. Be professional, neutral, and encouraging.\n"
        "3. Start with an easy question, and make subsequent questions progressively harder.\n"
        "4. Keep your question concise and focused on a single concept (e.g. data structures, algorithms, system design, databases).\n"
        f"5. You are on Question {question_num} out of 6.\n"
        f"{student_context_str}"
    )

    # Format transcript messages for LLM
    messages = [{"role": "system", "content": system_prompt}]
    
    # Append conversation history
    for turn in transcript:
        # Map roles correctly to API expectations (user, assistant, system)
        role = "user" if turn["role"] == "user" else "assistant"
        messages.append({"role": role, "content": turn["content"]})

    try:
        reply = await chat(messages)
        return {
            **state,
            "next_question": reply.strip(),
            "done": False
        }
    except Exception as exc:
        logger.error("[interview_agent] generate_question error: %s", exc)
        return {**state, "error": str(exc)}


# ── Node 4: return_response ───────────────────────────────────────────────────

async def return_response(state: InterviewState) -> InterviewState:
    """Finalize response."""
    return state


# ── Build graph ───────────────────────────────────────────────────────────────

def _build_graph() -> object:
    g = StateGraph(InterviewState)

    g.add_node("recall_memory",     recall_memory)
    g.add_node("build_prompt",      build_prompt)
    g.add_node("generate_question", generate_question)
    g.add_node("return_response",   return_response)

    g.set_entry_point("recall_memory")
    g.add_edge("recall_memory",     "build_prompt")
    g.add_edge("build_prompt",      "generate_question")
    g.add_edge("generate_question", "return_response")
    g.add_edge("return_response",   END)

    return g.compile()


_graph = _build_graph()


# ── Public entrypoint ─────────────────────────────────────────────────────────

async def run_interview_agent(
    student_id: str,
    session_id: str,
    transcript: list[dict],
    question_number: int
) -> dict:
    """
    Run one turn of the mock interview.

    Returns:
        A dict containing {"question": str | None, "done": bool, "question_number": int}
    """
    initial: InterviewState = {
        "student_id": student_id,
        "session_id": session_id,
        "transcript": transcript,
        "question_number": question_number,
        "context": "",
        "done": False,
        "next_question": None,
        "error": None
    }

    final: InterviewState = await _graph.ainvoke(initial)

    if final.get("error"):
        raise ValueError(final["error"])

    return {
        "question": final["next_question"],
        "done": final["done"],
        "question_number": question_number
    }
