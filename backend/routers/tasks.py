"""
routers/tasks.py
────────────────
GET  /tasks/today/{student_id}  → retrieve or generate today's task
POST /tasks/submit              → submit answers, calculate score, update progress & Cognee
"""

import logging
from datetime import datetime, timezone

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, status

from db.mongo import get_db
from models.schemas import (
    DailyTaskResponse,
    MCQQuestion,
    SubmitTaskRequest,
    SubmitTaskResponse,
    TaskResource,
)
from utils.auth import CurrentUser, get_current_user
from agents.task_agent import run_task_agent
from services.cognee_service import remember_task_result, remember_weak_topic, forget_mastered_topic
from services.llm_service import chat

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tasks", tags=["Daily Tasks"])


# ── GET /tasks/today/{student_id} ─────────────────────────────────────────────

@router.get(
    "/today/{student_id}",
    response_model=DailyTaskResponse,
    summary="Get or generate today's task for the student",
)
async def get_today_task(
    student_id: str,
    user: CurrentUser = Depends(get_current_user),
):
    """
    Fetch the student's daily task for today (formatted as YYYY-MM-DD).
    If it doesn't exist, trigger the LangGraph task agent to generate it.

    Protected: requires valid Bearer token.
    Students can only fetch their own daily task.
    """
    if user.student_id != student_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only access your own daily tasks.",
        )

    db = get_db()
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # 1. Check if daily task already exists for today
    task_doc = await db.daily_tasks.find_one({"student_id": student_id, "date": today_str})

    if task_doc:
        logger.info("Found existing daily task for student=%s, date=%s", student_id, today_str)
        return DailyTaskResponse(
            task_id=str(task_doc["_id"]),
            student_id=task_doc["student_id"],
            date=task_doc["date"],
            topic=task_doc["topic"],
            resource=TaskResource(**task_doc["resource"]),
            questions=[MCQQuestion(**q) for q in task_doc["questions"]],
            submitted=task_doc.get("submitted", False),
            score=task_doc.get("score"),
        )

    # 2. Generate daily task if not exists
    logger.info("Daily task not found. Generating new task for student=%s, date=%s", student_id, today_str)
    try:
        task_data = await run_task_agent(student_id, today_str)
        
        # Get the task doc from DB to fetch database ID
        task_doc = await db.daily_tasks.find_one({"student_id": student_id, "date": today_str})
        if not task_doc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Daily task generation succeeded but document was not found in DB."
            )

        return DailyTaskResponse(
            task_id=str(task_doc["_id"]),
            student_id=task_doc["student_id"],
            date=task_doc["date"],
            topic=task_doc["topic"],
            resource=TaskResource(**task_doc["resource"]),
            questions=[MCQQuestion(**q) for q in task_doc["questions"]],
            submitted=task_doc.get("submitted", False),
            score=task_doc.get("score"),
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )
    except Exception as exc:
        logger.error("Daily task generation failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate daily task. Please try again.",
        )


# ── POST /tasks/submit ────────────────────────────────────────────────────────

@router.post(
    "/submit",
    response_model=SubmitTaskResponse,
    summary="Submit answers for a daily task, score them, and update memory",
)
async def submit_task(
    body: SubmitTaskRequest,
    user: CurrentUser = Depends(get_current_user),
):
    """
    Submit multiple choice answers for a daily task.
    Calculates the score, updates the task submission status,
    updates progress history, and records findings in Cognee memory.
    """
    if user.student_id != body.student_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only submit answers for yourself.",
        )

    db = get_db()

    # 1. Fetch the daily task
    try:
        task_id_obj = ObjectId(body.task_id)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid task_id format.",
        )

    task = await db.daily_tasks.find_one({"_id": task_id_obj, "student_id": body.student_id})
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Daily task not found.",
        )

    if task.get("submitted"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This task has already been submitted.",
        )

    questions = task.get("questions", [])
    if len(body.answers) != len(questions):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Expected {len(questions)} answers, but received {len(body.answers)}.",
        )

    # 2. Score the answers
    correct_count = 0
    detailed_results = []
    for i, user_ans in enumerate(body.answers):
        correct_ans = questions[i].get("correct_index")
        is_correct = user_ans == correct_ans
        if is_correct:
            correct_count += 1
        detailed_results.append({
            "question": questions[i].get("question"),
            "user_answer": questions[i]["options"][user_ans] if 0 <= user_ans < 4 else "Invalid Option",
            "correct_answer": questions[i]["options"][correct_ans],
            "correct": is_correct
        })

    percentage = int((correct_count / len(questions)) * 100)
    struggled = percentage < 60
    topic = task.get("topic", "Unknown")

    # 3. Update the daily task document
    await db.daily_tasks.update_one(
        {"_id": task_id_obj},
        {
            "$set": {
                "submitted": True,
                "score": percentage,
                "struggled": struggled
            }
        }
    )

    # 4. Update the progress collection
    progress = await db.progress.find_one({"student_id": body.student_id, "topic": topic})
    
    attempts = 1
    best_score = percentage
    if progress:
        attempts = progress.get("attempts", 0) + 1
        best_score = max(progress.get("best_score", 0), percentage)

    # A topic is considered "weak" if the best score is still below 60%
    weak_status = best_score < 60

    await db.progress.update_one(
        {"student_id": body.student_id, "topic": topic},
        {
            "$set": {
                "attempts": attempts,
                "best_score": best_score,
                "last_attempted": datetime.now(timezone.utc),
                "weak": weak_status
            }
        },
        upsert=True
    )

    # 5. Save results to Cognee memory graph
    task_date = task.get("date", datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    await remember_task_result(body.student_id, topic, percentage, task_date, struggled)
    if struggled:
        await remember_weak_topic(body.student_id, topic)

    # 5b. Mastery detection — if the student has now scored >=80% three times
    #     on this topic, write a mastery node to Cognee (replacing the weak edge).
    #     This shows the graph dynamically evolving as the student improves.
    if best_score >= 80 and attempts >= 3 and not weak_status:
        logger.info(
            "Mastery detected for student=%s topic='%s' (attempts=%d best=%d%%) — updating Cognee graph",
            body.student_id, topic, attempts, best_score
        )
        await forget_mastered_topic(body.student_id, topic)

    # 6. Generate tutor feedback using Groq (brief and encouraging)
    feedback_prompt = [
        {
            "role": "system",
            "content": (
                "You are an encouraging AI tutor. Provide brief, actionable, and friendly feedback "
                "based on the student's quiz results. Explain what they did well and what they can improve. "
                "Keep the feedback under 100 words."
            )
        },
        {
            "role": "user",
            "content": f"""
Topic: {topic}
Score: {correct_count}/{len(questions)} ({percentage}%)
Detailed results: {detailed_results}
Struggled: {struggled}
"""
        }
    ]

    try:
        feedback = await chat(feedback_prompt)
    except Exception as exc:
        logger.error("Failed to generate feedback: %s", exc)
        feedback = "Great effort! Keep practicing and reviewing this topic to master it."

    return SubmitTaskResponse(
        score=correct_count,
        total=len(questions),
        percentage=float(percentage),
        struggled=struggled,
        feedback=feedback.strip()
    )
