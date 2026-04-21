"""AI-content detection using a RoBERTa-based HuggingFace classifier.

Logic preserved — identical to services/ai_detection.py.
Key change: functions now accept a pre-loaded pipeline instance so the model
is never loaded per-request (see core/model_cache.py).
"""

import asyncio
import logging
from functools import partial
from typing import Any, List

logger = logging.getLogger(__name__)


# ── Core detection ────────────────────────────────────────────────────────────

def detect_ai_content_sync(text: str, detector: Any) -> dict:
    """Detect whether text is AI-generated or human-written.

    The roberta-large-openai-detector model outputs:
        "Real" → Human-written
        "Fake"  → AI-generated

    Returns:
        { "label": "AI"|"Human", "confidence": float, "raw_label": "Fake"|"Real" }
    """
    if not text or not text.strip():
        return {
            "label": "Unknown",
            "confidence": 0.0,
            "raw_label": "N/A",
            "error": "Empty text provided",
        }

    result = detector(text)[0]
    raw_label: str = result["label"]
    confidence: float = round(result["score"], 4)
    label = "AI" if raw_label == "Fake" else "Human"

    return {
        "label": label,
        "confidence": confidence,
        "raw_label": raw_label,
    }


async def detect_ai_content(text: str, detector: Any) -> dict:
    """Async wrapper — runs inference in a thread pool to avoid blocking the event loop."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None,
        partial(detect_ai_content_sync, text, detector),
    )


async def detect_ai_batch(texts: List[str], detector: Any) -> List[dict]:
    """Detect AI content for a batch of texts concurrently.

    Returns a list of result dicts in the same order as input texts.
    """
    tasks = [detect_ai_content(text, detector) for text in texts]
    return await asyncio.gather(*tasks)
