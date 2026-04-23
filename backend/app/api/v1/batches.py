"""Batch CRUD endpoints — list, rename, and delete stored reference batches."""

import logging

from fastapi import APIRouter, HTTPException

from app.core.models import BatchInfo, BatchRenameRequest
from app.storage.repository import (
    async_delete_batch,
    async_fetch_all_batches,
    async_rename_batch,
)

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/", response_model=list[BatchInfo])
async def list_batches():
    """Return all stored reference batches with entry counts."""
    rows = await async_fetch_all_batches()
    return [
        BatchInfo(
            id=r["id"],
            name=r.get("name"),
            entry_count=r.get("entry_count", 0),
            created_at=str(r["created_at"]) if r.get("created_at") else None,
        )
        for r in rows
    ]


@router.delete("/{batch_id}", status_code=204)
async def delete_batch(batch_id: str):
    """Delete a batch and all its texts + embeddings (CASCADE)."""
    deleted = await async_delete_batch(batch_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Batch '{batch_id}' not found.")
    logger.info("Batch %s deleted.", batch_id)


@router.patch("/{batch_id}")
async def rename_batch(batch_id: str, body: BatchRenameRequest):
    """Rename a stored batch."""
    updated = await async_rename_batch(batch_id, body.name)
    if not updated:
        raise HTTPException(status_code=404, detail=f"Batch '{batch_id}' not found.")
    return {"batch_id": batch_id, "new_name": body.name}
