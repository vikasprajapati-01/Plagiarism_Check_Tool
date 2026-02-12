"""Detection endpoints (exact duplicate for now)."""

import uuid

from fastapi import FastAPI, Form, HTTPException

from app.services.detect import is_exact_duplicate


app = FastAPI(title="Detect API")


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
