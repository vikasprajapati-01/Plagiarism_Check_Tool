"""Detection endpoints for exact, fuzzy, and semantic matching."""

import io
import uuid

from fastapi import APIRouter, Form, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.services.detect import is_exact_duplicate
from app.services.fuzzy import is_fuzzy_duplicate, find_fuzzy_duplicates_in_batch
from app.services.embeddings import is_semantic_duplicate, find_semantic_duplicates_in_batch, is_available as embeddings_available
from app.services.reports import DetectionResult, classify_risk, generate_report_bytes, _OPENPYXL_AVAILABLE
from app.services import word2vec as word2vec_service
from app.services import clustering as clustering_service
from app.storage.repository import (
    async_fetch_all_texts_by_batch,
    async_get_batch_id_by_name,
    async_fetch_all_texts_with_batch_info,
)

app = APIRouter()


class BatchFuzzyRequest(BaseModel):
    texts: list[str]
    threshold: float = 0.85
    download_report: bool = False


class BatchSemanticRequest(BaseModel):
    texts: list[str]
    threshold: float = 0.85
    download_report: bool = False


class CrossBatchRequest(BaseModel):
    texts: list[str]
    method: str = "fuzzy"          # "exact" | "fuzzy" | "semantic"
    threshold: float = 0.85
    download_report: bool = False


@app.get("/")
async def detect_root():
    return {"message": "Detect endpoint"}


@app.post("/exact")
async def detect_exact(
    text: str = Form(...),
    batch_id: str | None = Form(None),
    batch_name: str | None = Form(None),
    download_report: bool = Form(False),
):
    resolved_batch_id = batch_id

    if batch_name:
        resolved_batch_id = await async_get_batch_id_by_name(batch_name)
        if not resolved_batch_id:
            raise HTTPException(status_code=404, detail="batch_name not found")

    if resolved_batch_id:
        try:
            uuid.UUID(resolved_batch_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="batch_id must be a valid UUID")

    is_dup = await is_exact_duplicate(text, resolved_batch_id)

    if download_report:
        if not _OPENPYXL_AVAILABLE:
            raise HTTPException(status_code=503, detail="openpyxl is not installed. Run: pip install openpyxl")
        result = DetectionResult(
            text=text,
            is_duplicate=is_dup,
            risk_level="high" if is_dup else "none",
            detection_method="exact",
        )
        report_bytes = generate_report_bytes([result])
        return StreamingResponse(
            io.BytesIO(report_bytes),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": "attachment; filename=exact_detection_report.xlsx"},
        )

    return {
        "is_duplicate": is_dup,
        "batch_id": resolved_batch_id,
        "batch_name": batch_name,
        "scope": "batch" if resolved_batch_id else "global",
    }

# Fuzzy duplicate detection endpoint

@app.post("/fuzzy")
async def detect_fuzzy_duplicate(
    text: str = Form(...),
    batch_id: str | None = Form(None),
    batch_name: str | None = Form(None),
    threshold: float = Form(0.85),
    download_report: bool = Form(False),
):
    resolved_batch_id = batch_id

    if batch_name:
        resolved_batch_id = await async_get_batch_id_by_name(batch_name)
        if not resolved_batch_id:
            raise HTTPException(status_code=404, detail="batch_name not found")

    if resolved_batch_id:
        try:
            uuid.UUID(resolved_batch_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="batch_id must be a valid UUID")

    candidates = await async_fetch_all_texts_by_batch(resolved_batch_id)

    is_dup, matched_text, scores = await is_fuzzy_duplicate(
        text,
        candidates,
        threshold=threshold,
    )

    if download_report:
        if not _OPENPYXL_AVAILABLE:
            raise HTTPException(status_code=503, detail="openpyxl is not installed. Run: pip install openpyxl")
        best_score = max(scores.values()) if scores else 0.0
        result = DetectionResult(
            text=text,
            is_duplicate=is_dup,
            similarity_scores=scores or {},
            source=matched_text,
            risk_level=classify_risk(best_score) if is_dup else "none",
            detection_method="fuzzy",
        )
        report_bytes = generate_report_bytes([result])
        return StreamingResponse(
            io.BytesIO(report_bytes),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": "attachment; filename=fuzzy_detection_report.xlsx"},
        )

    return {
        "is_duplicate": is_dup,
        "matched_text": matched_text,
        "similarity_scores": scores,
        "threshold": threshold,
        "batch_id": resolved_batch_id,
        "batch_name": batch_name,
        "scope": "batch" if resolved_batch_id else "global",
    }


