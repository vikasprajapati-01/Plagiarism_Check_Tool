"""Exact duplicate helpers (hash-based)."""

import hashlib
from typing import Optional

from app.services.preprocess import preprocess_text
from app.storage.repository import (
	async_fetch_all_hashes,
	async_fetch_hashes_by_batch,
	fetch_all_hashes,
	fetch_hashes_by_batch,
)


def sha256_hash(text: str) -> str:
	return hashlib.sha256(text.encode("utf-8")).hexdigest()


def is_exact_duplicate_sync(text: str, batch_id: Optional[str] = None) -> bool:
	cleaned = preprocess_text(text)
	text_hash = sha256_hash(cleaned)
	if batch_id:
		hashes = set(fetch_hashes_by_batch(batch_id))
	else:
		hashes = set(fetch_all_hashes())
	return text_hash in hashes


async def is_exact_duplicate(text: str, batch_id: Optional[str] = None) -> bool:
	cleaned = preprocess_text(text)
	text_hash = sha256_hash(cleaned)
	if batch_id:
		hashes = set(await async_fetch_hashes_by_batch(batch_id))
	else:
		hashes = set(await async_fetch_all_hashes())
	return text_hash in hashes