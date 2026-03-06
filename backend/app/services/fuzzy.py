"""
Fuzzy String Matching for Near-Duplicate Detection

Implements 4 algorithms to detect similar (but not identical) texts:
1. Levenshtein Distance - character-level edits (typos, spelling)
2. Hamming Distance - position-based comparison (equal-length only)
3. Jaccard Similarity - word/token overlap (paraphrasing)
4. N-gram Similarity - substring patterns (structural similarity)

Usage:
    from app.services.fuzzy import fuzzy_match
    
    is_match, scores = fuzzy_match("Samsung Galaxy", "Samsung Galxy")
    # Returns: (True, {'levenshtein': 0.93, 'jaccard': 1.0, 'ngram': 0.95})
"""

from typing import List, Set, Tuple, Optional
from app.services.preprocess import preprocess_text


# ==============================================================================
# LEVENSHTEIN DISTANCE - Minimum edits to transform str1 → str2
# ==============================================================================

def levenshtein_distance(str1: str, str2: str) -> int:
    """
    Calculate minimum character edits (insert/delete/substitute) needed.
    
    Example: "kitten" → "sitting" = 3 edits
    Uses dynamic programming: dp[i][j] = distance between str1[:i] and str2[:j]
    """
    len1, len2 = len(str1), len(str2)
    dp = [[0] * (len2 + 1) for _ in range(len1 + 1)]
    
    # Base cases: empty string transformations
    for i in range(len1 + 1):
        dp[i][0] = i
    for j in range(len2 + 1):
        dp[0][j] = j
    
    # Fill matrix: choose min cost operation
    for i in range(1, len1 + 1):
        for j in range(1, len2 + 1):
            if str1[i - 1] == str2[j - 1]:
                dp[i][j] = dp[i - 1][j - 1]  # No edit needed
            else:
                dp[i][j] = 1 + min(
                    dp[i - 1][j - 1],  # Replace
                    dp[i][j - 1],      # Insert
                    dp[i - 1][j]       # Delete
                )
    
    return dp[len1][len2]


def levenshtein_similarity(str1: str, str2: str) -> float:
    """Normalize to 0.0-1.0 scale: 1.0 = identical, 0.0 = completely different"""
    distance = levenshtein_distance(str1, str2)
    max_len = max(len(str1), len(str2))
    return 1.0 - (distance / max_len) if max_len > 0 else 1.0


# ==============================================================================
# HAMMING DISTANCE - Count position mismatches (equal-length strings only)
# ==============================================================================

def hamming_distance(str1: str, str2: str) -> int:
    """
    Count positions where characters differ.
    Example: "karolin" vs "kathrin" = 3 (positions 2, 4, 5)
    """
    if len(str1) != len(str2):
        raise ValueError(
            f"Hamming requires equal-length strings. Got {len(str1)} and {len(str2)}"
        )
    return sum(c1 != c2 for c1, c2 in zip(str1, str2))


def hamming_similarity(str1: str, str2: str) -> float:
    """Normalize to 0.0-1.0, returns 0.0 if lengths differ"""
    if len(str1) != len(str2) or len(str1) == 0:
        return 0.0 if len(str1) != len(str2) else 1.0
    return 1.0 - (hamming_distance(str1, str2) / len(str1))


# ==============================================================================
# JACCARD SIMILARITY - Set overlap: |A ∩ B| / |A ∪ B|
# ==============================================================================

def jaccard_similarity(str1: str, str2: str, use_tokens: bool = True) -> float:
    """
    Measure overlap between word sets (or character sets).
    
    Example: "the quick fox" vs "the fast fox"
             Intersection: {the, fox} = 2
             Union: {the, quick, fast, fox} = 4
             Jaccard = 2/4 = 0.5
    
    Order-independent, great for paraphrasing detection.
    """
    set1 = set(str1.split()) if use_tokens else set(str1)
    set2 = set(str2.split()) if use_tokens else set(str2)
    
    if len(set1) == 0 and len(set2) == 0:
        return 1.0
    if len(set1) == 0 or len(set2) == 0:
        return 0.0
    
    intersection = set1 & set2
    union = set1 | set2
    return len(intersection) / len(union)


# ==============================================================================
# N-GRAM SIMILARITY - Compare character sequences
# ==============================================================================

def generate_ngrams(text: str, n: int = 2) -> Set[str]:
    """
    Generate n-grams (consecutive character sequences).
    Example: "hello" with n=2 → {"he", "el", "ll", "lo"}
    """
    if len(text) < n:
        return {text} if text else set()
    return {text[i:i + n] for i in range(len(text) - n + 1)}


def ngram_similarity(str1: str, str2: str, n: int = 2) -> float:
    """
    Dice coefficient based on shared n-grams: 2 * |A ∩ B| / (|A| + |B|)
    Captures structural similarity and partial matches.
    """
    ngrams1 = generate_ngrams(str1, n)
    ngrams2 = generate_ngrams(str2, n)
    
    if len(ngrams1) == 0 and len(ngrams2) == 0:
        return 1.0
    if len(ngrams1) == 0 or len(ngrams2) == 0:
        return 0.0
    
    intersection = ngrams1 & ngrams2
    return 2 * len(intersection) / (len(ngrams1) + len(ngrams2))


# ==============================================================================
# COMBINED FUZZY MATCHING - Main interface
# ==============================================================================

