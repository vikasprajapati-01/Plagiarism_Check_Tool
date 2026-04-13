"""Ingestion endpoints for uploading or passing raw text data."""

import io
import os
import zipfile
from typing import Annotated, List, Optional

import pandas as pd
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from app.services.preprocess import preprocess_texts, read_all_text_from_file
from app.services.detect import sha256_hash
from app.services.embeddings import get_model, encode_texts, is_available
from app.storage.repository import (
    async_create_batch,
    async_insert_embeddings,
    async_insert_reference_texts,
)

app = APIRouter()

_EXCEL_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@app.get("/")
async def ingest_root():
    return {"message": "Ingest endpoint"}


# ==============================================================================
# HELPERS
# ==============================================================================

async def _collect_rows_from_uploads(
    files: List[UploadFile],
) -> tuple[List[str], List[dict]]:
    """
    Read all text rows from a list of uploaded files.

    Returns:
        rows          – flat list of all text values across all files
        file_summary  – per-file metadata: {filename, columns_read, row_count}
    """
    all_rows: List[str] = []
    file_summary: List[dict] = []

    for upload in files:
        contents = await upload.read()
        try:
            rows, columns = read_all_text_from_file(upload.filename, contents)
        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail=f"Error reading '{upload.filename}': {e}",
            )
        all_rows.extend(rows)
        file_summary.append({
            "filename": upload.filename,
            "columns_read": columns,
            "row_count": len(rows),
        })

    return all_rows, file_summary


# ==============================================================================
# INPUT DATA  — preview + preprocess without storing
# ==============================================================================

@app.post("/input/data")
async def input_data(
    files: Annotated[
        List[UploadFile],
        File(description="One or more CSV / XLSX / TXT files. Click 'Add item' in Swagger to add each file."),
    ] = [],
    texts: Optional[str] = Form(None),
):
    """
    Accept one or more files (CSV/XLSX/TXT) or comma-separated text.
    Returns original and preprocessed data from ALL rows and text columns.
    """
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


# ==============================================================================
# PREPROCESS  — clean file/text and optionally download result
# ==============================================================================

@app.post("/preprocess")
async def preprocess_data(
    files: Annotated[
        List[UploadFile],
        File(description="One or more CSV / XLSX / TXT files. Click 'Add item' in Swagger to add each file."),
    ] = [],
    texts: Optional[str] = Form(None),
    download_format: str = Form("none"),   # "none" | "csv" | "excel" | "both"
    preview_limit: int = Form(50),         # max rows shown in JSON preview
):
    """
    Normalize and clean text from one or more uploaded files or direct text input.

    - Reads ALL text columns from every uploaded CSV / XLSX / XLS / TXT file.
    - Strips punctuation, lowercases, removes stop words (Unicode-safe).
    - Returns a JSON preview of original → cleaned pairs.
    - Use download_format=csv|excel|both to also download the full cleaned dataset.
    """
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

    # ── Build download file ────────────────────────────────────────────────────
    fmt = download_format.lower()

    def _make_df() -> pd.DataFrame:
        source_labels = []
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

    # ── JSON preview (default) ────────────────────────────────────────────────
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
            "Use download_format=csv|excel|both to get the full dataset."
            if len(rows) > preview_limit else
            "All entries shown."
        ),
        "preview": preview,
    }


# ==============================================================================
# REFERENCE REGISTER  — store batches in the database for detection comparisons
# ==============================================================================

@app.post("/reference/register")
async def register_reference(
    files: Annotated[
        List[UploadFile],
        File(description="One or more CSV / XLSX / TXT files. Click 'Add item' in Swagger to add each file."),
    ] = [],
    texts: Optional[str] = Form(None),
    batch_name: Optional[str] = Form(None),
    build_embeddings: bool = Form(True),
    merge_files: bool = Form(False),
):
    """
    Register one or more files as reference batches in the database.

    - merge_files=False (default): each file becomes its own batch
      named after its filename (or batch_name-1, batch_name-2 if batch_name given).
    - merge_files=True: all files are merged into a single batch
      named by batch_name (or 'merged_batch' if not provided).
    """
    if not files and not texts:
        return {"status": "No reference input provided"}

    # ── Direct text input: single batch ───────────────────────────────────────
    if texts and not files:
        rows = [t.strip() for t in texts.split(",") if t.strip()]
        return await _register_single_batch(
            rows=rows,
            columns=["direct_input"],
            batch_name=batch_name,
            build_embeddings=build_embeddings,
        )

    # ── File uploads ──────────────────────────────────────────────────────────
    if merge_files:
        # All files → one batch
        all_rows, file_summary = await _collect_rows_from_uploads(files)
        merged_name = batch_name or "merged_batch"
        result = await _register_single_batch(
            rows=all_rows,
            columns=[f["filename"] for f in file_summary],
            batch_name=merged_name,
            build_embeddings=build_embeddings,
        )
        result["files"] = file_summary
        result["merge_mode"] = True
        return result

    else:
        # Each file → its own batch
        batches = []
        for i, upload in enumerate(files):
            contents = await upload.read()
            try:
                rows, columns = read_all_text_from_file(upload.filename, contents)
            except Exception as e:
                raise HTTPException(
                    status_code=400,
                    detail=f"Error reading '{upload.filename}': {e}",
                )
            # Name: explicit batch_name with suffix, or just the filename
            if batch_name:
                name = f"{batch_name}-{i + 1}" if len(files) > 1 else batch_name
            else:
                name = upload.filename

            result = await _register_single_batch(
                rows=rows,
                columns=columns,
                batch_name=name,
                build_embeddings=build_embeddings,
            )
            batches.append(result)

        return {
            "status": "All batches registered",
            "total_files": len(files),
            "merge_mode": False,
            "batches": batches,
        }


async def _register_single_batch(
    rows: List[str],
    columns: List[str],
    batch_name: Optional[str],
    build_embeddings: bool,
) -> dict:
    """Insert one batch of rows into the database and optionally build embeddings."""
    cleaned_rows = preprocess_texts(rows)
    hashes = [sha256_hash(r) for r in cleaned_rows]

    batch_id = await async_create_batch(batch_name)
    items = zip(rows, cleaned_rows, hashes, [None] * len(rows), [None] * len(rows))
    ref_ids = await async_insert_reference_texts(batch_id, items)

    embeddings_built = False
    model_name_used = None

    if build_embeddings and is_available():
        get_model()
        model_name_used = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
        emb_vecs = encode_texts(cleaned_rows, preprocess=False)
        pairs = [(rid, vec) for rid, vec in zip(ref_ids, emb_vecs)]
        await async_insert_embeddings(pairs)
        embeddings_built = True

    return {
        "status": "Reference batch registered",
        "batch_id": batch_id,
        "batch_name": batch_name,
        "columns_read": columns,
        "total_rows": len(rows),
        "embeddings_built": embeddings_built,
        "model": model_name_used,
    }
