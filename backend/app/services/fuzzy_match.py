"""Fuzzy string matching for near-duplicate detection.

Implements 4 algorithms:
  1. Levenshtein Distance  — character-level edits (typos, spelling)
  2. Hamming Distance      — position-based comparison (equal-length only)
  3. Jaccard Similarity    — word/token overlap (paraphrasing)
  4. N-gram Similarity     — substring patterns (structural similarity)

Logic preserved — identical to services/fuzzy.py.
Thresholds now accepted as parameters (sourced from config.py by callers).
"""

import logging
from typing import List, Optional, Set, Tuple

from app.services.preprocessor import preprocess_text

logger = logging.getLogger(__name__)


# ── Levenshtein ───────────────────────────────────────────────────────────────

def levenshtein_distance(str1: str, str2: str) -> int:
    """Minimum character edits (insert/delete/substitute) to transform str1 → str2."""
    len1, len2 = len(str1), len(str2)
    dp = [[0] * (len2 + 1) for _ in range(len1 + 1)]

    for i in range(len1 + 1):
        dp[i][0] = i
    for j in range(len2 + 1):
        dp[0][j] = j

    for i in range(1, len1 + 1):
        for j in range(1, len2 + 1):
            if str1[i - 1] == str2[j - 1]:
                dp[i][j] = dp[i - 1][j - 1]
            else:
                dp[i][j] = 1 + min(
                    dp[i - 1][j - 1],  # replace
                    dp[i][j - 1],      # insert
                    dp[i - 1][j],      # delete
                )

    return dp[len1][len2]


def levenshtein_similarity(str1: str, str2: str) -> float:
    """Normalize Levenshtein to 0.0-1.0 scale; 1.0 = identical."""
    distance = levenshtein_distance(str1, str2)
    max_len = max(len(str1), len(str2))
    return 1.0 - (distance / max_len) if max_len > 0 else 1.0


# ── Hamming ───────────────────────────────────────────────────────────────────

def hamming_distance(str1: str, str2: str) -> int:
    """Count positions where characters differ (equal-length strings only)."""
    if len(str1) != len(str2):
        raise ValueError(
            f"Hamming requires equal-length strings. Got {len(str1)} and {len(str2)}"
        )
    return sum(c1 != c2 for c1, c2 in zip(str1, str2))


def hamming_similarity(str1: str, str2: str) -> float:
    """Normalize Hamming to 0.0-1.0; returns 0.0 if lengths differ."""
    if len(str1) != len(str2) or len(str1) == 0:
        return 0.0 if len(str1) != len(str2) else 1.0
    return 1.0 - (hamming_distance(str1, str2) / len(str1))


# ── Jaccard ───────────────────────────────────────────────────────────────────

def jaccard_similarity(str1: str, str2: str, use_tokens: bool = True) -> float:
    """Set overlap: |A ∩ B| / |A ∪ B|. Order-independent, good for paraphrasing."""
    set1 = set(str1.split()) if use_tokens else set(str1)
    set2 = set(str2.split()) if use_tokens else set(str2)

    if len(set1) == 0 and len(set2) == 0:
        return 1.0
    if len(set1) == 0 or len(set2) == 0:
        return 0.0

    intersection = set1 & set2
    union = set1 | set2
    return len(intersection) / len(union)


# ── N-gram ────────────────────────────────────────────────────────────────────

def generate_ngrams(text: str, n: int = 2) -> Set[str]:
    """Generate n-grams (consecutive character sequences) from text."""
    if len(text) < n:
        return {text} if text else set()
    return {text[i:i + n] for i in range(len(text) - n + 1)}


def ngram_similarity(str1: str, str2: str, n: int = 2) -> float:
    """Dice coefficient on shared n-grams: 2 * |A ∩ B| / (|A| + |B|)."""
    ngrams1 = generate_ngrams(str1, n)
    ngrams2 = generate_ngrams(str2, n)

    if len(ngrams1) == 0 and len(ngrams2) == 0:
        return 1.0
    if len(ngrams1) == 0 or len(ngrams2) == 0:
        return 0.0

    intersection = ngrams1 & ngrams2
    return 2 * len(intersection) / (len(ngrams1) + len(ngrams2))


# ── Combined fuzzy match ──────────────────────────────────────────────────────

def fuzzy_match(
    text1: str,
    text2: str,
    preprocess: bool = True,
    levenshtein_threshold: float = 0.85,
    jaccard_threshold: float = 0.70,
    ngram_threshold: float = 0.75,
) -> Tuple[bool, dict]:
    """Comprehensive fuzzy match using all algorithms.

    Returns (is_match, scores_dict). Match fires when ANY threshold is exceeded.
    """
    if preprocess:
        processed1 = preprocess_text(text1)
        processed2 = preprocess_text(text2)
    else:
        processed1 = text1.lower().strip()
        processed2 = text2.lower().strip()

    if processed1 == processed2:
        return True, {"levenshtein": 1.0, "jaccard": 1.0, "ngram": 1.0, "is_match": True}

    if not processed1 or not processed2:
        return False, {"levenshtein": 0.0, "jaccard": 0.0, "ngram": 0.0, "is_match": False}

    lev_score = levenshtein_similarity(processed1, processed2)
    jac_score = jaccard_similarity(processed1, processed2, use_tokens=True)
    ngram_score = ngram_similarity(processed1, processed2, n=2)

    is_match = (
        lev_score >= levenshtein_threshold
        or jac_score >= jaccard_threshold
        or ngram_score >= ngram_threshold
    )

    return is_match, {
        "levenshtein": round(lev_score, 3),
        "jaccard": round(jac_score, 3),
        "ngram": round(ngram_score, 3),
        "is_match": is_match,
    }


# ── Async helper for pipeline use ─────────────────────────────────────────────

async def is_fuzzy_duplicate(
    text: str,
    candidates: List[str],
    threshold: float = 0.85,
) -> Tuple[bool, Optional[str], Optional[dict]]:
    """Check if text fuzzy-matches any candidate. Returns (is_dup, matched, scores)."""
    for candidate in candidates:
        is_match, scores = fuzzy_match(
            text,
            candidate,
            levenshtein_threshold=threshold,
            jaccard_threshold=threshold * 0.8,
            ngram_threshold=threshold * 0.9,
        )
        if is_match:
            return True, candidate, scores

    return False, None, None


# ── Batch helpers ─────────────────────────────────────────────────────────────

def find_fuzzy_duplicates_in_batch(
    texts: List[str],
    threshold: float = 0.85,
) -> List[Tuple[int, int, dict]]:
    """Find all duplicate pairs within a batch (pairwise). Returns (i, j, scores) list."""
    duplicates = []
    n = len(texts)

    for i in range(n):
        for j in range(i + 1, n):
            is_match, scores = fuzzy_match(
                texts[i],
                texts[j],
                levenshtein_threshold=threshold,
                jaccard_threshold=threshold * 0.8,
                ngram_threshold=threshold * 0.9,
            )
            if is_match:
                duplicates.append((i, j, scores))

    return duplicates


def get_best_match(
    query: str,
    candidates: List[str],
    top_k: int = 5,
) -> List[Tuple[str, dict]]:
    """Find top-k most similar candidates. Returns sorted (candidate_text, scores)."""
    matches = []

    for candidate in candidates:
        _, scores = fuzzy_match(query, candidate, preprocess=True)
        best_score = max(scores["levenshtein"], scores["jaccard"], scores["ngram"])
        matches.append((candidate, scores, best_score))

    matches.sort(key=lambda x: x[2], reverse=True)
    return [(text, scores) for text, scores, _ in matches[:top_k]]