@app.post("/batch-fuzzy")
async def detect_batch_fuzzy_duplicates(request: BatchFuzzyRequest):
    duplicates = find_fuzzy_duplicates_in_batch(
        request.texts,
        threshold=request.threshold,
    )

    if request.download_report:
        if not _OPENPYXL_AVAILABLE:
            raise HTTPException(status_code=503, detail="openpyxl is not installed. Run: pip install openpyxl")
        seen: set[int] = set()
        results = []
        for i, j, scores in duplicates:
            best = max(scores.values()) if scores else 0.0
            for idx, other_idx in [(i, j), (j, i)]:
                if idx not in seen:
                    seen.add(idx)
                    results.append(DetectionResult(
                        text=request.texts[idx],
                        is_duplicate=True,
                        similarity_scores=scores,
                        source=request.texts[other_idx],
                        risk_level=classify_risk(best),
                        detection_method="fuzzy",
                    ))
        for idx, t in enumerate(request.texts):
            if idx not in seen:
                results.append(DetectionResult(
                    text=t,
                    is_duplicate=False,
                    risk_level="none",
                    detection_method="fuzzy",
                ))
        report_bytes = generate_report_bytes(results)
        return StreamingResponse(
            io.BytesIO(report_bytes),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": "attachment; filename=batch_fuzzy_report.xlsx"},
        )

    return {
        "total_texts": len(request.texts),
        "duplicate_pairs": len(duplicates),
        "duplicates": [
            {
                "index1": i,
                "index2": j,
                "text1": request.texts[i],
                "text2": request.texts[j],
                "scores": scores,
            }
            for i, j, scores in duplicates
        ],
    }


# ==============================================================================
# SEMANTIC DUPLICATE DETECTION — SBERT + Cosine Similarity
# ==============================================================================

@app.post("/semantic")
async def detect_semantic_duplicate(
    text: str = Form(...),
    batch_id: str | None = Form(None),
    batch_name: str | None = Form(None),
    threshold: float = Form(0.85),
    download_report: bool = Form(False),
):
    """Check if a single text is a semantic duplicate of any stored reference text."""
    if not embeddings_available():
        raise HTTPException(
            status_code=503,
            detail="Semantic detection unavailable. Install: pip install sentence-transformers",
        )

    resolved_batch_id = batch_id

    if batch_name:
        resolved_batch_id = await async_get_batch_id_by_name(batch_name)
        if not resolved_batch_id:
            raise HTTPException(status_code=404, detail="batch_name not found")

    if resolved_batch_id:
        try:
            uuid.UUID(resolved_batch_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="batch_id must be a valid UUID")

    candidates = await async_fetch_all_texts_by_batch(resolved_batch_id)

    is_dup, matched_text, score = await is_semantic_duplicate(
        text,
        candidates,
        threshold=threshold,
    )

    if download_report:
        if not _OPENPYXL_AVAILABLE:
            raise HTTPException(status_code=503, detail="openpyxl is not installed. Run: pip install openpyxl")
        result = DetectionResult(
            text=text,
            is_duplicate=is_dup,
            similarity_scores={"cosine_similarity": score or 0.0},
            source=matched_text,
            risk_level=classify_risk(score) if is_dup and score else "none",
            detection_method="semantic",
        )
        report_bytes = generate_report_bytes([result])
        return StreamingResponse(
            io.BytesIO(report_bytes),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": "attachment; filename=semantic_detection_report.xlsx"},
        )

    return {
        "is_duplicate": is_dup,
        "matched_text": matched_text,
        "similarity_score": score,
        "threshold": threshold,
        "batch_id": resolved_batch_id,
        "batch_name": batch_name,
        "scope": "batch" if resolved_batch_id else "global",
    }


