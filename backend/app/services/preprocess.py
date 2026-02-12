"""Text normalization utilities for ingestion and detection pipelines."""

import re
import unicodedata
from typing import Iterable, List


# Lightweight stop word list to drop common fillers.
STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "but", "by", "for", "if", "in", "into",
    "is", "it", "no", "not", "of", "on", "or", "such", "that", "the", "their", "then",
    "there", "these", "they", "this", "to", "was", "will", "with",
}


def _normalize_unicode(text: str) -> str:
    # NFKC collapses visually similar forms (e.g., full-width) to improve matching.
    return unicodedata.normalize("NFKC", text)


def preprocess_text(text: str) -> str:
    """Normalize and lightly clean a single text snippet for duplicate checks."""
    if text is None:
        return ""

    normalized = _normalize_unicode(str(text)).lower()

    # Strip punctuation and symbols; keep alphanumerics and whitespace.
    normalized = re.sub(r"[^a-z0-9\s]", " ", normalized)

    # Collapse runs of whitespace and remove stop words.
    tokens = re.split(r"\s+", normalized.strip())
    filtered_tokens = [tok for tok in tokens if tok and tok not in STOP_WORDS]

    return " ".join(filtered_tokens)


def preprocess_texts(texts: Iterable[str]) -> List[str]:
    """Vectorized wrapper over ``preprocess_text`` preserving order."""
    return [preprocess_text(text) for text in texts]