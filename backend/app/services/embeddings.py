"""
Semantic similarity service using SentenceTransformers.
Handles model loading, text encoding, and duplicate detection.
"""

import asyncio
import math
import os
from functools import lru_cache, partial
from typing import List, Optional, Sequence, Tuple

from app.services.preprocess import preprocess_text

try:
    from sentence_transformers import SentenceTransformer
except ImportError:
    SentenceTransformer = None

_DEFAULT_MODEL = "all-MiniLM-L6-v2"


# ── Model Loading ─────────────────────────────────────────────────────────────

@lru_cache(maxsize=4)
def _load_model(name: str) -> "SentenceTransformer":
    # Cached by resolved name so the model is never loaded twice.
    if SentenceTransformer is None:
        raise RuntimeError(
            "sentence-transformers is not installed. "
            "Run: pip install sentence-transformers"
        )
    return SentenceTransformer(name)


def get_model(model_name: Optional[str] = None) -> "SentenceTransformer":
    """Returns a cached SentenceTransformer model.
    Falls back to EMBEDDING_MODEL env var, then 'all-MiniLM-L6-v2'."""
    name = model_name or os.getenv("EMBEDDING_MODEL", _DEFAULT_MODEL)
    return _load_model(name)


def is_available() -> bool:
    """Returns True if sentence-transformers is installed."""
    return SentenceTransformer is not None


# ── Encoding ──────────────────────────────────────────────────────────────────

def encode_text(
    text: str,
    model_name: Optional[str] = None,
    preprocess: bool = True,
) -> List[float]:
    """Encodes a single text into a normalized embedding vector."""
    model = get_model(model_name)
    cleaned = preprocess_text(text) if preprocess else text
    embedding = model.encode(
        cleaned,
        convert_to_numpy=True,
        normalize_embeddings=True,
    )
    return embedding.tolist()


def encode_texts(
    texts: Sequence[str],
    model_name: Optional[str] = None,
    preprocess: bool = True,
) -> List[List[float]]:
    """Encodes a batch of texts in one forward pass. More efficient than looping encode_text."""
    model = get_model(model_name)
    cleaned = [preprocess_text(t) for t in texts] if preprocess else list(texts)
    embeddings = model.encode(
        cleaned,
        convert_to_numpy=True,
        normalize_embeddings=True,
    )
    return embeddings.tolist()


# ── Cosine Similarity ─────────────────────────────────────────────────────────

def cosine_similarity(vec_a: Sequence[float], vec_b: Sequence[float]) -> float:
    """Returns cosine similarity between two vectors in [-1.0, 1.0].
    1.0 = identical, 0.0 = unrelated, -1.0 = opposite."""
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


# ── Semantic Matching ─────────────────────────────────────────────────────────

def find_semantic_matches(
    query_vec: Sequence[float],
    candidate_vecs: Sequence[Sequence[float]],
    candidate_labels: Optional[Sequence[str]] = None,
    top_k: int = 5,
    threshold: float = 0.75,
) -> List[Tuple[int, float, Optional[str]]]:
    """Ranks candidates by similarity to a query vector.
    Returns top_k results above threshold as (index, score, label)."""
    results: List[Tuple[int, float, Optional[str]]] = []

    for idx, candidate_vec in enumerate(candidate_vecs):
        score = cosine_similarity(query_vec, candidate_vec)
        if score >= threshold:
            label = candidate_labels[idx] if candidate_labels else None
            results.append((idx, round(score, 4), label))

    results.sort(key=lambda x: x[1], reverse=True)
    return results[:top_k]


# ── Duplicate Detection ───────────────────────────────────────────────────────

async def is_semantic_duplicate(
    text: str,
    candidate_texts: Sequence[str],
    threshold: float = 0.85,
    model_name: Optional[str] = None,
) -> Tuple[bool, Optional[str], Optional[float]]:
    """Checks if a text is a semantic duplicate of any candidate.
    Returns (is_duplicate, matched_text, similarity_score)."""
    if not candidate_texts:
        return False, None, None

    # Encode everything in a thread pool to avoid blocking the event loop.
    all_texts = [text] + list(candidate_texts)
    loop = asyncio.get_event_loop()
    all_vecs = await loop.run_in_executor(
        None,
        partial(encode_texts, all_texts, model_name=model_name, preprocess=True),
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


# ── Quick Demo ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("EMBEDDING SIMILARITY DEMO")

    if not is_available():
        print("\n⚠ sentence-transformers is not installed.")
        print("  Run: pip install sentence-transformers")
        exit(1)

    print("\n1. Model loading")
    model = get_model()
    print(f"   Loaded: {_DEFAULT_MODEL}")

    print("\n2. Single encoding")
    vec = encode_text("Samsung Galaxy S23 Ultra")
    print(f"   Dim: {len(vec)}, first 5: {vec[:5]}")

    print("\n3. Batch encoding")
    texts = ["Samsung Galaxy S23", "iPhone 15 Pro", "Samsung Galxy S23"]
    vecs = encode_texts(texts)
    print(f"   {len(vecs)} texts encoded, dim={len(vecs[0])}")

    print("\n4. Cosine similarity")
    print(f"   Samsung vs typo:  {cosine_similarity(vecs[0], vecs[2]):.4f}")
    print(f"   Samsung vs iPhone: {cosine_similarity(vecs[0], vecs[1]):.4f}")

    print("\n5. Semantic matches")
    query = encode_text("Galaxy phone by Samsung")
    matches = find_semantic_matches(query, vecs, texts, top_k=3, threshold=0.5)
    for idx, score, label in matches:
        print(f"   #{idx} {score:.4f}  '{label}'")

    print("\n6. Duplicate detection")

    async def _demo():
        is_dup, matched, score = await is_semantic_duplicate(
            "Samsung Galaxy S23 Ultra phone",
            ["Samsung Galaxy S23 Ultra", "iPhone 15 Pro", "Google Pixel 8"],
            threshold=0.85,
        )
        print(f"   Duplicate: {is_dup}, match: '{matched}', score: {score}")

    asyncio.run(_demo())
