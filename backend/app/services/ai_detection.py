"""
AI Content Detection Service
Uses roberta-base-openai-detector (HuggingFace) to classify text as
AI-generated or Human-written, with a confidence score.
"""

import asyncio
import os
from functools import lru_cache, partial
from typing import Optional, Tuple

from transformers import pipeline as hf_pipeline

_DEFAULT_MODEL = "openai-community/roberta-large-openai-detector"


# ── Model Loading ─────────────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def _load_detector(model_name: str):
    """Load and cache the HuggingFace classification pipeline."""
    if hf_pipeline is None:
        raise RuntimeError(
            "transformers might not be installed. "
            "Run: pip install transformers torch"
        )
    return hf_pipeline(
        "text-classification",
        model=model_name,
        truncation=True,
        max_length=512,
    )


def get_detector(model_name: Optional[str] = None):
    """Return cached detector. Falls back to env var, then default model."""
    name = model_name or os.getenv("AI_DETECTION_MODEL", _DEFAULT_MODEL)
    return _load_detector(name)


def is_available() -> bool:
    return True


# ── Core Detection ────────────────────────────────────────────────────────────

def detect_ai_content_sync(
    text: str,
    model_name: Optional[str] = None,
) -> dict:
    """
    Detect whether the given text is AI-generated or Human-written.

    The roberta-base-openai-detector model outputs:
        "Real"  → Human-written
        "Fake"  → AI-generated

    Args:
        text: The input text to analyse.
        model_name: Override the default model (optional).

    Returns:
        {
            "label":      "AI" | "Human",
            "confidence": float between 0.0 and 1.0,
            "raw_label":  "Fake" | "Real"  (original model output)
        }
    """
    if not text or not text.strip():
        return {
            "label": "Unknown",
            "confidence": 0.0,
            "raw_label": "N/A",
            "error": "Empty text provided",
        }

    detector = get_detector(model_name)
    result = detector(text)[0]

    raw_label: str = result["label"]      # "Real" = Human | "Fake" = AI
    confidence: float = round(result["score"], 4)

    # Map model labels → user-friendly labels
    label = "AI" if raw_label == "Fake" else "Human"

    return {
        "label": label,
        "confidence": confidence,
        "raw_label": raw_label,
    }


async def detect_ai_content(
    text: str,
    model_name: Optional[str] = None,
) -> dict:
    """
    Async wrapper around detect_ai_content_sync.
    Runs inference in a thread pool so it doesn't block the event loop.
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None,
        partial(detect_ai_content_sync, text, model_name),
    )


async def detect_ai_batch(
    texts: list[str],
    model_name: Optional[str] = None,
) -> list[dict]:
    """
    Detect AI content for a batch of texts.
    Runs all inferences concurrently.

    Returns a list of result dicts in the same order as input texts.
    """
    tasks = [detect_ai_content(text, model_name) for text in texts]
    return await asyncio.gather(*tasks)
