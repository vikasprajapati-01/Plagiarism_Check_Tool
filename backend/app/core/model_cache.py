"""
Singleton model cache — loads SBERT and GPT-2-small exactly once at startup.

Loading strategy:
  1. Try downloading from HuggingFace (online)
  2. If download fails → load from backend/checkpoints/
  3. If both fail → show clear warning, app continues with limited features
"""

import logging
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

_sbert_model: Optional[Any] = None
_gpt2_tokenizer: Optional[Any] = None
_gpt2_model: Optional[Any] = None
_load_warnings: list = []

# Checkpoint paths
_BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
_CHECKPOINT_SBERT = _BACKEND_DIR / "checkpoints" / "sbert"
_CHECKPOINT_GPT2 = _BACKEND_DIR / "checkpoints" / "gpt2"


def _has_checkpoint(path: Path) -> bool:
    return path.exists() and any(path.iterdir())


def load_models(embedding_model: str, gpt2_model: str = "gpt2") -> None:
    """Load SBERT and GPT-2 — online first, checkpoint fallback."""
    global _sbert_model, _gpt2_tokenizer, _gpt2_model

    # ── SBERT ────────────────────────────────────────────────────────────────
    try:
        from sentence_transformers import SentenceTransformer
        logger.info("Loading SBERT model: %s (online)", embedding_model)
        _sbert_model = SentenceTransformer(embedding_model)
        logger.info("SBERT loaded successfully (online).")
    except Exception:
        logger.warning("Online SBERT download failed. Trying checkpoint...")
        if _has_checkpoint(_CHECKPOINT_SBERT):
            try:
                from sentence_transformers import SentenceTransformer
                _sbert_model = SentenceTransformer(str(_CHECKPOINT_SBERT))
                logger.info("SBERT loaded successfully (checkpoint).")
            except Exception:
                _sbert_model = None
                msg = (
                    "⚠️  SBERT model failed to load from both online and checkpoint. "
                    "Semantic matching is DISABLED. Results may be incomplete. "
                    "Run: python scripts/download_models.py --no-ssl-verify"
                )
                _load_warnings.append(msg)
                logger.warning(msg)
        else:
            _sbert_model = None
            msg = (
                "⚠️  SBERT model could not be downloaded and no checkpoint found. "
                "Semantic matching is DISABLED. Results may be incomplete. "
                "Run: python scripts/download_models.py --no-ssl-verify"
            )
            _load_warnings.append(msg)
            logger.warning(msg)

    # ── GPT-2 ────────────────────────────────────────────────────────────────
    try:
        from transformers import GPT2LMHeadModel, GPT2TokenizerFast
        import torch  # noqa: F401
        logger.info("Loading GPT-2 model: %s (online)", gpt2_model)
        _gpt2_tokenizer = GPT2TokenizerFast.from_pretrained(gpt2_model)
        _gpt2_model = GPT2LMHeadModel.from_pretrained(gpt2_model)
        if getattr(_gpt2_model.config, "loss_type", None) is None:
            _gpt2_model.config.loss_type = "ForCausalLMLoss"
        _gpt2_model.eval()
        logger.info("GPT-2 loaded successfully (online).")
    except Exception:
        logger.warning("Online GPT-2 download failed. Trying checkpoint...")
        if _has_checkpoint(_CHECKPOINT_GPT2):
            try:
                from transformers import GPT2LMHeadModel, GPT2TokenizerFast
                _gpt2_tokenizer = GPT2TokenizerFast.from_pretrained(str(_CHECKPOINT_GPT2))
                _gpt2_model = GPT2LMHeadModel.from_pretrained(str(_CHECKPOINT_GPT2))
                if getattr(_gpt2_model.config, "loss_type", None) is None:
                    _gpt2_model.config.loss_type = "ForCausalLMLoss"
                _gpt2_model.eval()
                logger.info("GPT-2 loaded successfully (checkpoint).")
            except Exception:
                _gpt2_tokenizer = None
                _gpt2_model = None
                msg = (
                    "⚠️  GPT-2 model failed to load from both online and checkpoint. "
                    "AI detection is DISABLED. Results may be inaccurate. "
                    "Run: python scripts/download_models.py --no-ssl-verify"
                )
                _load_warnings.append(msg)
                logger.warning(msg)
        else:
            _gpt2_tokenizer = None
            _gpt2_model = None
            msg = (
                "⚠️  GPT-2 model could not be downloaded and no checkpoint found. "
                "AI detection is DISABLED. Results may be inaccurate. "
                "Run: python scripts/download_models.py --no-ssl-verify"
            )
            _load_warnings.append(msg)
            logger.warning(msg)

    logger.info("Model loading complete.")


# ── Accessors ─────────────────────────────────────────────────────────────────

def get_sbert_model() -> Optional[Any]:
    return _sbert_model

def get_gpt2_tokenizer() -> Optional[Any]:
    return _gpt2_tokenizer

def get_gpt2_model() -> Optional[Any]:
    return _gpt2_model

def get_load_warnings() -> list:
    """Return list of warning messages from model loading."""
    return _load_warnings
