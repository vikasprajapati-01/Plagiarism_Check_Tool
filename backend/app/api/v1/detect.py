"""Detection endpoints (exact duplicate for now)."""

import uuid
from pydantic import BaseModel

from fastapi import FastAPI, Form, HTTPException

from app.services.detect import is_exact_duplicate
from app.services.fuzzy import is_fuzzy_duplicate, find_fuzzy_duplicates_in_batch
from app.storage.repository import async_fetch_all_texts_by_batch

app = FastAPI(title="Detect API")


# Pydantic model for batch fuzzy request
class BatchFuzzyRequest(BaseModel):
    texts: list[str]
    threshold: float = 0.85


@app.post("/detect/exact")
async def detect_exact(text: str = Form(...), batch_id: str | None = Form(None)):
    if batch_id:
        try:
            uuid.UUID(batch_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="batch_id must be a valid UUID")

    is_dup = await is_exact_duplicate(text, batch_id)
    return {
        "is_duplicate": is_dup,
        "batch_id": batch_id,
        "scope": "batch" if batch_id else "global",
    }


@app.post("/detect/fuzzy")
async def detect_fuzzy_duplicate(
    text: str = Form(...),
    batch_id: str | None = Form(None),
    threshold: float = Form(0.85)
):
    """
    Detect fuzzy (near) duplicates using multiple similarity algorithms.
    
    Args:
        text: The text to check for duplicates
        batch_id: Optional batch ID to limit search scope
        threshold: Similarity threshold (0.0-1.0, default 0.85)
    
    Returns:
        JSON with duplicate status, matched text, and similarity scores
    """
    if batch_id:
        try:
            uuid.UUID(batch_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="batch_id must be a valid UUID")
    
    # Fetch candidate texts from database
    candidates = await async_fetch_all_texts_by_batch(batch_id) if batch_id else []
    
    # Check for fuzzy duplicates
    is_dup, matched_text, scores = await is_fuzzy_duplicate(
        text,
        candidates,
        threshold=threshold
    )
    
    return {
        "is_duplicate": is_dup,
        "matched_text": matched_text,
        "similarity_scores": scores,
        "threshold": threshold,
        "batch_id": batch_id,
        "scope": "batch" if batch_id else "global"
    }


@app.post("/detect/batch-fuzzy")
async def detect_batch_fuzzy_duplicates(request: BatchFuzzyRequest):
    """
    Find all fuzzy duplicate pairs within a batch of texts.
    
    Useful for detecting duplicates in Excel uploads.
    
    Request body (JSON):
    {
        "texts": ["text1", "text2", "text3"],
        "threshold": 0.85
    }
    """
    duplicates = find_fuzzy_duplicates_in_batch(request.texts, threshold=request.threshold)
    
    return {
        "total_texts": len(request.texts),
        "duplicate_pairs": len(duplicates),
        "duplicates": [
            {
                "index1": i,
                "index2": j,
                "text1": request.texts[i],
                "text2": request.texts[j],
                "scores": scores
            }
            for i, j, scores in duplicates
        ]
    }