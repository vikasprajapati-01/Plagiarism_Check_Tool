"""AI content detection endpoints."""

import io
from typing import Optional

import pandas as pd
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from app.services.ai_detection import detect_ai_content, detect_ai_batch, is_available
from app.services.reports import DetectionResult, classify_risk, generate_report_bytes, _OPENPYXL_AVAILABLE
from fastapi.responses import StreamingResponse

app = APIRouter()


class BatchAIRequest(BaseModel):
    texts: list[str]
    download_report: bool = False


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
    raise ValueError("Unsupported file format")


@app.get("/")
async def ai_detect_root():
    return {
        "message": "AI Detection endpoint",
        "model": "roberta-base-openai-detector",
        "available": is_available(),
    }


@app.post("/check")
async def check_ai_content(
    text: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
    download_report: bool = Form(False),
):
    if not is_available():
        raise HTTPException(
            status_code=503,
            detail="AI detection model unavailable. Install: pip install transformers torch",
        )

    # Case 1: file upload → batch detect
    if file is not None:
        contents = await file.read()
        filename = file.filename.lower()
        try:
            rows = _read_rows_from_file(filename, contents)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc))

        if not rows:
            raise HTTPException(status_code=400, detail="File contained no usable text")

        results = await detect_ai_batch(rows)
        if download_report:
            if not _OPENPYXL_AVAILABLE:
                raise HTTPException(status_code=503, detail="openpyxl is not installed. Run: pip install openpyxl")
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
            report_bytes = generate_report_bytes(detection_results)
            return StreamingResponse(
                io.BytesIO(report_bytes),
                media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                headers={"Content-Disposition": "attachment; filename=ai_detection_report.xlsx"},
            )
        return {
            "total": len(results),
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
            if not _OPENPYXL_AVAILABLE:
                raise HTTPException(status_code=503, detail="openpyxl is not installed. Run: pip install openpyxl")
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
            report_bytes = generate_report_bytes([detection_result])
            return StreamingResponse(
                io.BytesIO(report_bytes),
                media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                headers={"Content-Disposition": "attachment; filename=ai_detection_report.xlsx"},
            )

        return result

    # No input provided
    raise HTTPException(status_code=400, detail="Provide either text or a file upload")

@app.post("/batch-check")
async def check_ai_content_batch(
    request: BatchAIRequest | None = None,
    file: Optional[UploadFile] = File(None),
    download_report: bool = Form(False),
):
    if not is_available():
        raise HTTPException(
            status_code=503,
            detail="AI detection model unavailable. Install: pip install transformers torch",
        )

    rows: list[str] = []

    # Case 1: file upload
    if file is not None:
        contents = await file.read()
        filename = file.filename.lower()
        try:
            rows = _read_rows_from_file(filename, contents)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc))
    # Case 2: JSON payload of texts
    elif request is not None and request.texts:
        rows = request.texts
    else:
        raise HTTPException(status_code=400, detail="Provide either texts or a file upload")

    if not rows:
        raise HTTPException(status_code=400, detail="No texts to process")

    results = await detect_ai_batch(rows)

    should_download = download_report or (request is not None and request.download_report)

    if should_download:
        if not _OPENPYXL_AVAILABLE:
            raise HTTPException(status_code=503, detail="openpyxl is not installed. Run: pip install openpyxl")
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
        report_bytes = generate_report_bytes(detection_results)
        return StreamingResponse(
            io.BytesIO(report_bytes),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": "attachment; filename=ai_batch_detection_report.xlsx"},
        )

    return {
        "total": len(results),
        "results": [
            {
                "text_preview": text[:80],
                **result,
            }
            for text, result in zip(rows, results)
        ],
    }