def fuzzy_match(
    text1: str,
    text2: str,
    preprocess: bool = True,
    levenshtein_threshold: float = 0.85,
    jaccard_threshold: float = 0.70,
    ngram_threshold: float = 0.75,
) -> Tuple[bool, dict]:
    """
    Comprehensive fuzzy matching using all algorithms.
    
    Returns match if ANY threshold is exceeded (robust detection).
    
    Args:
        text1, text2: Texts to compare
        preprocess: Apply normalization (recommended)
        levenshtein_threshold: Character-level similarity (typos)
        jaccard_threshold: Word-level similarity (paraphrasing)
        ngram_threshold: Structural similarity
    
    Returns:
        (is_match, scores_dict)
    
    Example:
        is_match, scores = fuzzy_match(
            "Samsung Galaxy S23",
            "Samsung Galxy S23"
        )
        # → (True, {'levenshtein': 0.94, 'jaccard': 1.0, 'ngram': 0.96})
    """
    # Normalize texts
    if preprocess:
        processed1 = preprocess_text(text1)
        processed2 = preprocess_text(text2)
    else:
        processed1 = text1.lower().strip()
        processed2 = text2.lower().strip()
    
    # Handle edge cases
    if processed1 == processed2:
        return True, {
            "levenshtein": 1.0,
            "jaccard": 1.0,
            "ngram": 1.0,
            "is_match": True,
        }
    
    if not processed1 or not processed2:
        return False, {
            "levenshtein": 0.0,
            "jaccard": 0.0,
            "ngram": 0.0,
            "is_match": False,
        }
    
    # Calculate all similarity scores
    lev_score = levenshtein_similarity(processed1, processed2)
    jac_score = jaccard_similarity(processed1, processed2, use_tokens=True)
    ngram_score = ngram_similarity(processed1, processed2, n=2)
    
    # Match if ANY threshold exceeded
    is_match = (
        lev_score >= levenshtein_threshold or
        jac_score >= jaccard_threshold or
        ngram_score >= ngram_threshold
    )
    
    return is_match, {
        "levenshtein": round(lev_score, 3),
        "jaccard": round(jac_score, 3),
        "ngram": round(ngram_score, 3),
        "is_match": is_match,
    }


# ==============================================================================
# ASYNC API - For FastAPI integration
# ==============================================================================

async def is_fuzzy_duplicate(
    text: str,
    candidates: List[str],
    threshold: float = 0.85,
) -> Tuple[bool, Optional[str], Optional[dict]]:
    """
    Check if text matches any candidate (async for FastAPI).
    
    Returns:
        (is_duplicate, matched_text, scores)
    """
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


# ==============================================================================
# BATCH PROCESSING - For Excel uploads
# ==============================================================================

def find_fuzzy_duplicates_in_batch(
    texts: List[str],
    threshold: float = 0.85,
) -> List[Tuple[int, int, dict]]:
    """
    Find all duplicate pairs within a batch (pairwise comparison).
    
    Returns:
        List of (index1, index2, scores) for each duplicate pair
    
    Example:
        texts = ["quick brown fox", "hello world", "fast brown fox"]
        duplicates = find_fuzzy_duplicates_in_batch(texts)
        # → [(0, 2, {'levenshtein': 0.72, ...})]
    """
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


# ==============================================================================
# UTILITY - Get best matches
# ==============================================================================

def get_best_match(
    query: str,
    candidates: List[str],
    top_k: int = 5,
) -> List[Tuple[str, dict]]:
    """
    Find top-k most similar candidates (useful for ranking).
    Returns sorted list of (candidate_text, scores).
    """
    matches = []
    
    for candidate in candidates:
        _, scores = fuzzy_match(query, candidate, preprocess=True)
        best_score = max(scores["levenshtein"], scores["jaccard"], scores["ngram"])
        matches.append((candidate, scores, best_score))
    
    # Sort by best score descending
    matches.sort(key=lambda x: x[2], reverse=True)
    return [(text, scores) for text, scores, _ in matches[:top_k]]


# ==============================================================================
# DEMO & TESTING
# ==============================================================================

if __name__ == "__main__":
    print("=" * 70)
    print("FUZZY MATCHING DEMO")
    print("=" * 70)
    
    # Test 1: Typo detection
    print("\n1. TYPO DETECTION")
    t1, t2 = "Samsung Galaxy", "Sasmung Galaxy"
    is_match, scores = fuzzy_match(t1, t2)
    print(f"'{t1}' vs '{t2}'")
    print(f"Match: {is_match}, Scores: {scores}")
    
    # Test 2: Paraphrasing
    print("\n2. PARAPHRASING")
    t1, t2 = "machine learning is powerful", "ML is very powerful"
    is_match, scores = fuzzy_match(t1, t2)
    print(f"'{t1}' vs '{t2}'")
    print(f"Match: {is_match}, Scores: {scores}")
    
    # Test 3: Batch processing
    print("\n3. BATCH DUPLICATE DETECTION")
    batch = [
        "The quick brown fox",
        "Python programming",
        "The fast brown fox",
    ]
    duplicates = find_fuzzy_duplicates_in_batch(batch, threshold=0.75)
    print(f"Batch: {batch}")
    print(f"Duplicates found: {duplicates}")
    
    print("\n" + "=" * 70)
