"""License check detection endpoints."""

import io
from typing import Optional

import pandas as pd
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.services.license_check import (
    detect_license,
    detect_license_batch,
    get_supported_licenses,
    is_available,
    is_fuzzy_available,
    LicenseCheckResult,
)
from app.services.reports import (
    DetectionResult,
    classify_risk,
    generate_report_bytes,
    _OPENPYXL_AVAILABLE,
)


app = APIRouter()


# ==============================================================================
# REQUEST MODELS
# ==============================================================================

class BatchLicenseRequest(BaseModel):
    """Request model for batch license checking."""
    texts: list[str]
    threshold: float = 0.3
    download_report: bool = False


class SingleLicenseRequest(BaseModel):
    """Request model for single text license checking."""
    text: str
    threshold: float = 0.3


# ==============================================================================
# HELPER FUNCTIONS
# ==============================================================================

def _read_rows_from_file(filename: str, contents: bytes) -> list[str]:
    """Parse uploaded files (csv, xlsx, txt) into a list of strings."""
    if filename.endswith(".csv"):
        df = pd.read_csv(io.BytesIO(contents))
        first_column = df.columns[0]
        return df[first_column].dropna().astype(str).tolist()
    if filename.endswith(".xlsx") or filename.endswith(".xls"):
        df = pd.read_excel(io.BytesIO(contents))
        first_column = df.columns[0]
        return df[first_column].dropna().astype(str).tolist()
    if filename.endswith(".txt"):
        text_data = contents.decode("utf-8").splitlines()
        return [line.strip() for line in text_data if line.strip()]
    raise ValueError("Unsupported file format. Use .csv, .xlsx, .xls, or .txt")


def _license_result_to_dict(result: LicenseCheckResult) -> dict:
    """Convert LicenseCheckResult to JSON-serializable dict."""
    return {
        "has_license": result.has_license,
        "total_matches": result.total_matches,
        "risk_level": result.risk_level,
        "primary_license": {
            "name": result.primary_license.license_name,
            "spdx_id": result.primary_license.spdx_id,
            "confidence": result.primary_license.confidence,
            "matched_keywords": result.primary_license.matched_keywords,
            "signature_similarity": result.primary_license.signature_similarity,
            "license_url": result.primary_license.license_url,
            "snippet": result.primary_license.snippet,
        } if result.primary_license else None,
        "all_licenses": [
            {
                "name": m.license_name,
                "spdx_id": m.spdx_id,
                "confidence": m.confidence,
                "matched_keywords": m.matched_keywords,
                "license_url": m.license_url,
            }
            for m in result.licenses_detected
        ],
    }


def _license_result_to_detection_result(
    text: str,
    result: LicenseCheckResult,
) -> DetectionResult:
    """Convert LicenseCheckResult to DetectionResult for report generation."""
    primary = result.primary_license

    if primary:
        notes = f"License: {primary.license_name} ({primary.spdx_id}) | Confidence: {primary.confidence:.2%}"
        if primary.snippet:
            notes += f" | Snippet: {primary.snippet[:100]}..."
    else:
        notes = "No license detected"

    return DetectionResult(
        text=text[:500] if len(text) > 500 else text,
        is_duplicate=result.has_license,
        similarity_scores={
            "license_confidence": primary.confidence if primary else 0.0,
            "signature_similarity": primary.signature_similarity if primary else 0.0,
        },
        source=primary.license_name if primary else None,
        risk_level=result.risk_level,
        detection_method="license",
        notes=notes,
    )


# ==============================================================================
# ENDPOINTS
# ==============================================================================

@app.get("/")
async def license_check_root():
    """License check endpoint status and capabilities."""
    return {
        "message": "License Check endpoint",
        "description": "Detects open source licenses in text/code content",
        "available": is_available(),
        "fuzzy_matching": is_fuzzy_available(),
        "supported_licenses_count": len(get_supported_licenses()),
    }


@app.get("/licenses")
async def list_supported_licenses():
    """List all supported licenses that can be detected."""
    return {
        "total": len(get_supported_licenses()),
        "licenses": get_supported_licenses(),
    }


