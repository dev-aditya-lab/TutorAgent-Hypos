"""
models/schemas.py
─────────────────
Pydantic v2 request/response schemas for all TrackMind endpoints.
Populated progressively across Steps 2-7.
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, EmailStr, Field, field_validator


# ─────────────────────────────────────────────────────────────────────────────
# Auth
# ─────────────────────────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    email: EmailStr
    password: str = Field(..., min_length=8, description="Minimum 8 characters")
    year: Literal["1st", "2nd", "3rd", "4th"]
    goal: Literal["FAANG", "Startup", "MS Abroad", "Govt", "Freelance"]
    target_role: str = Field(..., min_length=1, max_length=100)
    current_skills: List[str] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def strip_name(cls, v: str) -> str:
        return v.strip()


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=1)


class TokenResponse(BaseModel):
    token: str
    token_type: str = "bearer"


class MeResponse(BaseModel):
    """Response for GET /auth/me — decoded from JWT, no DB call."""
    student_id: str
    email: str
    name: str


# ─────────────────────────────────────────────────────────────────────────────
# Roadmap
# ─────────────────────────────────────────────────────────────────────────────

class WeekPlan(BaseModel):
    week: int
    focus: str
    topics: List[str]


class RoadmapGenerateRequest(BaseModel):
    student_id: str


class RoadmapResponse(BaseModel):
    student_id: str
    weeks: List[WeekPlan]
    generated_at: datetime


# ─────────────────────────────────────────────────────────────────────────────
# Daily Tasks
# ─────────────────────────────────────────────────────────────────────────────

class MCQQuestion(BaseModel):
    question: str
    options: List[str]          # 4 options
    correct_index: int


class TaskResource(BaseModel):
    title: str
    content: str                # ~300 word explanation


class DailyTaskResponse(BaseModel):
    task_id: str
    student_id: str
    date: str
    topic: str
    resource: TaskResource
    questions: List[MCQQuestion]
    submitted: bool
    score: Optional[int] = None


class SubmitTaskRequest(BaseModel):
    student_id: str
    task_id: str
    answers: List[int]          # index of chosen option per question


class SubmitTaskResponse(BaseModel):
    score: int
    total: int
    percentage: float
    struggled: bool             # True if percentage < 60
    feedback: str


# ─────────────────────────────────────────────────────────────────────────────
# Interview
# ─────────────────────────────────────────────────────────────────────────────

class InterviewStartRequest(BaseModel):
    student_id: str


class InterviewStartResponse(BaseModel):
    session_id: str
    first_question: str
    question_number: int = 1


class InterviewRespondRequest(BaseModel):
    session_id: str
    student_id: str
    answer: str


class InterviewRespondResponse(BaseModel):
    question: Optional[str] = None
    question_number: int
    done: bool


class InterviewEndRequest(BaseModel):
    session_id: str
    student_id: str


class PerQuestionEval(BaseModel):
    question: str
    verdict: str
    score: int


class InterviewEvaluation(BaseModel):
    score: int
    strong_topics: List[str]
    weak_topics: List[str]
    feedback: str
    per_question: List[PerQuestionEval]


# ─────────────────────────────────────────────────────────────────────────────
# Progress
# ─────────────────────────────────────────────────────────────────────────────

class TopicProgress(BaseModel):
    topic: str
    attempts: int
    best_score: int
    last_attempted: Optional[datetime] = None
    weak: bool


class MemorySummary(BaseModel):
    """
    Structured breakdown of the Cognee graph-RAG narrative.
    Each section is parsed from the LLM-generated text; missing sections are None.
    """
    student_profile:    Optional[str] = None   # goals, background, year
    roadmap_overview:   Optional[str] = None   # 12-week plan summary
    topics_mastered:    Optional[str] = None   # topics the student has conquered
    topics_to_revise:   Optional[str] = None   # weak areas needing work
    quiz_trends:        Optional[str] = None   # quiz performance patterns
    interview_summary:  Optional[str] = None   # mock interview scores & feedback
    narrative:          Optional[str] = None   # overall AI summary paragraph
    raw:                str = ""               # full cleaned text (fallback)


class ProgressResponse(BaseModel):
    student_id: str
    topics: List[TopicProgress]
    memory: MemorySummary
