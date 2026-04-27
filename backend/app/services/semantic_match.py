"""Semantic similarity using SentenceTransformers (SBERT).

Logic preserved — identical to services/embeddings.py.
Key change: encode functions now accept a pre-loaded model instance so the
model is never loaded per-request (see core/model_cache.py).
"""

import asyncio
import logging
import math
from functools import partial
from typing import Any, List, Optional, Sequence, Tuple

from app.services.preprocessor import preprocess_text

logger = logging.getLogger(__name__)


# ── Encoding ──────────────────────────────────────────────────────────────────

def encode_text(text: str, model: Any, do_preprocess: bool = True) -> List[float]:
    """Encode a single text into a normalised embedding vector."""
    cleaned = preprocess_text(text) if do_preprocess else text
    embedding = model.encode(cleaned, convert_to_numpy=True, normalize_embeddings=True)
    return embedding.tolist()


def encode_texts(
    texts: Sequence[str],
    model: Any,
    do_preprocess: bool = True,
) -> List[List[float]]:
    """Encode a batch of texts in one forward pass."""
    cleaned = [preprocess_text(t) for t in texts] if do_preprocess else list(texts)
    embeddings = model.encode(cleaned, convert_to_numpy=True, normalize_embeddings=True)
    return embeddings.tolist()


# ── Cosine similarity ─────────────────────────────────────────────────────────

def cosine_similarity(vec_a: Sequence[float], vec_b: Sequence[float]) -> float:
    """Cosine similarity in [-1.0, 1.0]; 1.0 = identical, 0.0 = unrelated."""
    if len(vec_a) != len(vec_b):
        raise ValueError(
            f"Vectors must have the same dimension. Got {len(vec_a)} and {len(vec_b)}"
        )

    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))

    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0

    return dot / (norm_a * norm_b)


# ── Semantic match helpers ────────────────────────────────────────────────────

def find_semantic_matches(
    query_vec: Sequence[float],
    candidate_vecs: Sequence[Sequence[float]],
    candidate_labels: Optional[Sequence[str]] = None,
    top_k: int = 5,
    threshold: float = 0.75,
) -> List[Tuple[int, float, Optional[str]]]:
    """Rank candidates by similarity to a query vector.

    Returns top_k results above threshold as (index, score, label).
    """
    results: List[Tuple[int, float, Optional[str]]] = []

    for idx, candidate_vec in enumerate(candidate_vecs):
        score = cosine_similarity(query_vec, candidate_vec)
        if score >= threshold:
            label = candidate_labels[idx] if candidate_labels else None
            results.append((idx, round(score, 4), label))

    results.sort(key=lambda x: x[1], reverse=True)
    return results[:top_k]


def find_semantic_duplicates_in_batch(
    texts: Sequence[str],
    model: Any,
    threshold: float = 0.85,
) -> List[Tuple[int, int, float]]:
    """Find all semantic duplicate pairs within a batch.

    Encodes every text in one forward pass, then computes pairwise cosine
    similarity and returns pairs above the threshold, sorted by score desc.
    """
    if len(texts) < 2:
        return []

    all_vecs = encode_texts(texts, model=model, do_preprocess=True)
    duplicates: List[Tuple[int, int, float]] = []
    n = len(texts)

    for i in range(n):
        for j in range(i + 1, n):
            score = cosine_similarity(all_vecs[i], all_vecs[j])
            if score >= threshold:
                duplicates.append((i, j, round(score, 4)))

    duplicates.sort(key=lambda x: x[2], reverse=True)
    return duplicates


async def is_semantic_duplicate(
    text: str,
    candidate_texts: Sequence[str],
    model: Any,
    threshold: float = 0.85,
) -> Tuple[bool, Optional[str], Optional[float]]:
    """Check if text is a semantic duplicate of any candidate (async).

    Returns (is_duplicate, matched_text, similarity_score).
    Encoding runs in a thread pool to avoid blocking the event loop.
    """
    if not candidate_texts:
        return False, None, None

    all_texts = [text] + list(candidate_texts)
    loop = asyncio.get_running_loop()
    all_vecs = await loop.run_in_executor(
        None,
        partial(encode_texts, all_texts, model, True),
    )

    query_vec = all_vecs[0]
    candidate_vecs = all_vecs[1:]

    best_score = -1.0
    best_match: Optional[str] = None

    for idx, candidate_vec in enumerate(candidate_vecs):
        score = cosine_similarity(query_vec, candidate_vec)
        if score > best_score:
            best_score = score
            best_match = candidate_texts[idx]

    if best_score >= threshold:
        return True, best_match, round(best_score, 4)

    return False, None, round(best_score, 4) if best_score > 0 else None
