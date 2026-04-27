"""AI-content detection using GPT-2-small perplexity scoring.

Why perplexity?
  AI-generated text uses high-probability, low-surprise tokens.
  GPT-2 predicts those tokens easily  →  low perplexity  →  high AI%.
  Human text is more varied/unpredictable  →  higher perplexity  →  low AI%.

This approach detects text from ANY modern LLM (GPT-4, Claude, Gemini, Llama)
because we measure the statistical signature of the text, not the source model.
GPT-2-small (117M params, ~500 MB) is used to keep the footprint small and the
system fully offline after the initial one-time download.

Perplexity → AI% mapping (inverse sigmoid):
    PPL ≈ 10  →  AI% ≈ 92   (clearly AI)
    PPL ≈ 30  →  AI% ≈ 50   (uncertain boundary)
    PPL ≈ 60  →  AI% ≈  8   (likely human)
"""

import asyncio
import logging
import math
from functools import partial
from typing import Any, List, Optional

logger = logging.getLogger(__name__)

# Sigmoid parameters — tuned for short text (<20 words).
# Increase _PIVOT if you observe too many false-positives on human text.
_PIVOT: float = 30.0       # perplexity at which we are 50 % confident it's AI
_TEMPERATURE: float = 8.0  # lower = sharper AI/Human boundary


# ── Core helpers ──────────────────────────────────────────────────────────────

def _compute_perplexity(text: str, tokenizer: Any, model: Any) -> float:
    """Compute GPT-2 per-token cross-entropy loss and return exp(loss).

    Returns 50.0 (uncertain midpoint) for empty input or texts too short
    to produce a meaningful score (< 2 tokens).
    """
    import torch

    if not text or not text.strip():
        return 50.0

    try:
        inputs = tokenizer(
            text,
            return_tensors="pt",
            truncation=True,
            max_length=512,
        )
        input_ids = inputs["input_ids"]

        if input_ids.shape[1] < 2:
            # Single token — perplexity is undefined.
            return 50.0

        with torch.no_grad():
            outputs = model(input_ids, labels=input_ids)
            # outputs.loss = mean negative log-likelihood per token
            loss: float = outputs.loss.item()

        # Clamp to avoid exp overflow on extreme losses.
        safe_loss = min(loss, 100.0)
        return math.exp(safe_loss)

    except Exception as exc:
        logger.warning("Perplexity computation failed: %s", exc)
        return 50.0  # return uncertain on any error


def _perplexity_to_ai_pct(perplexity: float) -> float:
    """Map a GPT-2 perplexity value to an AI-probability percentage (0–100).

    Formula:  AI% = 100 / (1 + exp((PPL - pivot) / temperature))
    """
    exponent_arg = (perplexity - _PIVOT) / _TEMPERATURE
    # Avoid overflow and preserve sigmoid saturation behavior.
    if exponent_arg >= 50.0:
        return 0.0
    if exponent_arg <= -50.0:
        return 100.0

    ai_prob = 1.0 / (1.0 + math.exp(exponent_arg))
    return round(ai_prob * 100.0, 1)


# ── Public API ────────────────────────────────────────────────────────────────

def detect_ai_content_sync(
    text: str,
    tokenizer: Optional[Any],
    model: Optional[Any],
) -> dict:
    """Detect whether text is AI-generated using GPT-2 perplexity.

    Returns a dict with:
        label      : "AI" | "Human" | "Unknown"
        confidence : probability for the predicted label (0.0–1.0)
        ai_pct     : AI probability as a percentage (0.0–100.0)
        perplexity : raw GPT-2 perplexity score (for debugging)

    Falls back to "Unknown" / 0.0 when GPT-2 is not loaded (graceful degradation).
    """
    if tokenizer is None or model is None:
        return {
            "label": "Unknown",
            "confidence": 0.0,
            "ai_pct": 0.0,
            "perplexity": -1.0,
            "error": "GPT-2 model not loaded",
        }

    if not text or not text.strip():
        return {
            "label": "Unknown",
            "confidence": 0.0,
            "ai_pct": 0.0,
            "perplexity": -1.0,
            "error": "Empty text provided",
        }

    perplexity = _compute_perplexity(text, tokenizer, model)
    ai_pct = _perplexity_to_ai_pct(perplexity)
    is_ai = ai_pct >= 50.0
    label = "AI" if is_ai else "Human"
    # confidence = the model's probability for the *predicted* label
    confidence = round(ai_pct / 100.0 if is_ai else (100.0 - ai_pct) / 100.0, 4)

    return {
        "label": label,
        "confidence": confidence,
        "ai_pct": ai_pct,
        "perplexity": round(perplexity, 2),
    }


async def detect_ai_content(
    text: str,
    tokenizer: Optional[Any],
    model: Optional[Any],
) -> dict:
    """Async wrapper — runs GPT-2 inference in a thread pool to avoid blocking the event loop."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None,
        partial(detect_ai_content_sync, text, tokenizer, model),
    )


async def detect_ai_batch(
    texts: List[str],
    tokenizer: Optional[Any],
    model: Optional[Any],
) -> List[dict]:
    """Detect AI content for a batch of texts concurrently."""
    tasks = [detect_ai_content(text, tokenizer, model) for text in texts]
    return await asyncio.gather(*tasks)
