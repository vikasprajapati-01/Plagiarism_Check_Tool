"""Cluster texts into groups using DBSCAN or K-means.

Embeddings come from the existing SBERT service (embeddings.py).
DBSCAN is good when you don't know the number of clusters up front.
K-means requires you to specify n_clusters in advance.
"""

from typing import Dict, List, Optional, Sequence

from app.services.embeddings import encode_texts

try:
    import numpy as np
    from sklearn.cluster import DBSCAN, KMeans
    _SKLEARN_AVAILABLE = True
except ImportError:
    _SKLEARN_AVAILABLE = False


def is_available() -> bool:
    return _SKLEARN_AVAILABLE


# ── DBSCAN ────────────────────────────────────────────────────────────────────

def cluster_dbscan(
    texts: Sequence[str],
    eps: float = 0.25,      # cosine distance ceiling; lower = tighter clusters
    min_samples: int = 2,
    model_name: Optional[str] = None,
) -> Dict[int, List[int]]:
    """Group texts with DBSCAN. Label -1 = noise (text belongs to no cluster).

    eps is cosine *distance* (0 = identical, 1 = orthogonal), not similarity.
    Returns {cluster_id: [text_indices]}.
    """
    if not _SKLEARN_AVAILABLE:
        raise RuntimeError("scikit-learn not installed. Run: pip install scikit-learn")
    if len(texts) < 2:
        return {0: [0]} if texts else {}

    vecs = np.array(encode_texts(list(texts), model_name=model_name, preprocess=True))
    labels = DBSCAN(eps=eps, min_samples=min_samples, metric="cosine").fit_predict(vecs)

    clusters: Dict[int, List[int]] = {}
    for idx, label in enumerate(labels.tolist()):
        clusters.setdefault(label, []).append(idx)
    return clusters


# ── K-means ───────────────────────────────────────────────────────────────────

def cluster_kmeans(
    texts: Sequence[str],
    n_clusters: int = 5,
    model_name: Optional[str] = None,
    random_state: int = 42,
) -> Dict[int, List[int]]:
    """Group texts into exactly n_clusters via K-means.

    n_clusters is capped at len(texts) automatically.
    Returns {cluster_id: [text_indices]}.
    """
    if not _SKLEARN_AVAILABLE:
        raise RuntimeError("scikit-learn not installed. Run: pip install scikit-learn")

    k = min(n_clusters, len(texts))
    if k < 2:
        return {0: list(range(len(texts)))}

    vecs = np.array(encode_texts(list(texts), model_name=model_name, preprocess=True))
    labels = KMeans(n_clusters=k, random_state=random_state, n_init="auto").fit_predict(vecs)

    clusters: Dict[int, List[int]] = {}
    for idx, label in enumerate(labels.tolist()):
        clusters.setdefault(label, []).append(idx)
    return clusters


# ── Output formatter ──────────────────────────────────────────────────────────

def format_clusters(clusters: Dict[int, List[int]], texts: Sequence[str]) -> List[dict]:
    """Convert raw cluster map to a readable list with actual text content."""
    return [
        {
            "cluster_id": cid,
            "label": "noise" if cid == -1 else f"cluster_{cid}",
            "size": len(indices),
            "texts": [{"index": i, "text": texts[i]} for i in indices],
        }
        for cid, indices in sorted(clusters.items())
    ]
