"""
core/config.py
──────────────
Centralised settings loaded from the .env file via pydantic-settings.
Import `settings` everywhere — never read os.environ directly.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── LLM ──────────────────────────────────────────────
    GROQ_API_KEY: str
    LLM_MODEL: str = "llama-3.3-70b-versatile"   # override in .env to swap models

    # ── MongoDB ──────────────────────────────────────────
    MONGODB_URI: str = "mongodb://localhost:27017/trackmind"
    DB_NAME: str = "trackmind"

    # ── JWT ──────────────────────────────────────────────
    JWT_SECRET: str
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_DAYS: int = 7

    # ── Cognee ───────────────────────────────────────────
    COGNEE_API_KEY: str = ""            # empty → local Cognee
    COGNEE_SERVICE_URL: str = ""        # remote tenant URL (e.g. https://your-tenant.cognee.ai)

    # ── App ──────────────────────────────────────────────
    APP_TITLE: str = "TrackMind API"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = Field(default=False)


# Singleton — import this everywhere
settings = Settings()
