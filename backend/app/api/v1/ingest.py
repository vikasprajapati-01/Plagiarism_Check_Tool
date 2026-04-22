"""Ingestion endpoints — file upload, preprocessing, and batch registration.

Updated from api/v1/ingest.py:
  - Imports now use the renamed preprocessor.py and exact_match.py modules.
  - Model loading uses app.state instead of calling get_model() per-request.
  - encode_texts now accepts an explicit model parameter.
"""

import io
import logging
import zipfile
from typing import Annotated, List, Optional

import pandas as pd
from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse

from app.services.preprocessor import preprocess_texts, read_all_text_from_file
from app.services.exact_match import sha256_hash
from app.services.semantic_match import encode_texts
from app.storage.repository import (
    async_create_batch,
    async_insert_embeddings,
    insert_reference_text_with_position,
    _get_pool,
)

logger = logging.getLogger(__name__)
router = APIRouter()

_EXCEL_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _collect_rows_from_uploads(
    files: List[UploadFile],
) -> tuple[List[str], List[dict]]:
    """Read all text rows from a list of uploaded files.

    Returns (rows, file_summary) where file_summary is per-file metadata.
    """
    all_rows: List[str] = []
    file_summary: List[dict] = []

    for upload in files:
        contents = await upload.read()
        try:
            rows, columns = read_all_text_from_file(upload.filename or "upload.txt", contents)
        except Exception as exc:
            raise HTTPException(
                status_code=400,
                detail=f"Error reading '{upload.filename}': {exc}",
            ) from exc
        all_rows.extend(rows)
        file_summary.append({
            "filename": upload.filename,
            "columns_read": columns,
            "row_count": len(rows),
        })

    return all_rows, file_summary


# ── Preview endpoint ──────────────────────────────────────────────────────────

@router.post("/input/data")
async def input_data(
    files: Annotated[
        List[UploadFile],
        File(description="One or more CSV / XLSX / TXT files."),
    ] = [],
    texts: Optional[str] = Form(None),
):
    """Accept files or comma-separated text and return original + preprocessed data."""
    rows: List[str] = []
    file_summary: List[dict] = []

    if files:
        rows, file_summary = await _collect_rows_from_uploads(files)
    elif texts:
        rows = [t.strip() for t in texts.split(",") if t.strip()]
        file_summary = [{"filename": "direct_input", "columns_read": ["text"], "row_count": len(rows)}]
    else:
        return {"status": "No input provided"}

    cleaned_rows = preprocess_texts(rows)

    return {
        "total_rows": len(rows),
        "total_files": len(file_summary),
        "files": file_summary,
        "status": "Data processed successfully",
        "original_data": rows,
        "preprocessed_data": cleaned_rows,
    }


# ── Preprocess + optional download ───────────────────────────────────────────

@router.post("/preprocess")
async def preprocess_data(
    files: Annotated[
        List[UploadFile],
        File(description="One or more CSV / XLSX / TXT files."),
    ] = [],
    texts: Optional[str] = Form(None),
    download_format: str = Form("none"),  # "none" | "csv" | "excel" | "both"
    preview_limit: int = Form(50),
):
    """Normalize and clean text. Optionally download as CSV or Excel."""
    rows: List[str] = []
    file_summary: List[dict] = []

    if files:
        rows, file_summary = await _collect_rows_from_uploads(files)
    elif texts:
        rows = [t.strip() for t in texts.split(",") if t.strip()]
        file_summary = [{"filename": "direct_input", "columns_read": ["text"], "row_count": len(rows)}]
    else:
        raise HTTPException(status_code=400, detail="Provide at least one file or text input.")

    if not rows:
        raise HTTPException(status_code=400, detail="No text found in the provided input.")

    cleaned_rows = preprocess_texts(rows)
    fmt = download_format.lower()

    def _make_df() -> pd.DataFrame:
        source_labels: List[str] = []
        for fs in file_summary:
            source_labels.extend([fs["filename"]] * fs["row_count"])
        return pd.DataFrame({
            "source_file": source_labels,
            "original_text": rows,
            "cleaned_text": cleaned_rows,
        })

    def _make_csv_bytes() -> bytes:
        return _make_df().to_csv(index=False).encode("utf-8")

    def _make_excel_bytes() -> bytes:
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as writer:
            _make_df().to_excel(writer, index=False, sheet_name="Preprocessed")
        return buf.getvalue()

    if fmt == "csv":
        return StreamingResponse(
            io.BytesIO(_make_csv_bytes()),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=preprocessed_data.csv"},
        )

    if fmt in ("excel", "xlsx"):
        return StreamingResponse(
            io.BytesIO(_make_excel_bytes()),
            media_type=_EXCEL_MEDIA_TYPE,
            headers={"Content-Disposition": "attachment; filename=preprocessed_data.xlsx"},
        )

    if fmt == "both":
        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("preprocessed_data.csv", _make_csv_bytes())
            zf.writestr("preprocessed_data.xlsx", _make_excel_bytes())
        return StreamingResponse(
            io.BytesIO(zip_buf.getvalue()),
            media_type="application/zip",
            headers={"Content-Disposition": "attachment; filename=preprocessed_data.zip"},
        )

    # Default: JSON preview
    preview = [
        {"original": orig, "cleaned": clean}
        for orig, clean in list(zip(rows, cleaned_rows))[:preview_limit]
    ]

    return {
        "status": "ok",
        "total_files": len(file_summary),
        "files": file_summary,
        "total_entries": len(rows),
        "preview_shown": len(preview),
        "note": (
            f"Showing first {preview_limit} of {len(rows)} entries. "
            "Use download_format=csv|excel|both for the full dataset."
            if len(rows) > preview_limit else "All entries shown."
        ),
        "preview": preview,
    }


