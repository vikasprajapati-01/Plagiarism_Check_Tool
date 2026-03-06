"""AI content detection endpoints."""

from fastapi import APIRouter, Form, HTTPException
from pydantic import BaseModel

from app.services.ai_detection import detect_ai_content, detect_ai_batch, is_available

app = APIRouter()


class BatchAIRequest(BaseModel):
    texts: list[str]


@app.get("/")
async def ai_detect_root():
    return {
        "message": "AI Detection endpoint",
        "model": "roberta-base-openai-detector",
        "available": is_available(),
    }


@app.post("/check")
async def check_ai_content(text: str = Form(...)):
    """
    Detect whether a single text is AI-generated or Human-written.

    Returns:
        - label:      "AI" or "Human"
        - confidence: float (0.0 – 1.0)
        - raw_label:  "Fake" or "Real" (original model output)
    """
    if not is_available():
        raise HTTPException(
            status_code=503,
            detail="AI detection model unavailable. Install: pip install transformers torch",
        )

    result = await detect_ai_content(text)

    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])

    return result


@app.post("/batch-check")
async def check_ai_content_batch(request: BatchAIRequest):
    """
    Detect AI content for a batch of texts.

    Returns a list of results in the same order as the input texts.
    Each result contains label, confidence, and raw_label.
    """
    if not is_available():
        raise HTTPException(
            status_code=503,
            detail="AI detection model unavailable. Install: pip install transformers torch",
        )

    if not request.texts:
        raise HTTPException(status_code=400, detail="texts list cannot be empty")

    results = await detect_ai_batch(request.texts)

    return {
        "total": len(results),
        "results": [
            {
                "text_preview": text[:80],
                **result,
            }
            for text, result in zip(request.texts, results)
        ],
    }