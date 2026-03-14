"""Reports endpoint — accepts detection results and returns a downloadable .xlsx report."""

import io
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.services.reports import DetectionResult, classify_risk, generate_report_bytes, _OPENPYXL_AVAILABLE

app = APIRouter()


class ResultItem(BaseModel):
    text: str
    is_duplicate: bool
    similarity_scores: Dict[str, float] = {}
    source: Optional[str] = None
    risk_level: str = "none"
    detection_method: Optional[str] = None
    notes: Optional[str] = None


class ReportRequest(BaseModel):
    results: List[ResultItem]
    filename: str = "plagiarism_report"


# Matches the exact shape returned by POST /api/v1/web-scan/scan
class WebScanMatchItem(BaseModel):
    url: str
    title: str
    snippet: str
    page_excerpt: str
    similarity_scores: Dict[str, float] = {}
    best_score: float = 0.0
    fingerprint: Dict[str, Any] = {}


class WebScanReportRequest(BaseModel):
    submitted_text: str
    is_plagiarism: bool
    best_score: float
    best_url: Optional[str] = None
    matches: List[WebScanMatchItem] = []
    filename: str = "web_scan_report"


@app.get("/")
async def reports_root():
    return {
        "message": "Reports endpoint",
        "available": _OPENPYXL_AVAILABLE,
        "install_hint": None if _OPENPYXL_AVAILABLE else "Run: pip install openpyxl",
    }


@app.post("/download")
async def download_report(request: ReportRequest):
    """Generate a styled .xlsx report from provided detection results and return it as a file download."""
    if not _OPENPYXL_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail="openpyxl not installed. Run: pip install openpyxl",
        )

    if not request.results:
        raise HTTPException(status_code=400, detail="Provide at least one result")

    detection_results = [
        DetectionResult(
            text=r.text,
            is_duplicate=r.is_duplicate,
            similarity_scores=r.similarity_scores,
            source=r.source,
            risk_level=r.risk_level,
            detection_method=r.detection_method,
            notes=r.notes,
        )
        for r in request.results
    ]

    report_bytes = generate_report_bytes(detection_results)
    filename = f"{request.filename.strip() or 'plagiarism_report'}.xlsx"

    return StreamingResponse(
        io.BytesIO(report_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@app.post("/from-web-scan")
async def report_from_web_scan(request: WebScanReportRequest):
    """Generate a report directly from the web scan response — one row per matched source.

    Paste the full JSON from POST /api/v1/web-scan/scan here (with submitted_text included).
    If no matches, a single clean row is generated.
    """
    if not _OPENPYXL_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail="openpyxl not installed. Run: pip install openpyxl",
        )

    detection_results = []

    if request.matches:
        for m in request.matches:
            domain = m.fingerprint.get("domain", "")
            published = m.fingerprint.get("published_at")
            notes = f"Title: {m.title}"
            if domain:
                notes += f" | Domain: {domain}"
            if published:
                notes += f" | Published: {published}"

            detection_results.append(DetectionResult(
                text=request.submitted_text,
                is_duplicate=True,
                similarity_scores=m.similarity_scores,
                source=m.url,
                risk_level=classify_risk(m.best_score),
                detection_method="web_scan",
                notes=notes,
            ))
    else:
        # No matches found — single clean row
        detection_results.append(DetectionResult(
            text=request.submitted_text,
            is_duplicate=False,
            risk_level="none",
            detection_method="web_scan",
        ))

    report_bytes = generate_report_bytes(detection_results)
    filename = f"{request.filename.strip() or 'web_scan_report'}.xlsx"

    return StreamingResponse(
        io.BytesIO(report_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )

