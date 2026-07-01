"""
routers/interview.py
────────────────────
POST /interview/start   → start interview, create session, return first question
POST /interview/respond → process student answer, generate next question or conclude
POST /interview/end     → trigger evaluation_agent, save to database and Cognee
"""

import logging
from datetime import datetime, timezone

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, status

from db.mongo import get_db
from models.schemas import (
    InterviewStartRequest,
    InterviewStartResponse,
    InterviewRespondRequest,
    InterviewRespondResponse,
    InterviewEndRequest,
    InterviewEvaluation,
    PerQuestionEval,
)
from utils.auth import CurrentUser, get_current_user
from agents.interview_agent import run_interview_agent
from agents.evaluation_agent import run_evaluation_agent

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/interview", tags=["Interview"])


# ── POST /interview/start ─────────────────────────────────────────────────────

@router.post(
    "/start",
    response_model=InterviewStartResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Start a new mock interview session and get the first question",
)
async def start_interview(
    body: InterviewStartRequest,
    user: CurrentUser = Depends(get_current_user),
):
    """
    Start a new mock interview session.
    Fleshes out a temporary session in the database, queries Cognee for student profile,
    and returns the first customized technical question.
    """
    if user.student_id != body.student_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only start an interview for yourself.",
        )

    db = get_db()

    # 1. Create a placeholder session document to get an ID
    session_doc = {
        "student_id": body.student_id,
        "transcript": [],
        "question_number": 1,
        "created_at": datetime.now(timezone.utc)
    }
    result = await db.interview_sessions.insert_one(session_doc)
    session_id = str(result.inserted_id)

    # 2. Run the interview agent to generate the first question
    try:
        agent_res = await run_interview_agent(
            student_id=body.student_id,
            session_id=session_id,
            transcript=[],
            question_number=1
        )
        first_q = agent_res.get("question")
        if not first_q:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Interviewer agent failed to generate the first question."
            )

        # 3. Store the first question in the transcript
        await db.interview_sessions.update_one(
            {"_id": ObjectId(session_id)},
            {
                "$push": {
                    "transcript": {"role": "assistant", "content": first_q}
                }
            }
        )

        return InterviewStartResponse(
            session_id=session_id,
            first_question=first_q,
            question_number=1
        )

    except Exception as exc:
        logger.error("Failed to start interview session: %s", exc)
        # Clean up the session placeholder if creation fails
        await db.interview_sessions.delete_one({"_id": ObjectId(session_id)})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to initialize mock interview. Please try again."
        )


# ── POST /interview/respond ───────────────────────────────────────────────────

@router.post(
    "/respond",
    response_model=InterviewRespondResponse,
    summary="Submit student answer and get the next question or completion signal",
)
async def respond_interview(
    body: InterviewRespondRequest,
    user: CurrentUser = Depends(get_current_user),
):
    """
    Submit the student's answer to the previous question and retrieve the next question.
    Concludes the interview after 6 questions.
    """
    if user.student_id != body.student_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only respond to your own interview session.",
        )

    db = get_db()

    # 1. Fetch the active interview session
    try:
        session_id_obj = ObjectId(body.session_id)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid session_id format.",
        )

    session = await db.interview_sessions.find_one({"_id": session_id_obj, "student_id": body.student_id})
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Active interview session not found.",
        )

    transcript = session.get("transcript", [])
    current_q_num = session.get("question_number", 1)

    # 2. Append student answer to the transcript in memory and DB
    new_turn_student = {"role": "user", "content": body.answer.strip()}
    transcript.append(new_turn_student)

    await db.interview_sessions.update_one(
        {"_id": session_id_obj},
        {
            "$push": {
                "transcript": new_turn_student
            }
        }
    )

    # 3. Call interview agent to get next question or done signal
    next_q_num = current_q_num + 1
    try:
        agent_res = await run_interview_agent(
            student_id=body.student_id,
            session_id=body.session_id,
            transcript=transcript,
            question_number=next_q_num
        )

        done = agent_res.get("done", False)
        next_q = agent_res.get("question")

        if done or next_q_num > 6:
            # Mark the session status in DB
            await db.interview_sessions.update_one(
                {"_id": session_id_obj},
                {
                    "$set": {
                        "question_number": next_q_num,
                        "done": True
                    }
                }
            )
            return InterviewRespondResponse(
                question=None,
                question_number=current_q_num,
                done=True
            )

        # 4. Save the next question to the database transcript
        new_turn_agent = {"role": "assistant", "content": next_q}
        await db.interview_sessions.update_one(
            {"_id": session_id_obj},
            {
                "$set": {
                    "question_number": next_q_num
                },
                "$push": {
                    "transcript": new_turn_agent
                }
            }
        )

        return InterviewRespondResponse(
            question=next_q,
            question_number=next_q_num,
            done=False
        )

    except Exception as exc:
        logger.error("Failed to process interview response: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate the next interview question."
        )


# ── POST /interview/end ───────────────────────────────────────────────────────

@router.post(
    "/end",
    response_model=InterviewEvaluation,
    summary="Conclude the mock interview and receive the evaluation report",
)
async def end_interview(
    body: InterviewEndRequest,
    user: CurrentUser = Depends(get_current_user),
):
    """
    End the mock interview session. Triggers the LangGraph evaluation agent to
    analyze the full transcript, score it, save the details to DB and Cognee,
    and clean up the session.
    """
    if user.student_id != body.student_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only end your own interview session.",
        )

    logger.info("Ending interview session=%s for student=%s", body.session_id, body.student_id)

    try:
        report = await run_evaluation_agent(
            session_id=body.session_id,
            student_id=body.student_id
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc)
        )
    except Exception as exc:
        logger.error("Interview evaluation agent failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Mock interview evaluation failed. Please try again."
        )

    return InterviewEvaluation(
        score=report["score"],
        strong_topics=report["strong_topics"],
        weak_topics=report["weak_topics"],
        feedback=report["feedback"],
        per_question=[PerQuestionEval(**q) for q in report["per_question"]]
    )
