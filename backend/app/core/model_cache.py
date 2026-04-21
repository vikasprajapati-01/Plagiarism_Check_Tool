"""
Singleton model cache — loads SBERT and RoBERTa exactly once at startup.

Called from the lifespan context manager in main.py.
Service functions receive models as parameters; they never load models
themselves.
"""

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Module-level holders — populated by load_models()
_sbert_model: Optional[Any] = None
_ai_model: Optional[Any] = None


def load_models(embedding_model: str, ai_detection_model: str) -> None:
    """Load SBERT and RoBERTa into module-level singletons.

    Called once during the FastAPI lifespan startup event.
    Raises RuntimeError if required packages are not installed.
    """
    global _sbert_model, _ai_model

    # ── SBERT ─────────────────────────────────────────────────────────────────
    try:
        from sentence_transformers import SentenceTransformer
        logger.info("Loading SBERT model: %s", embedding_model)
        _sbert_model = SentenceTransformer(embedding_model)
        logger.info("SBERT model loaded successfully.")
    except ImportError as exc:
        raise RuntimeError(
            "sentence-transformers is not installed. Run: pip install sentence-transformers"
        ) from exc

    # ── RoBERTa AI detector ───────────────────────────────────────────────────
    try:
        from transformers import pipeline as hf_pipeline
        logger.info("Loading AI detection model: %s", ai_detection_model)
        _ai_model = hf_pipeline(
            "text-classification",
            model=ai_detection_model,
            truncation=True,
            max_length=512,
        )
        logger.info("AI detection model loaded successfully.")
    except ImportError as exc:
        raise RuntimeError(
            "transformers is not installed. Run: pip install transformers torch"
        ) from exc

    logger.info("Models loaded successfully.")


def get_sbert_model() -> Any:
    """Return the cached SBERT model. Raises if not yet loaded."""
    if _sbert_model is None:
        raise RuntimeError("SBERT model has not been loaded. Call load_models() first.")
    return _sbert_model


def get_ai_model() -> Any:
    """Return the cached RoBERTa pipeline. Raises if not yet loaded."""
    if _ai_model is None:
        raise RuntimeError("AI detection model has not been loaded. Call load_models() first.")
    return _ai_model
