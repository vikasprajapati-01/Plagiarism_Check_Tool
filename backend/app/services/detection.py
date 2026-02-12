"""Exact duplicate checks using SHA-256 on cleaned text."""

import hashlib
from typing import Optional

from app.services.preprocess import preprocess_text
from app.storage.repository import async_fetch_hashes_by_batch, fetch_hashes_by_batch


def sha256_hash(text: str) -> str:
	return hashlib.sha256(text.encode("utf-8")).hexdigest()


def is_exact_duplicate_sync(text: str, batch_id: str) -> bool:
	"""Sync exact match against a batch."""
	cleaned = preprocess_text(text)
	text_hash = sha256_hash(cleaned)
	hashes = set(fetch_hashes_by_batch(batch_id))
	return text_hash in hashes


async def is_exact_duplicate(text: str, batch_id: str) -> bool:
	"""Async exact match against a batch."""
	cleaned = preprocess_text(text)
	text_hash = sha256_hash(cleaned)
	hashes = set(await async_fetch_hashes_by_batch(batch_id))
	return text_hash in hashes