@app.post("/check")
async def check_license(
    text: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
    threshold: float = Form(0.3),
    download_report: bool = Form(False),
):
    """
    Check text or file for open source license content.

    Args:
        text: Text content to check (form data)
        file: File upload (csv, xlsx, txt) - each row/line is checked separately
        threshold: Minimum confidence threshold (0.0 to 1.0, default 0.3)
        download_report: If True, return Excel report instead of JSON

    Returns:
        License detection results with confidence scores and matched licenses.
    """
    if not is_available():
        raise HTTPException(
            status_code=503,
            detail="License check service unavailable",
        )

    if threshold < 0.0 or threshold > 1.0:
        raise HTTPException(
            status_code=400,
            detail="Threshold must be between 0.0 and 1.0",
        )

    # Case 1: File upload - batch process
    if file is not None:
        contents = await file.read()
        filename = file.filename.lower()
        try:
            rows = _read_rows_from_file(filename, contents)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc))

        if not rows:
            raise HTTPException(status_code=400, detail="File contained no usable text")

        results = await detect_license_batch(rows, threshold)

        if download_report:
            if not _OPENPYXL_AVAILABLE:
                raise HTTPException(
                    status_code=503,
                    detail="openpyxl is not installed. Run: pip install openpyxl",
                )
            detection_results = [
                _license_result_to_detection_result(text_row, res)
                for text_row, res in zip(rows, results)
            ]
            report_bytes = generate_report_bytes(detection_results)
            return StreamingResponse(
                io.BytesIO(report_bytes),
                media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                headers={"Content-Disposition": "attachment; filename=license_check_report.xlsx"},
            )

        # Return JSON results
        licenses_found = sum(1 for r in results if r.has_license)
        return {
            "total": len(results),
            "licenses_found": licenses_found,
            "results": [
                {
                    "text_preview": text_row[:80],
                    **_license_result_to_dict(res),
                }
                for text_row, res in zip(rows, results)
            ],
        }

    # Case 2: Single text input
    if text is not None:
        if not text.strip():
            raise HTTPException(status_code=400, detail="Empty text provided")

        result = await detect_license(text, threshold)

        if download_report:
            if not _OPENPYXL_AVAILABLE:
                raise HTTPException(
                    status_code=503,
                    detail="openpyxl is not installed. Run: pip install openpyxl",
                )
            detection_result = _license_result_to_detection_result(text, result)
            report_bytes = generate_report_bytes([detection_result])
            return StreamingResponse(
                io.BytesIO(report_bytes),
                media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                headers={"Content-Disposition": "attachment; filename=license_check_report.xlsx"},
            )

        return _license_result_to_dict(result)

    # No input provided
    raise HTTPException(
        status_code=400,
        detail="Provide either 'text' or a file upload",
    )


@app.post("/batch-check")
async def check_license_batch(
    request: BatchLicenseRequest | None = None,
    file: Optional[UploadFile] = File(None),
    threshold: float = Form(0.3),
    download_report: bool = Form(False),
):
    """
    Batch check multiple texts for license content.

    Args:
        request: JSON body with texts array (BatchLicenseRequest)
        file: File upload (csv, xlsx, txt) as alternative input
        threshold: Minimum confidence threshold
        download_report: If True, return Excel report

    Returns:
        Array of license detection results for each input text.
    """
    if not is_available():
        raise HTTPException(
            status_code=503,
            detail="License check service unavailable",
        )

    rows: list[str] = []
    effective_threshold = threshold

    # Case 1: File upload
    if file is not None:
        contents = await file.read()
        filename = file.filename.lower()
        try:
            rows = _read_rows_from_file(filename, contents)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc))
    # Case 2: JSON payload
    elif request is not None and request.texts:
        rows = request.texts
        effective_threshold = request.threshold
    else:
        raise HTTPException(
            status_code=400,
            detail="Provide either 'texts' in JSON body or a file upload",
        )

    if not rows:
        raise HTTPException(status_code=400, detail="No texts to process")

    results = await detect_license_batch(rows, effective_threshold)

    should_download = download_report or (request is not None and request.download_report)

    if should_download:
        if not _OPENPYXL_AVAILABLE:
            raise HTTPException(
                status_code=503,
                detail="openpyxl is not installed. Run: pip install openpyxl",
            )
        detection_results = [
            _license_result_to_detection_result(text_row, res)
            for text_row, res in zip(rows, results)
        ]
        report_bytes = generate_report_bytes(detection_results)
        return StreamingResponse(
            io.BytesIO(report_bytes),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": "attachment; filename=license_batch_report.xlsx"},
        )

    licenses_found = sum(1 for r in results if r.has_license)
    return {
        "total": len(results),
        "licenses_found": licenses_found,
        "results": [
            {
                "text_preview": text_row[:80],
                **_license_result_to_dict(res),
            }
            for text_row, res in zip(rows, results)
        ],
    }
