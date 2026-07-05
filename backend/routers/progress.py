"""
routers/progress.py
───────────────────
GET /progress/{student_id}

Returns a fully structured progress response combining:
  1. Topic-by-topic MongoDB stats (attempts, scores, weak flags)
  2. A MemorySummary — Cognee's graph-RAG output parsed into named sections

The Cognee narrative is parsed into sections using the section headers
that the LLM consistently produces in its structured output.
"""

import logging
import re
from fastapi import APIRouter, Depends, HTTPException, status

from db.mongo import get_db
from models.schemas import MemorySummary, ProgressResponse, TopicProgress
from utils.auth import CurrentUser, get_current_user
from services.cognee_service import recall

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/progress", tags=["Progress"])


# ── Section parser ────────────────────────────────────────────────────────────

# Maps normalised section-header keywords → MemorySummary field names
_SECTION_MAP = {
    "student profile":   "student_profile",
    "profile":           "student_profile",
    "background":        "student_profile",
    "roadmap":           "roadmap_overview",
    "12-week":           "roadmap_overview",
    "learning plan":     "roadmap_overview",
    "mastered":          "topics_mastered",
    "conquered":         "topics_mastered",
    "struggled":         "topics_to_revise",
    "revision":          "topics_to_revise",
    "weak":              "topics_to_revise",
    "quiz":              "quiz_trends",
    "performance":       "quiz_trends",
    "interview":         "interview_summary",
    "mock interview":    "interview_summary",
    "summary":           "narrative",
    "overall":           "narrative",
}


def _parse_memory_sections(text: str) -> MemorySummary:
    """
    Parse Cognee's plain-text narrative into named MemorySummary sections.

    Strategy:
      - Split the text on lines that look like section headers
        (short lines that are title-cased, ALL CAPS, or end with a colon)
      - Match each header to a known section keyword
      - Assign the following paragraph(s) to that section field
      - Everything unmatched goes into `narrative`
    """
    if not text or not text.strip():
        return MemorySummary(raw="")

    # Split into paragraphs first
    paragraphs = [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]

    sections: dict[str, list[str]] = {
        "student_profile":  [],
        "roadmap_overview": [],
        "topics_mastered":  [],
        "topics_to_revise": [],
        "quiz_trends":      [],
        "interview_summary":[],
        "narrative":        [],
    }

    current_section = "narrative"  # default bucket

    for para in paragraphs:
        # Detect a section-header paragraph:
        # - 10 words or fewer AND matches a known keyword
        first_line = para.split("\n")[0].lower()
        word_count = len(first_line.split())

        matched_field = None
        if word_count <= 10:
            for keyword, field in _SECTION_MAP.items():
                if keyword in first_line:
                    matched_field = field
                    break

        if matched_field:
            current_section = matched_field
            # The rest of the paragraph after the header line is content
            rest = "\n".join(para.split("\n")[1:]).strip()
            if rest:
                sections[current_section].append(rest)
        else:
            sections[current_section].append(para)

    def _join(parts: list[str]) -> str | None:
        joined = "\n\n".join(parts).strip()
        return joined if joined else None

    return MemorySummary(
        student_profile   = _join(sections["student_profile"]),
        roadmap_overview  = _join(sections["roadmap_overview"]),
        topics_mastered   = _join(sections["topics_mastered"]),
        topics_to_revise  = _join(sections["topics_to_revise"]),
        quiz_trends       = _join(sections["quiz_trends"]),
        interview_summary = _join(sections["interview_summary"]),
        narrative         = _join(sections["narrative"]),
        raw               = text,
    )


# ── GET /progress/{student_id} ────────────────────────────────────────────────

@router.get(
    "/{student_id}",
    response_model=ProgressResponse,
    summary="Fetch full structured progress: MongoDB stats + Cognee graph-RAG memory",
)
async def get_progress(
    student_id: str,
    user: CurrentUser = Depends(get_current_user),
):
    """
    Returns a structured ProgressResponse:

    topics   → per-topic MongoDB stats (attempts, best score, weak flag)
    memory   → MemorySummary parsed from Cognee's graph-RAG narrative:
                 - student_profile   : goals and background
                 - roadmap_overview  : 12-week plan summary
                 - topics_mastered   : topics the student has conquered
                 - topics_to_revise  : weak areas needing revision
                 - quiz_trends       : quiz performance patterns
                 - interview_summary : mock interview scores and feedback
                 - narrative         : overall AI learning journey summary
                 - raw               : full cleaned Cognee text (for debugging)
    """
    if user.student_id != student_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only access your own progress summary.",
        )

    db = get_db()

    # 1. Fetch per-topic progress from MongoDB
    try:
        cursor       = db.progress.find({"student_id": student_id})
        progress_docs = await cursor.to_list(length=100)
    except Exception as exc:
        logger.error("Failed to fetch progress from DB: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve progress records.",
        )

    topics_progress = [
        TopicProgress(
            topic         = doc.get("topic", "Unknown"),
            attempts      = doc.get("attempts", 0),
            best_score    = doc.get("best_score", 0),
            last_attempted= doc.get("last_attempted"),
            weak          = doc.get("weak", False),
        )
        for doc in progress_docs
    ]

    # 2. Query Cognee graph-RAG and parse into structured sections
    logger.info("Fetching graph-RAG memory narrative from Cognee for student=%s", student_id)
    try:
        raw_text = await recall(
            student_id,
            (
                "Student profile: goals, background, academic year. "
                "Roadmap: current 12-week learning plan. "
                "Mastered topics: topics the student has consistently scored above 80% on. "
                "Topics to revise: weak areas the student has struggled with. "
                "Quiz trends: quiz scores and performance history. "
                "Interview summary: mock interview scores and feedback. "
                "Summary: overall learning journey narrative."
            ),
            include_ontology=False,
        )

        if not raw_text:
            memory = MemorySummary(
                narrative=(
                    "No learning memories recorded yet. "
                    "Complete a quiz, generate a roadmap, or conduct an interview to build memory."
                ),
                raw="",
            )
        else:
            memory = _parse_memory_sections(raw_text)

    except Exception as exc:
        logger.error("Failed to recall memory from Cognee: %s", exc)
        memory = MemorySummary(
            narrative="Temporarily unable to retrieve semantic memory.",
            raw="",
        )

    return ProgressResponse(
        student_id=student_id,
        topics=topics_progress,
        memory=memory,
    )