@app.post("/batch-semantic")
async def detect_batch_semantic_duplicates(request: BatchSemanticRequest):
    """Find all semantic duplicate pairs within a submitted batch of texts."""
    if not embeddings_available():
        raise HTTPException(
            status_code=503,
            detail="Semantic detection unavailable. Install: pip install sentence-transformers",
        )

    if len(request.texts) < 2:
        raise HTTPException(status_code=400, detail="Provide at least 2 texts for batch comparison")

    duplicates = find_semantic_duplicates_in_batch(
        request.texts,
        threshold=request.threshold,
    )

    if request.download_report:
        if not _OPENPYXL_AVAILABLE:
            raise HTTPException(status_code=503, detail="openpyxl is not installed. Run: pip install openpyxl")
        seen: set[int] = set()
        results = []
        for i, j, score in duplicates:
            for idx, other_idx in [(i, j), (j, i)]:
                if idx not in seen:
                    seen.add(idx)
                    results.append(DetectionResult(
                        text=request.texts[idx],
                        is_duplicate=True,
                        similarity_scores={"cosine_similarity": score},
                        source=request.texts[other_idx],
                        risk_level=classify_risk(score),
                        detection_method="semantic",
                    ))
        for idx, t in enumerate(request.texts):
            if idx not in seen:
                results.append(DetectionResult(
                    text=t,
                    is_duplicate=False,
                    risk_level="none",
                    detection_method="semantic",
                ))
        report_bytes = generate_report_bytes(results)
        return StreamingResponse(
            io.BytesIO(report_bytes),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": "attachment; filename=batch_semantic_report.xlsx"},
        )

    return {
        "total_texts": len(request.texts),
        "duplicate_pairs": len(duplicates),
        "duplicates": [
            {
                "index1": i,
                "index2": j,
                "text1": request.texts[i],
                "text2": request.texts[j],
                "cosine_similarity": score,
            }
            for i, j, score in duplicates
        ],
    }


# ==============================================================================
# CROSS-BATCH DUPLICATE DETECTION — Check against ALL stored batches
# ==============================================================================

