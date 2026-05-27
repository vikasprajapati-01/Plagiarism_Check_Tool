"""Ingestion endpoints — file upload, preprocessing, and batch registration.

Updated from api/v1/ingest.py:
  - Imports now use the renamed preprocessor.py and exact_match.py modules.
  - Model loading uses app.state instead of calling get_model() per-request.
  - encode_texts now accepts an explicit model parameter.
"""

import io
import logging
import os
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
) -> tuple[List[dict], List[dict]]:
    """Read all text entries from a list of uploaded files.

    Returns (entries, file_summary) where file_summary is per-file metadata.
    """
    all_entries: List[dict] = []
    file_summary: List[dict] = []

    for upload in files:
        contents = await upload.read()
        try:
            entries = read_all_text_from_file(upload.filename or "upload.txt", contents)
        except Exception as exc:
            raise HTTPException(
                status_code=400,
                detail=f"Error reading '{upload.filename}': {exc}",
            ) from exc
        rows = [e.get("text", "") for e in entries if e.get("text")]
        columns = sorted({str(e.get("column_name")) for e in entries if e.get("column_name")})
        if not columns:
            columns = ["text"]

        all_entries.extend(entries)
        file_summary.append({
            "filename": upload.filename,
            "columns_read": columns,
            "row_count": len(rows),
        })

    return all_entries, file_summary


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
        entries, file_summary = await _collect_rows_from_uploads(files)
        rows = [e.get("text", "") for e in entries if e.get("text")]
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
    files_payload: List[tuple[str, bytes]] = []

    if files:
        for upload in files:
            files_payload.append((upload.filename or "upload.txt", await upload.read()))
    elif texts:
        rows = [t.strip() for t in texts.split(",") if t.strip()]
        files_payload = [("direct_input.txt", "\n".join(rows).encode("utf-8"))]
    else:
        raise HTTPException(status_code=400, detail="Provide at least one file or text input.")

    if not files_payload:
        raise HTTPException(status_code=400, detail="No text found in the provided input.")

    fmt = download_format.lower()

    def _read_file_frames(filename: str, contents: bytes) -> dict[str, pd.DataFrame]:
        name = filename or "upload.txt"
        lower = name.lower()

        if lower.endswith(".txt"):
            lines = contents.decode("utf-8", errors="replace").splitlines()
            return {"text": pd.DataFrame({"text": [ln for ln in lines if ln.strip()]})}

        if lower.endswith(".csv"):
            df = pd.read_csv(io.BytesIO(contents))
            return {"Sheet1": df}

        if lower.endswith((".xlsx", ".xls")):
            sheets = pd.read_excel(io.BytesIO(contents), sheet_name=None)
            return sheets or {"Sheet1": pd.DataFrame()}

        raise ValueError("Unsupported file format. Supported: CSV, XLSX, XLS, TXT")

    def _cleaned_name(filename: str, ext: str) -> str:
        base = os.path.splitext(os.path.basename(filename))[0] or "cleaned"
        return f"{base}_cleaned{ext}"

    def _row_signature(values: List[object]) -> str:
        parts = [str(v).strip() for v in values]
        joined = " | ".join(parts).strip()
        return joined

    def _dedupe_frames_across_files(
        files_data: List[tuple[str, dict[str, pd.DataFrame]]]
    ) -> dict[str, dict[str, pd.DataFrame]]:
        seen: set[str] = set()
        cleaned: dict[str, dict[str, pd.DataFrame]] = {}

        for fname, sheets in files_data:
            cleaned[fname] = {}
            for sheet_name, df in sheets.items():
                if df is None or df.empty:
                    cleaned[fname][sheet_name] = df
                    continue

                keep_rows = []
                for _, row in df.iterrows():
                    sig = _row_signature(row.tolist())
                    if not sig:
                        continue
                    if sig in seen:
                        continue
                    seen.add(sig)
                    keep_rows.append(row)

                if keep_rows:
                    cleaned_df = pd.DataFrame(keep_rows, columns=df.columns)
                else:
                    cleaned_df = df.iloc[0:0]

                cleaned[fname][sheet_name] = cleaned_df

        return cleaned

    def _make_excel_bytes(sheets: dict[str, pd.DataFrame]) -> bytes:
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as writer:
            for sheet_name, df in sheets.items():
                safe_name = sheet_name or "Sheet1"
                df.to_excel(writer, index=False, sheet_name=safe_name[:31])
        return buf.getvalue()

    def _make_csv_bytes(df: pd.DataFrame) -> bytes:
        return df.to_csv(index=False).encode("utf-8")

    def _make_txt_bytes(df: pd.DataFrame) -> bytes:
        if df.empty:
            return b""
        col = df.columns[0] if len(df.columns) else "text"
        return "\n".join(df[col].astype(str).tolist()).encode("utf-8")

    files_data: List[tuple[str, dict[str, pd.DataFrame]]] = []
    for fname, contents in files_payload:
        try:
            files_data.append((fname, _read_file_frames(fname, contents)))
        except Exception as exc:
            raise HTTPException(
                status_code=400,
                detail=f"Error reading '{fname}': {exc}",
            ) from exc

    cleaned_by_file = _dedupe_frames_across_files(files_data)

    def _build_preview(files_map: dict[str, dict[str, pd.DataFrame]]) -> dict:
        total_entries = 0
        files_preview = []
        for fname, sheets in files_map.items():
            sheet_previews = []
            file_total = 0
            for sheet_name, df in sheets.items():
                count = 0 if df is None else len(df.index)
                file_total += count
                total_entries += count
                headers = [str(c) for c in (df.columns.tolist() if df is not None else [])]
                rows_preview = []
                if df is not None and not df.empty:
                    preview_df = df.head(preview_limit).fillna("")
                    rows_preview = preview_df.astype(str).values.tolist()
                sheet_previews.append({
                    "sheet_name": sheet_name or "Sheet1",
                    "headers": headers,
                    "rows": rows_preview,
                    "total_entries": count,
                })
            files_preview.append({
                "filename": fname,
                "total_entries": file_total,
                "sheets": sheet_previews,
            })
        return {
            "total_entries": total_entries,
            "files": files_preview,
        }

    if fmt != "none":
        if len(cleaned_by_file) == 1:
            filename = next(iter(cleaned_by_file.keys()), "cleaned")
            sheets = cleaned_by_file[filename]
            ext = os.path.splitext(filename)[1].lower()
            if ext in (".xlsx", ".xls", ".csv", ".txt"):
                if ext in (".xlsx", ".xls"):
                    return StreamingResponse(
                        io.BytesIO(_make_excel_bytes(sheets)),
                        media_type=_EXCEL_MEDIA_TYPE,
                        headers={"Content-Disposition": f"attachment; filename={_cleaned_name(filename, '.xlsx')}"},
                    )
                if ext == ".csv":
                    first_sheet = next(iter(sheets.values()), pd.DataFrame())
                    return StreamingResponse(
                        io.BytesIO(_make_csv_bytes(first_sheet)),
                        media_type="text/csv",
                        headers={"Content-Disposition": f"attachment; filename={_cleaned_name(filename, '.csv')}"},
                    )
                if ext == ".txt":
                    first_sheet = next(iter(sheets.values()), pd.DataFrame())
                    return StreamingResponse(
                        io.BytesIO(_make_txt_bytes(first_sheet)),
                        media_type="text/plain",
                        headers={"Content-Disposition": f"attachment; filename={_cleaned_name(filename, '.txt')}"},
                    )

        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for fname, sheets in cleaned_by_file.items():
                ext = os.path.splitext(fname)[1].lower()
                if ext in (".xlsx", ".xls"):
                    zf.writestr(_cleaned_name(fname, ".xlsx"), _make_excel_bytes(sheets))
                elif ext == ".csv":
                    first_sheet = next(iter(sheets.values()), pd.DataFrame())
                    zf.writestr(_cleaned_name(fname, ".csv"), _make_csv_bytes(first_sheet))
                elif ext == ".txt":
                    first_sheet = next(iter(sheets.values()), pd.DataFrame())
                    zf.writestr(_cleaned_name(fname, ".txt"), _make_txt_bytes(first_sheet))
        return StreamingResponse(
            io.BytesIO(zip_buf.getvalue()),
            media_type="application/zip",
            headers={"Content-Disposition": "attachment; filename=cleaned_files.zip"},
        )

    # Default: JSON preview
    preview_payload = _build_preview(cleaned_by_file)
    total_entries = preview_payload["total_entries"]
    preview_shown = sum(len(s["rows"]) for f in preview_payload["files"] for s in f["sheets"])
    return {
        "status": "ok",
        "total_files": len(preview_payload["files"]),
        "total_entries": total_entries,
        "preview_shown": preview_shown,
        "note": (
            f"Showing first {preview_limit} rows per sheet. "
            "Download to get the full cleaned files."
            if total_entries > preview_limit else "All entries shown."
        ),
        "files": preview_payload["files"],
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
