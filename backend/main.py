"""
main.py
───────
TrackMind FastAPI application entry point.

Start the server:
    uvicorn main:app --reload --host 0.0.0.0 --port 8000
"""

from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from core.config import settings
from db.mongo import connect_to_mongo, close_mongo_connection

# ── Routers ──────────────────────────────────────────────────────────────────
from routers.auth import router as auth_router
from routers.roadmap import router as roadmap_router
from routers.tasks import router as tasks_router
from routers.interview import router as interview_router
from routers.progress import router as progress_router

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


# ── Lifespan (startup / shutdown) ────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Replaces the old @app.on_event("startup") / @app.on_event("shutdown").
    Runs startup logic before `yield`, shutdown logic after.
    """
    # ── Startup ──────────────────────────────────────────────────────────────
    logger.info("🚀  TrackMind API starting up…")

    # 1. MongoDB
    await connect_to_mongo()

    # 2. Cognee — configure LLM backend (Groq) + local vector store
    from services.cognee_service import init_cognee, seed_cs_ontology
    await init_cognee()

    # 3. Seed shared CS topic ontology graph (prerequisites/relationships)
    #    This runs once and is used by all agents to enrich quiz generation
    #    with topic dependency context via cognee.recall(ontology_dataset).
    await seed_cs_ontology()

    logger.info("✅  All services ready — accepting requests")
    yield

    # ── Shutdown ─────────────────────────────────────────────────────────────
    logger.info("🛑  TrackMind API shutting down…")
    await close_mongo_connection()
    logger.info("👋  Shutdown complete")


# ── App factory ──────────────────────────────────────────────────────────────
app = FastAPI(
    title=settings.APP_TITLE,
    version=settings.APP_VERSION,
    description=(
        "TrackMind — Personalized AI Learning Companion for college students. "
        "Powered by LangGraph · Cognee · Groq · MongoDB."
    ),
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# ── CORS ─────────────────────────────────────────────────────────────────────
# Tighten `allow_origins` before going to production.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Router registration ───────────────────────────────────────────────────────
app.include_router(auth_router)
app.include_router(roadmap_router)
app.include_router(tasks_router)
app.include_router(interview_router)
app.include_router(progress_router)


# ── Health check ─────────────────────────────────────────────────────────────
@app.get("/", tags=["Health"])
async def root():
    return {
        "service": settings.APP_TITLE,
        "version": settings.APP_VERSION,
        "status": "running",
    }


@app.get("/health", tags=["Health"])
async def health():
    """
    Lightweight liveness probe.
    Does NOT hit the database — use /health/db for a readiness probe.
    """
    return JSONResponse(content={"status": "ok"})


@app.get("/health/db", tags=["Health"])
async def health_db():
    """
    Readiness probe — pings MongoDB to confirm the connection is alive.
    """
    from db.mongo import client

    try:
        await client.admin.command("ping")
        return JSONResponse(content={"status": "ok", "db": "connected"})
    except Exception as exc:
        logger.error("DB health check failed: %s", exc)
        return JSONResponse(
            status_code=503,
            content={"status": "error", "db": "unreachable", "detail": str(exc)},
        )