# ── Reference batch registration ──────────────────────────────────────────────

@router.post("/reference/register")
async def register_reference(
    request: Request,
    files: Annotated[
        List[UploadFile],
        File(description="One or more CSV / XLSX / TXT files."),
    ] = [],
    texts: Optional[str] = Form(None),
    batch_name: Optional[str] = Form(None),
    build_embeddings: bool = Form(True),
    merge_files: bool = Form(False),
):
    """Register one or more files as reference batches in the database.

    - merge_files=False (default): each file becomes its own batch.
    - merge_files=True: all files are merged into a single batch.
    """
    if not files and not texts:
        return {"status": "No reference input provided"}

    sbert_model = getattr(request.app.state, "sbert_model", None)

    if texts and not files:
        text_entries = []
        for idx, raw_text in enumerate([t.strip() for t in texts.split(",") if t.strip()], start=1):
            cleaned_text = preprocess_texts([raw_text])[0]
            text_entries.append(
                {
                    "text": raw_text,
                    "cleaned_text": cleaned_text,
                    "sha256": sha256_hash(cleaned_text),
                    "source_file": "direct_input",
                    "row_number": idx,
                    "column_name": "text",
                    "cell_ref": f"A{idx}",
                }
            )
        batch = await _register_single_batch(
            text_entries,
            batch_name or "direct_input",
            "direct_input",
            build_embeddings,
            sbert_model,
        )
        return {
            "batches": [batch],
            "total_entries": batch["entries_registered"],
        }

    if merge_files:
        merged_entries = []
        for upload in files:
            contents = await upload.read()
            try:
                merged_entries.extend(
                    read_all_text_from_file(upload.filename or "upload.txt", contents)
                )
            except Exception as exc:
                raise HTTPException(
                    status_code=400,
                    detail=f"Error reading '{upload.filename}': {exc}",
                ) from exc

        merged_name = batch_name or "merged_batch"
        batch = await _register_single_batch(
            merged_entries,
            merged_name,
            merged_name,
            build_embeddings,
            sbert_model,
        )
        return {
            "batches": [batch],
            "total_entries": batch["entries_registered"],
        }

    batches = []
    total_entries = 0
    for i, upload in enumerate(files):
        contents = await upload.read()
        try:
            entries = read_all_text_from_file(upload.filename or "upload.txt", contents)
        except Exception as exc:
            raise HTTPException(
                status_code=400,
                detail=f"Error reading '{upload.filename}': {exc}",
            ) from exc

        name = (
            f"{batch_name}-{i + 1}" if batch_name and len(files) > 1
            else batch_name or upload.filename
        )
        batch = await _register_single_batch(
            entries,
            name,
            upload.filename or name,
            build_embeddings,
            sbert_model,
        )
        total_entries += batch["entries_registered"]
        batches.append(batch)

    return {"batches": batches, "total_entries": total_entries}


async def _register_single_batch(
    entries: List[dict],
    batch_name: Optional[str],
    file_label: Optional[str],
    build_embeddings: bool,
    sbert_model,
) -> dict:
    """Insert one batch of rows into the database and optionally build embeddings."""
    batch_id = await async_create_batch(batch_name)
    pool = await _get_pool()

    ref_ids: List[str] = []
    cleaned_rows: List[str] = []

    for entry in entries:
        raw_text = entry.get("text", "")
        cleaned_text = entry.get("cleaned_text", "")
        sha256 = entry.get("sha256") or sha256_hash(cleaned_text)
        source_file = entry.get("source_file")
        row_number = entry.get("row_number")
        column_name = entry.get("column_name")
        cell_ref = entry.get("cell_ref")

        ref_id = await insert_reference_text_with_position(
            pool,
            batch_id,
            raw_text,
            cleaned_text,
            sha256,
            source_file,
            row_number,
            column_name,
            cell_ref,
            None,
            None,
        )
        ref_ids.append(ref_id)
        cleaned_rows.append(cleaned_text)

    embeddings_built = False
    if build_embeddings and sbert_model is not None:
        emb_vecs = encode_texts(cleaned_rows, model=sbert_model, do_preprocess=False)
        pairs = [(rid, vec) for rid, vec in zip(ref_ids, emb_vecs)]
        await async_insert_embeddings(pairs)
        embeddings_built = True

    return {
        "batch_id": batch_id,
        "batch_name": batch_name,
        "file": file_label,
        "entries_registered": len(entries),
    }
