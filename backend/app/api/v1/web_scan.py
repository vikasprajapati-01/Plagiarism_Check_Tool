# Web scan endpoints — searches DuckDuckGo and scores each result for plagiarism.

import io
from typing import List

from fastapi import APIRouter, Form, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.services.web_scan import scan_text_online, scan_texts_online, is_available
from app.services.reports import (
    DetectionResult,
    classify_risk,
    generate_report_bytes,
    _OPENPYXL_AVAILABLE,
)

app = APIRouter()


class BatchWebScanRequest(BaseModel):
    texts: List[str]
    threshold: float = 0.5
    max_queries: int = 2
    max_results_per_query: int = 3
    download_report: bool = False


def _to_detection_result(r) -> DetectionResult:
    """Map a WebScanResult to the common DetectionResult shape used by the report generator."""
    scores = r.matches[0].similarity_scores if r.matches else {}
    return DetectionResult(
        text=r.submitted_text,
        is_duplicate=r.is_plagiarism,
        similarity_scores=scores,
        source=r.best_url or "",
        risk_level=classify_risk(r.best_score) if r.is_plagiarism else "none",
        detection_method="web_scan",
        notes=f"Best source: {r.best_url}" if r.best_url else None,
    )


@app.get("/")
async def web_scan_root():
    return {
        "message": "Web Scan endpoint",
        "available": is_available(),
        "install_hint": (
            None if is_available()
            else "Run: pip install ddgs beautifulsoup4 lxml"
        ),
    }


@app.post("/scan")
async def web_scan_single(
    text: str = Form(...),
    threshold: float = Form(0.5),
    max_queries: int = Form(3),
    max_results_per_query: int = Form(5),
    download_report: bool = Form(False),
):
    """
    Check a single text for plagiarism against live web sources.
    Set threshold between 0.4–0.6 for best results.
    """
    if not is_available():
        raise HTTPException(
            status_code=503,
            detail="Web scan unavailable. Run: pip install ddgs beautifulsoup4 lxml",
        )

    result = await scan_text_online(
        text,
        threshold=threshold,
        max_queries=max_queries,
        max_results_per_query=max_results_per_query,
    )

    if result.error:
        raise HTTPException(status_code=503, detail=result.error)

    if download_report:
        if not _OPENPYXL_AVAILABLE:
            raise HTTPException(
                status_code=503,
                detail="openpyxl not installed. Run: pip install openpyxl",
            )
        report_bytes = generate_report_bytes([_to_detection_result(result)])
        return StreamingResponse(
            io.BytesIO(report_bytes),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": "attachment; filename=web_scan_report.xlsx"},
        )

    return {
        "submitted_text": result.submitted_text,
        "is_plagiarism": result.is_plagiarism,
        "best_score": result.best_score,
        "best_url": result.best_url,
        "total_urls_checked": result.total_urls_checked,
        "matches_found": len(result.matches),
        "matches": [
            {
                "url": m.url,
                "title": m.title,
                "snippet": m.snippet,
                "page_excerpt": m.page_excerpt,
                "similarity_scores": m.similarity_scores,
                "best_score": m.best_score,
                "fingerprint": m.fingerprint,
            }
            for m in result.matches
        ],
    }


@app.post("/batch-scan")
async def web_scan_batch(request: BatchWebScanRequest):
    """
    Check multiple texts concurrently.
    Keep max_results_per_query low (2–3) to avoid rate limiting.
    """
    if not is_available():
        raise HTTPException(
            status_code=503,
            detail="Web scan unavailable. Run: pip install ddgs beautifulsoup4 lxml",
        )

    if not request.texts:
        raise HTTPException(status_code=400, detail="Provide at least one text")

    results = await scan_texts_online(
        request.texts,
        threshold=request.threshold,
        max_queries=request.max_queries,
        max_results_per_query=request.max_results_per_query,
    )

    if request.download_report:
        if not _OPENPYXL_AVAILABLE:
            raise HTTPException(
                status_code=503,
                detail="openpyxl not installed. Run: pip install openpyxl",
            )
        report_bytes = generate_report_bytes([_to_detection_result(r) for r in results])
        return StreamingResponse(
            io.BytesIO(report_bytes),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": "attachment; filename=web_scan_batch_report.xlsx"},
        )

    total_flagged = sum(1 for r in results if r.is_plagiarism)

    return {
        "total_texts": len(results),
        "plagiarism_detected": total_flagged,
        "results": [
            {
                "submitted_text": (
                    r.submitted_text[:120] + "..."
                    if len(r.submitted_text) > 120
                    else r.submitted_text
                ),
                "is_plagiarism": r.is_plagiarism,
                "best_score": r.best_score,
                "best_url": r.best_url,
                "total_urls_checked": r.total_urls_checked,
                "match_count": len(r.matches),
                "top_matches": [
                    {
                        "url": m.url,
                        "title": m.title,
                        "best_score": m.best_score,
                        "similarity_scores": m.similarity_scores,
                    }
                    for m in r.matches[:3]
                ],
                "error": r.error,
            }
            for r in results
        ],
    }