@app.post("/cross-batch")
async def detect_cross_batch_duplicates(request: CrossBatchRequest):
    """
    Check each submitted text against every reference text stored across
    ALL batches in the database.

    Returns which batch each match came from (batch_id + batch_name).

    Methods:
        exact    — SHA-256 hash comparison
        fuzzy    — Levenshtein / Jaccard / N-gram
        semantic — SBERT cosine similarity (requires sentence-transformers)
    """
    method = request.method.lower()
    if method not in ("exact", "fuzzy", "semantic"):
        raise HTTPException(status_code=400, detail="method must be 'exact', 'fuzzy', or 'semantic'")

    if method == "semantic" and not embeddings_available():
        raise HTTPException(
            status_code=503,
            detail="Semantic detection unavailable. Install: pip install sentence-transformers",
        )

    if not request.texts:
        raise HTTPException(status_code=400, detail="Provide at least one text")

    # Fetch every stored reference text with batch metadata
    all_refs = await async_fetch_all_texts_with_batch_info()

    if not all_refs:
        return {
            "total_submitted": len(request.texts),
            "total_references": 0,
            "message": "No reference texts found in the database. Register batches first via /api/v1/ingest/reference/register",
            "results": [],
        }

    ref_texts   = [r["cleaned_text"] for r in all_refs]
    ref_raw     = [r["raw_text"]     for r in all_refs]
    ref_batches = [(r["batch_id"], r["batch_name"]) for r in all_refs]

    results = []

    for submitted in request.texts:
        match_found        = False
        matched_raw        = None
        matched_batch_id   = None
        matched_batch_name = None
        scores: dict       = {}

        if method == "exact":
            from app.services.detect import sha256_hash
            from app.services.preprocess import preprocess_text
            cleaned = preprocess_text(submitted)
            submitted_hash = sha256_hash(cleaned)
            for ref_clean, (bid, bname) in zip(ref_texts, ref_batches):
                if sha256_hash(ref_clean) == submitted_hash:
                    match_found        = True
                    matched_raw        = ref_clean
                    matched_batch_id   = bid
                    matched_batch_name = bname
                    scores             = {"exact": 1.0}
                    break

        elif method == "fuzzy":
            is_dup, matched_text, match_scores = await is_fuzzy_duplicate(
                submitted, ref_texts, threshold=request.threshold
            )
            if is_dup and matched_text is not None:
                match_found        = True
                matched_raw        = matched_text
                idx                = ref_texts.index(matched_text)
                matched_batch_id, matched_batch_name = ref_batches[idx]
                scores             = match_scores or {}

        elif method == "semantic":
            is_dup, matched_text, sim_score = await is_semantic_duplicate(
                submitted, ref_texts, threshold=request.threshold
            )
            if is_dup and matched_text is not None:
                match_found        = True
                matched_raw        = matched_text
                idx                = ref_texts.index(matched_text)
                matched_batch_id, matched_batch_name = ref_batches[idx]
                scores             = {"cosine_similarity": sim_score}

        # Resolve back to original raw text for display
        matched_original = None
        if matched_raw is not None:
            try:
                idx = ref_texts.index(matched_raw)
                matched_original = ref_raw[idx]
            except ValueError:
                matched_original = matched_raw

        best_score = max(scores.values()) if scores else 0.0

        results.append({
            "submitted_text":     submitted,
            "is_duplicate":       match_found,
            "matched_text":       matched_original,
            "matched_batch_id":   matched_batch_id,
            "matched_batch_name": matched_batch_name,
            "similarity_scores":  scores,
            "risk_level":         classify_risk(best_score) if match_found else "none",
            "detection_method":   method,
        })

    if request.download_report:
        if not _OPENPYXL_AVAILABLE:
            raise HTTPException(status_code=503, detail="openpyxl is not installed. Run: pip install openpyxl")
        report_items = [
            DetectionResult(
                text=r["submitted_text"],
                is_duplicate=r["is_duplicate"],
                similarity_scores=r["similarity_scores"],
                source=r["matched_text"],
                risk_level=r["risk_level"],
                detection_method=r["detection_method"],
                notes=(
                    f"Matched batch: {r['matched_batch_name']} (id={r['matched_batch_id']})"
                    if r["is_duplicate"] else None
                ),
            )
            for r in results
        ]
        report_bytes = generate_report_bytes(report_items)
        return StreamingResponse(
            io.BytesIO(report_bytes),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": "attachment; filename=cross_batch_report.xlsx"},
        )

    total_dups = sum(1 for r in results if r["is_duplicate"])
    return {
        "total_submitted":  len(request.texts),
        "total_references": len(all_refs),
        "total_duplicates": total_dups,
        "method":           method,
        "threshold":        request.threshold,
        "results":          results,
    }


# ==============================================================================
# WORD2VEC / GLOVE BATCH DUPLICATE DETECTION
# ==============================================================================

class BatchWord2VecRequest(BaseModel):
    texts: list[str]
    threshold: float = 0.85
    download_report: bool = False


