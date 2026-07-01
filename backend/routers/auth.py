"""
routers/auth.py
───────────────
POST /auth/register  — create a new student account
POST /auth/login     — verify credentials, return JWT access token
"""

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, status, Depends
from pymongo.errors import DuplicateKeyError

from db.mongo import get_db
from models.schemas import LoginRequest, MeResponse, RegisterRequest, TokenResponse
from utils.auth import CurrentUser, create_access_token, get_current_user, hash_password, verify_password
from services.cognee_service import remember_onboarding

router = APIRouter(prefix="/auth", tags=["Auth"])


# ── Register ──────────────────────────────────────────────────────────────────

@router.post(
    "/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new student account",
)
async def register(body: RegisterRequest):
    """
    Create a student account and return a JWT access token immediately
    so the client does not need a separate login call after sign-up.

    Payload:
        name, email, password, year, goal, target_role, current_skills
    """
    db = get_db()

    # ── Build the document ────────────────────────────────────────────────────
    student_doc = {
        "name": body.name,
        "email": body.email.lower().strip(),
        "password_hash": hash_password(body.password),
        "year": body.year,
        "goal": body.goal,
        "target_role": body.target_role,
        "current_skills": body.current_skills,
        "created_at": datetime.now(timezone.utc),
    }

    # ── Persist (unique index on email catches duplicates) ────────────────────
    try:
        result = await db.students.insert_one(student_doc)
    except DuplicateKeyError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        )

    student_id = str(result.inserted_id)

    # ── Save onboarding details to Cognee memory graph ────────────────────────
    try:
        await remember_onboarding(
            student_id=student_id,
            name=body.name,
            year=body.year,
            goal=body.goal,
            skills=body.current_skills
        )
    except Exception as exc:
        # Cognee errors should never block user registration
        logger.error("Failed to remember onboarding in Cognee: %s", exc)

    # ── Issue token ───────────────────────────────────────────────────────────
    token = create_access_token(
        student_id=student_id,
        email=student_doc["email"],
        name=body.name,
    )
    return TokenResponse(token=token)


# ── Login ─────────────────────────────────────────────────────────────────────

@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Login and receive a JWT access token",
)
async def login(body: LoginRequest):
    """
    Verify email + password and return a JWT access token.

    Payload:
        email, password
    """
    db = get_db()

    # ── Look up student ───────────────────────────────────────────────────────
    student = await db.students.find_one({"email": body.email.lower().strip()})

    # Use the same error for "not found" and "wrong password" to
    # prevent email enumeration attacks.
    _auth_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid email or password.",
    )

    if student is None:
        raise _auth_error

    if not verify_password(body.password, student["password_hash"]):
        raise _auth_error

    # ── Issue token ───────────────────────────────────────────────────────────
    token = create_access_token(
        student_id=str(student["_id"]),
        email=student["email"],
        name=student["name"],
    )
    return TokenResponse(token=token)


# ── Me (token introspection) ──────────────────────────────────────────────────

@router.get(
    "/me",
    response_model=MeResponse,
    summary="Return the currently authenticated student's identity",
)
async def me(user: CurrentUser = Depends(get_current_user)):
    """
    Protected endpoint — requires a valid Bearer token.
    Returns identity decoded from the JWT (no database call needed).
    """
    return MeResponse(
        student_id=user.student_id,
        email=user.email,
        name=user.name,
    )
