"""Detection endpoints for exact and fuzzy matching."""

import uuid

from fastapi import APIRouter, Form, HTTPException
from pydantic import BaseModel

from app.services.detect import is_exact_duplicate
from app.services.fuzzy import is_fuzzy_duplicate, find_fuzzy_duplicates_in_batch
from app.storage.repository import async_fetch_all_texts_by_batch, async_get_batch_id_by_name

app = APIRouter()


class BatchFuzzyRequest(BaseModel):
    texts: list[str]
    threshold: float = 0.85


@app.get("/")
async def detect_root():
    return {"message": "Detect endpoint"}


@app.post("/exact")
async def detect_exact(
    text: str = Form(...),
    batch_id: str | None = Form(None),
    batch_name: str | None = Form(None),
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
    threshold: float = Form(0.85)
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