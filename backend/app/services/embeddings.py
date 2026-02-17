"""
Embedding-based Semantic Similarity Service

Provides reusable functions for generating text embeddings and computing
semantic similarity using SentenceTransformers.

Functions:
    get_model        – Load & cache a SentenceTransformer model
    encode_text      – Encode a single text into a normalized vector
    encode_texts     – Encode a batch of texts into normalized vectors
    cosine_similarity – Compute cosine similarity between two vectors
    find_semantic_matches  – Rank candidates by similarity to a query
    is_semantic_duplicate  – High-level duplicate check (encode + compare)

Usage:
    from app.services.embeddings import encode_text, cosine_similarity

    vec_a = encode_text("Samsung Galaxy S23")
    vec_b = encode_text("Samsung Galxy S23")
    score = cosine_similarity(vec_a, vec_b)
    # → ~0.97 (very similar)
"""

import math
import os
from functools import lru_cache
from typing import List, Optional, Sequence, Tuple

from app.services.preprocess import preprocess_text

# Lazy import – SentenceTransformers is an optional heavy dependency.
try:
    from sentence_transformers import SentenceTransformer
except ImportError:
    SentenceTransformer = None

_DEFAULT_MODEL = "all-MiniLM-L6-v2"


# ==============================================================================
# MODEL LOADING
# ==============================================================================

@lru_cache(maxsize=1)
def get_model(model_name: Optional[str] = None) -> "SentenceTransformer":
    """
    Load and cache a SentenceTransformer model (singleton pattern via lru_cache).

    Args:
        model_name: HuggingFace model identifier.
                    Falls back to the EMBEDDING_MODEL env var, then to
                    'all-MiniLM-L6-v2'.

    Returns:
        A ready-to-use SentenceTransformer instance.

    Raises:
        RuntimeError: If the sentence-transformers package is not installed.

    Example:
        model = get_model()                      # default model
        model = get_model("paraphrase-MiniLM-L3-v2")  # custom model
    """
    if SentenceTransformer is None:
        raise RuntimeError(
            "sentence-transformers is not installed. "
            "Run: pip install sentence-transformers"
        )
    name = model_name or os.getenv("EMBEDDING_MODEL", _DEFAULT_MODEL)
    return SentenceTransformer(name)


def is_available() -> bool:
    """Check whether the sentence-transformers library is installed."""
    return SentenceTransformer is not None


# ==============================================================================
# ENCODING – Convert text(s) to embedding vectors
# ==============================================================================

def encode_text(
    text: str,
    model_name: Optional[str] = None,
    preprocess: bool = True,
) -> List[float]:
    """
    Encode a **single** text string into a normalized embedding vector.

    Args:
        text: Raw text to encode.
        model_name: Optional model override.
        preprocess: If True, clean the text with preprocess_text() first.

    Returns:
        A list of floats representing the embedding (e.g. 384-dim for
        all-MiniLM-L6-v2).

    Example:
        vec = encode_text("Samsung Galaxy S23")
        print(len(vec))  # 384
    """
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
    """
    Encode a **batch** of texts into normalized embedding vectors.

    More efficient than calling encode_text() in a loop because the model
    processes the entire batch in one forward pass.

    Args:
        texts: List of raw text strings.
        model_name: Optional model override.
        preprocess: If True, clean each text with preprocess_text() first.

    Returns:
        A list of embedding vectors (one per input text).

    Example:
        vecs = encode_texts(["hello world", "hi there"])
        print(len(vecs), len(vecs[0]))  # 2, 384
    """
    model = get_model(model_name)
    cleaned = [preprocess_text(t) for t in texts] if preprocess else list(texts)
    embeddings = model.encode(
        cleaned,
        convert_to_numpy=True,
        normalize_embeddings=True,
    )
    return embeddings.tolist()


# ==============================================================================
# COSINE SIMILARITY – Pure math, no ML dependency
# ==============================================================================

def cosine_similarity(vec_a: Sequence[float], vec_b: Sequence[float]) -> float:
    """
    Compute the cosine similarity between two vectors.

    Returns a value in [-1.0, 1.0]:
        1.0  = identical direction (semantically identical)
        0.0  = orthogonal (unrelated)
       -1.0  = opposite direction

    For normalized vectors (as produced by encode_text), this is equivalent
    to the dot product.

    Args:
        vec_a: First embedding vector.
        vec_b: Second embedding vector.

    Returns:
        Cosine similarity score (float).

    Example:
        score = cosine_similarity([1, 0], [0, 1])  # 0.0
        score = cosine_similarity([1, 0], [1, 0])  # 1.0
    """
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


# ==============================================================================
# SEMANTIC MATCHING – Find similar texts by embedding distance
# ==============================================================================

