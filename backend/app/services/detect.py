import hashlib
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple

import numpy as np

# Optional heavy dependencies (lazy import inside functions)
# from thefuzz import fuzz
# from sentence_transformers import SentenceTransformer
# import torch


# ----------------------------
# Utilities
# ----------------------------
def sha256_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    if a.ndim == 1:
        a = a.reshape(1, -1)
    if b.ndim == 1:
        b = b.reshape(1, -1)
    denom = (np.linalg.norm(a, axis=1) * np.linalg.norm(b, axis=1)) + 1e-12
    return float(np.dot(a, b.T).squeeze() / denom)


# ----------------------------
# Exact & Near-Duplicate Detection
# ----------------------------
def exact_match_hash(
    text: str,
    reference_hashes: set
) -> bool:
    return sha256_hash(text) in reference_hashes


def fuzzy_match_score(
    text: str,
    references: List[str]
) -> float:
    """
    Returns the highest fuzzy match score (0-100).
    Uses thefuzz (Levenshtein-based) if available.
    """
    from thefuzz import fuzz  # lazy import for speed if unused
    if not references:
        return 0.0
    return float(max(fuzz.ratio(text, ref) for ref in references))


# ----------------------------
# Semantic Similarity (Paraphrase Detection)
# ----------------------------
@dataclass
class EmbeddingIndex:
    model_name: str
    embeddings: np.ndarray
    texts: List[str]

    @staticmethod
    def build(texts: List[str], model_name: str = "all-MiniLM-L6-v2") -> "EmbeddingIndex":
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer(model_name)
        emb = model.encode(texts, convert_to_numpy=True, normalize_embeddings=True)
        return EmbeddingIndex(model_name=model_name, embeddings=emb, texts=texts)

    def best_cosine_similarity(self, text: str) -> float:
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer(self.model_name)
        vec = model.encode([text], convert_to_numpy=True, normalize_embeddings=True)
        sims = np.dot(self.embeddings, vec.T).squeeze()
        return float(np.max(sims)) if len(sims) else 0.0


# ----------------------------
# AI-Generated Content Detection (Placeholder / Lightweight)
# ----------------------------
def ai_generated_probability(text: str) -> float:
    """
    Placeholder: Replace with a small classifier or a hosted API.
    For example, a fine-tuned RoBERTa model can be used here.
    """
    # Example stub: return fixed low probability
    return 0.10


# ----------------------------
# Web Scraping & License Validation (Simulated)
# ----------------------------
RESTRICTED_SITES = {"wikipedia.org", "github.com", "stackoverflow.com"}


def simulate_web_search(text: str) -> Optional[str]:
    """
    Simulated web search. Replace with Google Search API or Serper.dev.
    """
    # Placeholder: pretend no match
    return None


def license_risk_status(url: Optional[str]) -> str:
    if not url:
        return "Pass"
    for domain in RESTRICTED_SITES:
        if domain in url:
            return "Fail"
    return "Pass"


# ----------------------------
# Main Validation Function
# ----------------------------
def validate_text(
    text: str,
    reference_texts: List[str],
    reference_hashes: Optional[set] = None,
    embedding_index: Optional[EmbeddingIndex] = None,
    fuzzy_threshold: float = 90.0,
    semantic_threshold: float = 0.85,
    ai_threshold: float = 0.70
) -> Dict:
    """
    Returns a structured JSON-like dict:
    {
      is_duplicate: bool,
      similarity_score: float,
      is_ai_generated: bool,
      web_match_url: str|None,
      license_status: "Pass"/"Fail"
    }
    """
    if reference_hashes is None:
        reference_hashes = {sha256_hash(t) for t in reference_texts}

    # 1) Exact match
    is_exact_dup = exact_match_hash(text, reference_hashes)

    # 2) Fuzzy match
    fuzzy_score = fuzzy_match_score(text, reference_texts)
    is_fuzzy_dup = fuzzy_score >= fuzzy_threshold

    # 3) Semantic match
    semantic_score = 0.0
    if embedding_index is not None and reference_texts:
        semantic_score = embedding_index.best_cosine_similarity(text)
    is_semantic_dup = semantic_score >= semantic_threshold

    # 4) AI generation score
    ai_prob = ai_generated_probability(text)
    is_ai_generated = ai_prob >= ai_threshold

    # 5) Web search + license validation
    web_url = simulate_web_search(text)
    license_status = license_risk_status(web_url)

    # Decide overall similarity score (max of fuzzy or semantic for short text)
    similarity_score = max(fuzzy_score / 100.0, semantic_score)

    is_duplicate = is_exact_dup or is_fuzzy_dup or is_semantic_dup

    return {
        "is_duplicate": bool(is_duplicate),
        "similarity_score": float(similarity_score),
        "is_ai_generated": bool(is_ai_generated),
        "web_match_url": web_url,
        "license_status": license_status
    }


# ----------------------------
# Batch Example (Excel-ready)
# ----------------------------
def validate_batch(
    texts: List[str],
    reference_texts: List[str],
    use_embeddings: bool = True
) -> List[Dict]:
    reference_hashes = {sha256_hash(t) for t in reference_texts}
    embedding_index = EmbeddingIndex.build(reference_texts) if use_embeddings else None

    return [
        validate_text(
            text=t,
            reference_texts=reference_texts,
            reference_hashes=reference_hashes,
            embedding_index=embedding_index
        )
        for t in texts
    ]