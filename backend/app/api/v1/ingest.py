"""Ingestion endpoints for uploading or passing raw text data."""

import io
import os
from typing import Iterable, Optional

import pandas as pd
from fastapi import APIRouter, File, Form, UploadFile

from app.services.preprocess import preprocess_texts
from app.services.detect import sha256_hash
from app.services.embeddings import get_model, encode_texts, is_available
from app.storage.repository import (
	async_create_batch,
	async_insert_embeddings,
	async_insert_reference_texts,
)

app = APIRouter()


@app.get("/")
async def ingest_root():
	return {"message": "Ingest endpoint"}



def _read_rows_from_file(filename: str, contents: bytes) -> Iterable[str]:
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


@app.post("/input/data")
async def input_data(
	file: Optional[UploadFile] = File(None),
	texts: Optional[str] = Form(None)
):
	rows = []

	# Case 1: File upload
	if file:
		contents = await file.read()
		filename = file.filename.lower()

		try:
			rows = list(_read_rows_from_file(filename, contents))
		except Exception as e:  # pragma: no cover - passthrough of parsing errors
			return {"status": "File processing error", "error": str(e)}

	# Case 2: Direct text input
	elif texts:
		rows = [t.strip() for t in texts.split(",") if t.strip()]

	# No input provided
	else:
		return {"status": "No input provided"}

	cleaned_rows = preprocess_texts(rows)

	return {
		"total_rows": len(rows),
		"status": "Data processed successfully",
		"original_data": rows,
		"preprocessed_data": cleaned_rows,
	}


@app.post("/reference/register")
async def register_reference(
	file: Optional[UploadFile] = File(None),
	texts: Optional[str] = Form(None),
	batch_name: Optional[str] = Form(None),
	build_embeddings: bool = Form(True),
):
	rows = []

	if file:
		contents = await file.read()
		filename = file.filename.lower()
		try:
			rows = list(_read_rows_from_file(filename, contents))
		except Exception as e:
			return {"status": "File processing error", "error": str(e)}
	elif texts:
		rows = [t.strip() for t in texts.split(",") if t.strip()]
	else:
		return {"status": "No reference input provided"}

	cleaned_rows = preprocess_texts(rows)
	hashes = [sha256_hash(r) for r in cleaned_rows]

	batch_id = await async_create_batch(batch_name)
	items = zip(rows, cleaned_rows, hashes, [None] * len(rows), [None] * len(rows))
	ref_ids = await async_insert_reference_texts(batch_id, items)

	embeddings_built = False
	model_name_used = None

	if build_embeddings and is_available():
		model = get_model()
		model_name_used = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
		emb_vecs = encode_texts(cleaned_rows, preprocess=False)  # already cleaned
		pairs = [(rid, vec) for rid, vec in zip(ref_ids, emb_vecs)]
		await async_insert_embeddings(pairs)
		embeddings_built = True

	return {
		"status": "Reference batch registered",
		"batch_id": batch_id,
		"total_rows": len(rows),
		"embeddings_built": embeddings_built,
		"model": model_name_used,
	}

