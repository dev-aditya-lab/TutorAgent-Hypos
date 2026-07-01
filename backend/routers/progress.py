"""
routers/progress.py
───────────────────
GET /progress/{student_id} → returns a student's progress and the Cognee memory summary
"""

import logging
from fastapi import APIRouter, Depends, HTTPException, status

from db.mongo import get_db
from models.schemas import ProgressResponse, TopicProgress
from utils.auth import CurrentUser, get_current_user
from services.cognee_service import recall

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/progress", tags=["Progress"])


# ── GET /progress/{student_id} ────────────────────────────────────────────────

@router.get(
    "/{student_id}",
    response_model=ProgressResponse,
    summary="Fetch full progress summary from MongoDB + Cognee recall",
)
async def get_progress(
    student_id: str,
    user: CurrentUser = Depends(get_current_user),
):
    """
    Fetch the student's learning progress summary.
    Combines:
        1. Topic-by-topic quiz attempts and performance from MongoDB.
        2. A comprehensive semantic memory narrative from Cognee recall().

    Protected: requires a valid Bearer token.
    Students can only fetch their own progress summary.
    """
    if user.student_id != student_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only access your own progress summary.",
        )

    db = get_db()

    # 1. Fetch progress records from MongoDB
    try:
        cursor = db.progress.find({"student_id": student_id})
        progress_docs = await cursor.to_list(length=100)
    except Exception as exc:
        logger.error("Failed to fetch progress from DB: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve progress records."
        )

    topics_progress = []
    for doc in progress_docs:
        topics_progress.append(
            TopicProgress(
                topic=doc.get("topic", "Unknown"),
                attempts=doc.get("attempts", 0),
                best_score=doc.get("best_score", 0),
                last_attempted=doc.get("last_attempted"),
                weak=doc.get("weak", False)
            )
        )

    # 2. Query Cognee for the semantic memory narrative.
    # The query traverses multiple relationship types across the student graph:
    #   - student identity & goals (from onboarding)
    #   - roadmap plan (weekly topics)
    #   - quiz performance history (struggled/performed well per topic)
    #   - weak areas that need revision
    #   - mastered topics the student has overcome
    #   - mock interview scores and feedback
    # This multi-aspect query leverages Cognee's graph-RAG to produce a
    # connected narrative that a plain vector DB cannot generate.
    logger.info("Fetching graph-RAG memory narrative from Cognee for student=%s", student_id)
    try:
        memory_summary = await recall(
            student_id,
            (
                "Summarise the complete learning journey of this student: "
                "their goals and background, current roadmap plan, "
                "topics they have mastered, topics they have struggled with and need revision, "
                "quiz performance trends, and mock interview scores and feedback."
            ),
            include_ontology=False,
        )
        if not memory_summary:
            memory_summary = (
                "No learning memories recorded yet. "
                "Complete a quiz, generate a roadmap, or conduct an interview to build memory."
            )
    except Exception as exc:
        logger.error("Failed to recall memory from Cognee: %s", exc)
        memory_summary = "Temporarily unable to retrieve semantic memory."

    return ProgressResponse(
        student_id=student_id,
        topics=topics_progress,
        memory_summary=memory_summary
    )
