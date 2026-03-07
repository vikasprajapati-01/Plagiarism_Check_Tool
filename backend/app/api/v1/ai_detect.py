"""AI content detection endpoints."""

import io
from typing import Optional

import pandas as pd
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from app.services.ai_detection import detect_ai_content, detect_ai_batch, is_available

app = APIRouter()


class BatchAIRequest(BaseModel):
    texts: list[str]


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

        return result

    # No input provided
    raise HTTPException(status_code=400, detail="Provide either text or a file upload")

@app.post("/batch-check")
async def check_ai_content_batch(
    request: BatchAIRequest | None = None,
    file: Optional[UploadFile] = File(None),
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