def find_semantic_matches(
    query_vec: Sequence[float],
    candidate_vecs: Sequence[Sequence[float]],
    candidate_labels: Optional[Sequence[str]] = None,
    top_k: int = 5,
    threshold: float = 0.75,
) -> List[Tuple[int, float, Optional[str]]]:
    """
    Rank candidates by cosine similarity to a query vector.

    Args:
        query_vec: The query embedding vector.
        candidate_vecs: List of candidate embedding vectors.
        candidate_labels: Optional text labels for each candidate.
        top_k: Maximum number of results to return.
        threshold: Minimum similarity score to include.

    Returns:
        Sorted list of (candidate_index, similarity_score, label)
        in descending order of similarity.

    Example:
        matches = find_semantic_matches(
            query_vec=encode_text("quick brown fox"),
            candidate_vecs=[
                encode_text("fast brown fox"),
                encode_text("python programming"),
            ],
            candidate_labels=["fast brown fox", "python programming"],
        )
        # → [(0, 0.92, "fast brown fox")]
    """
    results: List[Tuple[int, float, Optional[str]]] = []

    for idx, candidate_vec in enumerate(candidate_vecs):
        score = cosine_similarity(query_vec, candidate_vec)
        if score >= threshold:
            label = candidate_labels[idx] if candidate_labels else None
            results.append((idx, round(score, 4), label))

    # Sort by score descending, take top_k
    results.sort(key=lambda x: x[1], reverse=True)
    return results[:top_k]


# ==============================================================================
# HIGH-LEVEL DUPLICATE DETECTION – Encode + compare in one call
# ==============================================================================

async def is_semantic_duplicate(
    text: str,
    candidate_texts: Sequence[str],
    threshold: float = 0.85,
    model_name: Optional[str] = None,
) -> Tuple[bool, Optional[str], Optional[float]]:
    """
    Check whether a text is a semantic duplicate of any candidate.

    This is the main entry point for the detection API — analogous to
    is_fuzzy_duplicate() in fuzzy.py but uses embedding similarity
    instead of string-matching algorithms.

    Args:
        text: The text to check.
        candidate_texts: Existing texts to compare against.
        threshold: Minimum cosine similarity to flag as duplicate (0.0–1.0).
        model_name: Optional model override.

    Returns:
        (is_duplicate, matched_text, similarity_score)

    Example:
        is_dup, matched, score = await is_semantic_duplicate(
            "Samsung Galaxy S23 Ultra",
            ["Samsung Galxy S23 Ultra", "iPhone 15 Pro"]
        )
        # → (True, "Samsung Galxy S23 Ultra", 0.97)
    """
    if not candidate_texts:
        return False, None, None

    # Encode all texts in one efficient batch
    all_texts = [text] + list(candidate_texts)
    all_vecs = encode_texts(all_texts, model_name=model_name, preprocess=True)

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


# ==============================================================================
# DEMO & TESTING
# ==============================================================================

if __name__ == "__main__":
    print("=" * 70)
    print("EMBEDDING SIMILARITY DEMO")
    print("=" * 70)

    if not is_available():
        print("\n⚠ sentence-transformers is not installed.")
        print("  Run: pip install sentence-transformers")
        exit(1)

    # Test 1: Model loading
    print("\n1. MODEL LOADING")
    model = get_model()
    print(f"   Model loaded: {_DEFAULT_MODEL}")

    # Test 2: Single encoding
    print("\n2. SINGLE TEXT ENCODING")
    vec = encode_text("Samsung Galaxy S23 Ultra")
    print(f"   Vector dimension: {len(vec)}")
    print(f"   First 5 values: {vec[:5]}")

    # Test 3: Batch encoding
    print("\n3. BATCH ENCODING")
    texts = ["Samsung Galaxy S23", "iPhone 15 Pro", "Samsung Galxy S23"]
    vecs = encode_texts(texts)
    print(f"   Encoded {len(vecs)} texts, dim={len(vecs[0])}")

    # Test 4: Cosine similarity
    print("\n4. COSINE SIMILARITY")
    sim_similar = cosine_similarity(vecs[0], vecs[2])  # Samsung typo
    sim_different = cosine_similarity(vecs[0], vecs[1])  # Samsung vs iPhone
    print(f"   'Samsung Galaxy S23' vs 'Samsung Galxy S23': {sim_similar:.4f}")
    print(f"   'Samsung Galaxy S23' vs 'iPhone 15 Pro':     {sim_different:.4f}")

    # Test 5: Find semantic matches
    print("\n5. FIND SEMANTIC MATCHES")
    query = encode_text("Galaxy phone by Samsung")
    matches = find_semantic_matches(
        query_vec=query,
        candidate_vecs=vecs,
        candidate_labels=texts,
        top_k=3,
        threshold=0.5,
    )
    for idx, score, label in matches:
        print(f"   #{idx} score={score:.4f}  '{label}'")

    # Test 6: Semantic duplicate check
    print("\n6. SEMANTIC DUPLICATE DETECTION")
    import asyncio

    async def _demo_dup():
        is_dup, matched, score = await is_semantic_duplicate(
            "Samsung Galaxy S23 Ultra phone",
            ["Samsung Galaxy S23 Ultra", "iPhone 15 Pro", "Google Pixel 8"],
            threshold=0.85,
        )
        print(f"   Is duplicate: {is_dup}")
        print(f"   Matched text: {matched}")
        print(f"   Score: {score}")

    asyncio.run(_demo_dup())

    print("\n" + "=" * 70)
    print("All demos completed successfully!")
    print("=" * 70)
