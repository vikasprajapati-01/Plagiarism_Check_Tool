"""Word2Vec / GloVe word-level embeddings for document similarity.

Documents are embedded by averaging word vectors, then compared with cosine similarity.
Works with any gensim-compatible model (Word2Vec .bin, GloVe converted to w2v format).
Set WORD2VEC_MODEL env var to a file path or a gensim model name.
Default: 'glove-wiki-gigaword-100' (~130 MB, downloaded once via gensim).
"""

import math
import os
from functools import lru_cache
from typing import List, Optional, Sequence, Tuple

from app.services.preprocess import preprocess_text

try:
    from gensim.models import KeyedVectors
    import gensim.downloader as gensim_api
    _GENSIM_AVAILABLE = True
except ImportError:
    _GENSIM_AVAILABLE = False

_DEFAULT_MODEL = "glove-wiki-gigaword-100"


# ── Model loading ─────────────────────────────────────────────────────────────

@lru_cache(maxsize=2)
def _load_model(model_name: str) -> "KeyedVectors":
    if not _GENSIM_AVAILABLE:
        raise RuntimeError("gensim not installed. Run: pip install gensim")

    # File path on disk → load directly
    if os.path.exists(model_name):
        return KeyedVectors.load_word2vec_format(
            model_name, binary=model_name.endswith(".bin")
        )

    # Otherwise download/fetch via gensim (cached locally after first call)
    return gensim_api.load(model_name)


def get_model(model_name: Optional[str] = None) -> "KeyedVectors":
    name = model_name or os.getenv("WORD2VEC_MODEL", _DEFAULT_MODEL)
    return _load_model(name)


def is_available() -> bool:
    return _GENSIM_AVAILABLE


# ── Encoding ──────────────────────────────────────────────────────────────────

def _mean_vector(words: List[str], kv: "KeyedVectors") -> Optional[List[float]]:
    """Average of all word vectors present in vocabulary. Returns None if none found."""
    vecs = [kv[w] for w in words if w in kv]
    if not vecs:
        return None
    dim = len(vecs[0])
    avg = [sum(vecs[i][d] for i in range(len(vecs))) / len(vecs) for d in range(dim)]
    norm = math.sqrt(sum(x * x for x in avg))
    return [x / norm for x in avg] if norm > 0 else avg


def encode_text(text: str, model_name: Optional[str] = None) -> Optional[List[float]]:
    """Encode a text to a document vector. Returns None if no vocabulary overlap."""
    kv = get_model(model_name)
    words = preprocess_text(text).split()
    return _mean_vector(words, kv)


# ── Cosine similarity ─────────────────────────────────────────────────────────

def _cosine(a: List[float], b: List[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    return dot / (na * nb) if na > 0 and nb > 0 else 0.0


def similarity(
    text1: str,
    text2: str,
    model_name: Optional[str] = None,
) -> Optional[float]:
    """Cosine similarity between two texts using Word2Vec/GloVe vectors.
    Returns None if either text has no words in the model vocabulary.
    """
    v1 = encode_text(text1, model_name)
    v2 = encode_text(text2, model_name)
    if v1 is None or v2 is None:
        return None
    return round(_cosine(v1, v2), 4)


# ── Batch duplicate detection ─────────────────────────────────────────────────

def find_duplicates_in_batch(
    texts: Sequence[str],
    threshold: float = 0.85,
    model_name: Optional[str] = None,
) -> List[Tuple[int, int, float]]:
    """Find all duplicate pairs in a batch via Word2Vec/GloVe cosine similarity.

    Returns list of (index_i, index_j, score) sorted by score descending.
    Pairs where either text has no vocabulary overlap are skipped.
    """
    kv = get_model(model_name)
    vecs = [_mean_vector(preprocess_text(t).split(), kv) for t in texts]

    pairs: List[Tuple[int, int, float]] = []
    for i in range(len(texts)):
        for j in range(i + 1, len(texts)):
            if vecs[i] is None or vecs[j] is None:
                continue
            score = _cosine(vecs[i], vecs[j])
            if score >= threshold:
                pairs.append((i, j, round(score, 4)))

    pairs.sort(key=lambda x: x[2], reverse=True)
    return pairs