@app.post("/batch-word2vec")
async def detect_batch_word2vec_duplicates(request: BatchWord2VecRequest):
    """Find near-duplicate pairs in a batch using Word2Vec/GloVe cosine similarity.

    Requires a model to be available (set WORD2VEC_MODEL env var to a file path
    or a gensim model name like 'glove-wiki-gigaword-100').
    """
    if not word2vec_service.is_available():
        raise HTTPException(
            status_code=503,
            detail="gensim not installed. Run: pip install gensim",
        )

    if len(request.texts) < 2:
        raise HTTPException(status_code=400, detail="Provide at least 2 texts for batch comparison")

    try:
        duplicates = word2vec_service.find_duplicates_in_batch(
            request.texts,
            threshold=request.threshold,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))

    if request.download_report:
        if not _OPENPYXL_AVAILABLE:
            raise HTTPException(status_code=503, detail="openpyxl not installed. Run: pip install openpyxl")
        seen: set[int] = set()
        results = []
        for i, j, score in duplicates:
            for idx, other_idx in [(i, j), (j, i)]:
                if idx not in seen:
                    seen.add(idx)
                    results.append(DetectionResult(
                        text=request.texts[idx],
                        is_duplicate=True,
                        similarity_scores={"word2vec_cosine": score},
                        source=request.texts[other_idx],
                        risk_level=classify_risk(score),
                        detection_method="word2vec",
                    ))
        for idx, t in enumerate(request.texts):
            if idx not in seen:
                results.append(DetectionResult(
                    text=t,
                    is_duplicate=False,
                    risk_level="none",
                    detection_method="word2vec",
                ))
        report_bytes = generate_report_bytes(results)
        return StreamingResponse(
            io.BytesIO(report_bytes),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": "attachment; filename=word2vec_report.xlsx"},
        )

    return {
        "total_texts": len(request.texts),
        "duplicate_pairs": len(duplicates),
        "threshold": request.threshold,
        "duplicates": [
            {
                "index1": i,
                "index2": j,
                "text1": request.texts[i],
                "text2": request.texts[j],
                "word2vec_cosine": score,
            }
            for i, j, score in duplicates
        ],
    }


# ==============================================================================
# CLUSTERING — DBSCAN / K-MEANS
# ==============================================================================

class ClusterRequest(BaseModel):
    texts: list[str]
    method: str = "dbscan"     # "dbscan" or "kmeans"
    eps: float = 0.25          # DBSCAN only — cosine distance threshold
    min_samples: int = 2       # DBSCAN only — minimum cluster size
    n_clusters: int = 5        # K-means only — number of clusters


@app.post("/cluster")
async def cluster_texts(request: ClusterRequest):
    """Group a batch of texts into similarity clusters using DBSCAN or K-means.

    Uses SBERT embeddings internally.
    DBSCAN: auto-detects number of clusters; label -1 means noise (no group).
    K-means: groups into exactly n_clusters.
    """
    if not clustering_service.is_available():
        raise HTTPException(
            status_code=503,
            detail="scikit-learn not installed. Run: pip install scikit-learn",
        )

    if not embeddings_available():
        raise HTTPException(
            status_code=503,
            detail="sentence-transformers not installed. Run: pip install sentence-transformers",
        )

    if len(request.texts) < 2:
        raise HTTPException(status_code=400, detail="Provide at least 2 texts to cluster")

    method = request.method.lower()
    if method not in ("dbscan", "kmeans"):
        raise HTTPException(status_code=400, detail="method must be 'dbscan' or 'kmeans'")

    try:
        if method == "dbscan":
            clusters = clustering_service.cluster_dbscan(
                request.texts,
                eps=request.eps,
                min_samples=request.min_samples,
            )
        else:
            clusters = clustering_service.cluster_kmeans(
                request.texts,
                n_clusters=request.n_clusters,
            )
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))

    formatted = clustering_service.format_clusters(clusters, request.texts)

    return {
        "total_texts": len(request.texts),
        "total_clusters": sum(1 for cid in clusters if cid != -1),
        "noise_count": len(clusters.get(-1, [])),   # DBSCAN only; 0 for K-means
        "method": method,
        "clusters": formatted,
    }

