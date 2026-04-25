"""
Application settings loaded from environment variables / .env file.

All thresholds, model names, and DB credentials live here.
Service files must import from this module — never hardcode values.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration object. Values are read from .env, then environment."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Database ──────────────────────────────────────────────────────────────
    DATABASE_URL: str = ""
    SUPABASE_URL: str = ""
    SUPABASE_ANON_KEY: str = ""
    SUPABASE_SERVICE_ROLE_KEY: str = ""

    # ── ML Models ─────────────────────────────────────────────────────────────
    EMBEDDING_MODEL: str = "all-MiniLM-L6-v2"
    AI_DETECTION_MODEL: str = "openai-community/roberta-large-openai-detector"

    # ── Detection thresholds ──────────────────────────────────────────────────
    FUZZY_THRESHOLD: float = 0.85
    SEMANTIC_THRESHOLD: float = 0.85

    # ── Web scanner ───────────────────────────────────────────────────────────
    WEB_SCAN_TIMEOUT: int = 10
    WEB_SCAN_RETRIES: int = 1
    WEB_SCAN_MAX_QUERIES: int = 1
    WEB_SCAN_MAX_RESULTS: int = 2
    WEB_SCAN_MAX_SCAN_TIME: int = 25
    WEB_SCAN_OVERALL_TIMEOUT: int = 60

    # ── Logging ───────────────────────────────────────────────────────────────
    LOG_LEVEL: str = "INFO"


# Singleton — import this everywhere instead of constructing a new Settings()
settings = Settings()
