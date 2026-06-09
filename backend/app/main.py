"""FastAPI application entry point.

Startup lifespan:
  1. Loads SBERT and RoBERTa once and stores them on app.state.
  2. Initialises logging at the level set in config.
  3. Mounts the unified /api/v1 router.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.model_cache import load_models, get_sbert_model, get_gpt2_tokenizer, get_gpt2_model, get_load_warnings
from app.api.v1.router import api_router

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load ML models once at startup; release resources on shutdown."""
    logger.info("Starting up — loading ML models …")
    load_models(
        embedding_model=settings.EMBEDDING_MODEL,
        gpt2_model=settings.GPT2_MODEL,
    )
    # Store on app.state so any request handler can access them
    from app.core.model_cache import get_sbert_model, get_gpt2_tokenizer, get_gpt2_model
    app.state.sbert_model    = get_sbert_model()       # may be None
    app.state.gpt2_tokenizer = get_gpt2_tokenizer()    # may be None
    app.state.gpt2_model     = get_gpt2_model()        # may be None

    # Log which features are active
    features = []
    if app.state.sbert_model:
        features.append("semantic-matching")
    if app.state.gpt2_model:
        features.append("ai-detection")
    features += ["exact-match", "fuzzy-match", "cross-comparison"]  # always available

    logger.info("Startup complete. Active features: %s", ", ".join(features))
    if not app.state.sbert_model or not app.state.gpt2_model:
        logger.warning(
            "Some ML models failed to load. Run `python scripts/download_models.py` "
            "to cache models locally for offline use."
        )

    yield  # ── application is running ───────────────────────────────────────

    logger.info("Shutting down.")


# ── Application ───────────────────────────────────────────────────────────────

app = FastAPI(
    title="Plagiarism Check Tool API",
    description=(
        "Samsung PRISM — Plagiarism & Duplicate Detection for AI training datasets. "
        "Unified pipeline with exact, fuzzy, semantic, AI-detection, web-scan, "
        "and license-check methods."
    ),
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", tags=["Health"])
async def root():
    """Health-check endpoint — shows model status and any warnings."""
    warnings = get_load_warnings()
    return {
        "message": "Plagiarism Checker Backend Running",
        "version": "2.0.0",
        "models": {
            "sbert": "loaded" if app.state.sbert_model else "unavailable",
            "gpt2": "loaded" if app.state.gpt2_model else "unavailable",
        },
        "warnings": warnings if warnings else None,
    }


# Mount the single unified router under /api/v1
app.include_router(api_router, prefix="/api/v1")