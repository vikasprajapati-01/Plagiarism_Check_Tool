"""AI content detection endpoints."""

import io
import zipfile
from typing import Optional

import pandas as pd
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from app.services.ai_detection import detect_ai_content, detect_ai_batch, is_available
from app.services.preprocess import read_all_text_from_file
from app.services.reports import (
    DetectionResult,
    classify_risk,
    generate_report_bytes,
    generate_report_csv_bytes,
    _OPENPYXL_AVAILABLE,
)
from fastapi.responses import StreamingResponse

app = APIRouter()


class BatchAIRequest(BaseModel):
    texts: list[str]
    download_report: bool = False
    download_format: str = "excel"


_EXCEL_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _build_report_response(
    results: list[DetectionResult],
    base_filename: str,
    download_format: str | None,
):
    """Create a download response for excel, csv, or both."""
    fmt = (download_format or "excel").lower()

    if fmt == "none":
        return None

    if fmt not in {"excel", "xlsx", "csv", "both"}:
        raise HTTPException(status_code=400, detail="Invalid download_format. Use 'excel', 'csv', 'both', or 'none'")

    if fmt in {"excel", "xlsx"}:
        if not _OPENPYXL_AVAILABLE:
            raise HTTPException(status_code=503, detail="openpyxl is not installed. Run: pip install openpyxl")
        report_bytes = generate_report_bytes(results)
        return StreamingResponse(
            io.BytesIO(report_bytes),
            media_type=_EXCEL_MEDIA_TYPE,
            headers={"Content-Disposition": f"attachment; filename={base_filename}.xlsx"},
        )

    if fmt == "csv":
        report_bytes = generate_report_csv_bytes(results)
        return StreamingResponse(
            io.BytesIO(report_bytes),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={base_filename}.csv"},
        )

    # fmt == "both"
    if not _OPENPYXL_AVAILABLE:
        raise HTTPException(status_code=503, detail="openpyxl is not installed. Run: pip install openpyxl")

    excel_bytes = generate_report_bytes(results)
    csv_bytes = generate_report_csv_bytes(results)
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f"{base_filename}.xlsx", excel_bytes)
        zf.writestr(f"{base_filename}.csv", csv_bytes)

    return StreamingResponse(
        io.BytesIO(zip_buffer.getvalue()),
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={base_filename}_reports.zip"},
    )


@app.get("/")
async def ai_detect_root():
    return {
        "message": "AI Detection endpoint",
        "model": "openai-community/roberta-large-openai-detector",
        "available": is_available(),
    }


@app.post("/check")
async def check_ai_content(
    text: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
    download_report: bool = Form(False),
    download_format: str = Form("excel"),
):
    if not is_available():
        raise HTTPException(
            status_code=503,
            detail="AI detection model unavailable. Install: pip install transformers torch",
        )

    # Case 1: file upload → batch detect across all text columns
    if file is not None:
        contents = await file.read()
        try:
            rows, columns_read = read_all_text_from_file(file.filename, contents)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc))

        if not rows:
            raise HTTPException(status_code=400, detail="File contained no usable text")

        results = await detect_ai_batch(rows)
        if download_report:
            detection_results = []
            for text_row, res in zip(rows, results):
                is_ai = res["label"] == "AI"
                confidence = res["confidence"]
                detection_results.append(DetectionResult(
                    text=text_row,
                    is_duplicate=is_ai,
                    similarity_scores={"ai_confidence": confidence},
                    risk_level=classify_risk(confidence) if is_ai else "none",
                    detection_method="ai",
                    notes=f"Label: {res['label']} | Raw: {res['raw_label']} | Confidence: {confidence:.2%}",
                ))
            response = _build_report_response(
                detection_results,
                base_filename="ai_detection_report",
                download_format=download_format,
            )
            if response:
                return response
        return {
            "total": len(results),
            "columns_read": columns_read,
            "results": [
                {"text_preview": text_row[:80], **res}
                for text_row, res in zip(rows, results)
            ],
        }

    # Case 2: single text input
    if text is not None:
        result = await detect_ai_content(text)

        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])

        if download_report:
            is_ai = result["label"] == "AI"
            confidence = result["confidence"]
            detection_result = DetectionResult(
                text=text,
                is_duplicate=is_ai,
                similarity_scores={"ai_confidence": confidence},
                risk_level=classify_risk(confidence) if is_ai else "none",
                detection_method="ai",
                notes=f"Label: {result['label']} | Raw: {result['raw_label']} | Confidence: {confidence:.2%}",
            )
            response = _build_report_response(
                [detection_result],
                base_filename="ai_detection_report",
                download_format=download_format,
            )
            if response:
                return response

        return result

    # No input provided
    raise HTTPException(status_code=400, detail="Provide either text or a file upload")


@app.post("/batch-check")
async def check_ai_content_batch(
    request: BatchAIRequest | None = None,
    file: Optional[UploadFile] = File(None),
    download_report: bool = Form(False),
    download_format: str = Form("excel"),
):
    if not is_available():
        raise HTTPException(
            status_code=503,
            detail="AI detection model unavailable. Install: pip install transformers torch",
        )

    rows: list[str] = []
    columns_read: list[str] = []

    # Case 1: file upload — read all text columns
    if file is not None:
        contents = await file.read()
        try:
            rows, columns_read = read_all_text_from_file(file.filename, contents)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc))
    # Case 2: JSON payload of texts
    elif request is not None and request.texts:
        rows = request.texts
        columns_read = ["direct_input"]
    else:
        raise HTTPException(status_code=400, detail="Provide either texts or a file upload")

    if not rows:
        raise HTTPException(status_code=400, detail="No texts to process")

    results = await detect_ai_batch(rows)

    effective_format = download_format
    if request is not None:
        effective_format = request.download_format or effective_format

    should_download = download_report or (request is not None and request.download_report)

    if should_download:
        detection_results = []
        for text_row, res in zip(rows, results):
            is_ai = res["label"] == "AI"
            confidence = res["confidence"]
            detection_results.append(DetectionResult(
                text=text_row,
                is_duplicate=is_ai,
                similarity_scores={"ai_confidence": confidence},
                risk_level=classify_risk(confidence) if is_ai else "none",
                detection_method="ai",
                notes=f"Label: {res['label']} | Raw: {res['raw_label']} | Confidence: {confidence:.2%}",
            ))
        response = _build_report_response(
            detection_results,
            base_filename="ai_batch_detection_report",
            download_format=effective_format,
        )
        if response:
            return response

    return {
        "total": len(results),
        "columns_read": columns_read,
        "results": [
            {
                "text_preview": text_row[:80],
                **result,
            }
            for text_row, result in zip(rows, results)
        ],
    }