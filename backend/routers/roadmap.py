"""
routers/roadmap.py
──────────────────
POST /roadmap/generate   → run roadmap_agent for the authenticated student
GET  /roadmap/{student_id} → fetch the stored roadmap from MongoDB
"""

import logging
from datetime import datetime, timezone

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, status

from db.mongo import get_db
from models.schemas import RoadmapResponse, WeekPlan
from utils.auth import CurrentUser, get_current_user
from agents.roadmap_agent import run_roadmap_agent

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/roadmap", tags=["Roadmap"])


# ── POST /roadmap/generate ────────────────────────────────────────────────────

@router.post(
    "/generate",
    response_model=RoadmapResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Generate a personalised 12-week roadmap for the authenticated student",
)
async def generate_roadmap(user: CurrentUser = Depends(get_current_user)):
    """
    Triggers the LangGraph roadmap agent pipeline:
        1. Fetch student profile from MongoDB
        2. Recall Cognee memory for prior context
        3. Generate 12-week plan via Groq (JSON mode)
        4. Upsert into MongoDB roadmaps collection
        5. Store roadmap summary in Cognee memory

    Protected: requires a valid Bearer token.
    The student_id is taken from the JWT — no body needed.
    """
    logger.info("POST /roadmap/generate | student=%s", user.student_id)

    try:
        roadmap = await run_roadmap_agent(user.student_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )
    except Exception as exc:
        logger.error("Roadmap generation failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Roadmap generation failed. Please try again.",
        )

    return RoadmapResponse(
        student_id=user.student_id,
        weeks=[WeekPlan(**w) for w in roadmap["weeks"]],
        generated_at=datetime.now(timezone.utc),
    )


# ── GET /roadmap/{student_id} ─────────────────────────────────────────────────

@router.get(
    "/{student_id}",
    response_model=RoadmapResponse,
    summary="Fetch the stored roadmap for a student",
)
async def get_roadmap(
    student_id: str,
    user: CurrentUser = Depends(get_current_user),
):
    """
    Fetch the most recently generated roadmap from MongoDB.

    Students can only access their own roadmap (student_id must match JWT).
    """
    if user.student_id != student_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only access your own roadmap.",
        )

    db = get_db()
    roadmap_doc = await db.roadmaps.find_one({"student_id": student_id})

    if roadmap_doc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No roadmap found. Call POST /roadmap/generate first.",
        )

    return RoadmapResponse(
        student_id=student_id,
        weeks=[WeekPlan(**w) for w in roadmap_doc["weeks"]],
        generated_at=roadmap_doc.get("generated_at", datetime.now(timezone.utc)),
    )
