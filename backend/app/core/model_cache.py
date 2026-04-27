"""
Singleton model cache — loads SBERT and GPT-2-small exactly once at startup.

SBERT      : sentence-transformers model for semantic similarity.
GPT-2-small: used for AI-content detection via perplexity scoring.

Called from the lifespan context manager in main.py.
Service functions receive models as parameters; they never load models
themselves, ensuring zero per-request overhead.
"""

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Module-level holders — populated by load_models()
_sbert_model: Optional[Any] = None
_gpt2_tokenizer: Optional[Any] = None
_gpt2_model: Optional[Any] = None


def load_models(embedding_model: str, gpt2_model: str = "gpt2") -> None:
    """Load SBERT and GPT-2-small into module-level singletons.

    Called once during the FastAPI lifespan startup event.

    - SBERT failure is fatal (raises RuntimeError).
    - GPT-2 failure is non-fatal: a warning is logged and AI detection
      degrades gracefully to 'Unknown' with 0% confidence.
    """
    global _sbert_model, _gpt2_tokenizer, _gpt2_model

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

    # ── GPT-2-small (AI detector) ─────────────────────────────────────────────
    try:
        from transformers import GPT2LMHeadModel, GPT2TokenizerFast
        import torch  # noqa: F401 — verify torch is available

        logger.info("Loading GPT-2 model: %s", gpt2_model)
        _gpt2_tokenizer = GPT2TokenizerFast.from_pretrained(gpt2_model)
        _gpt2_model = GPT2LMHeadModel.from_pretrained(gpt2_model)
        if getattr(_gpt2_model.config, "loss_type", None) is None:
            _gpt2_model.config.loss_type = "ForCausalLMLoss"
        _gpt2_model.eval()  # switch to inference mode
        logger.info("GPT-2 model loaded successfully.")
    except ImportError:
        logger.warning(
            "transformers or torch not installed — AI detection disabled. "
            "Run: pip install transformers torch"
        )
    except Exception as exc:
        logger.warning(
            "Failed to load GPT-2 model '%s': %s — AI detection disabled.",
            gpt2_model, exc,
        )

    logger.info("Model loading complete.")


# ── Accessors ─────────────────────────────────────────────────────────────────

def get_sbert_model() -> Any:
    """Return the cached SBERT model. Raises if not yet loaded."""
    if _sbert_model is None:
        raise RuntimeError("SBERT model has not been loaded. Call load_models() first.")
    return _sbert_model


def get_gpt2_tokenizer() -> Optional[Any]:
    """Return the cached GPT-2 tokenizer, or None if loading failed/skipped."""
    return _gpt2_tokenizer


def get_gpt2_model() -> Optional[Any]:
    """Return the cached GPT-2 LM model, or None if loading failed/skipped."""
    return _gpt2_model
