"""Text normalisation and file-reading utilities for ingestion and detection pipelines.

Logic preserved — identical to services/preprocess.py.
"""

import hashlib
import io
import os
import re
import unicodedata
from typing import Dict, Iterable, List

import pandas as pd


# Lightweight stop word list to drop common fillers.
STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "but", "by", "for", "if", "in", "into",
    "is", "it", "no", "not", "of", "on", "or", "such", "that", "the", "their", "then",
    "there", "these", "they", "this", "to", "was", "will", "with",
}


def _normalize_unicode(text: str) -> str:
    """Collapse visually similar Unicode forms (e.g. full-width) via NFKC."""
    return unicodedata.normalize("NFKC", text)


def preprocess_text(text: str) -> str:
    """Normalize and lightly clean a single text snippet for duplicate checks."""
    if text is None:
        return ""

    normalized = _normalize_unicode(str(text)).lower()

    # Strip punctuation and symbols; keep alphanumerics and whitespace.
    normalized = re.sub(r"[^a-z0-9\s]", " ", normalized)

    # Collapse runs of whitespace and remove stop words.
    tokens = re.split(r"\s+", normalized.strip())
    filtered_tokens = [tok for tok in tokens if tok and tok not in STOP_WORDS]

    return " ".join(filtered_tokens)


def preprocess_texts(texts: Iterable[str]) -> List[str]:
    """Vectorized wrapper over preprocess_text preserving order."""
    return [preprocess_text(text) for text in texts]


# ── Shared File Reader ────────────────────────────────────────────────────────

def read_all_text_from_file(
    filename: str,
    contents: bytes,
) -> List[Dict[str, object]]:
    """Read text values from CSV/XLSX/XLS/TXT with per-cell position metadata."""

    def _column_letter(col_index: int) -> str:
        letters = ""
        index = col_index
        while index >= 0:
            index, remainder = divmod(index, 26)
            letters = chr(65 + remainder) + letters
            index -= 1
        return letters

    def _sha256(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    source_file = os.path.basename(filename)
    filename_lower = filename.lower()

    if filename_lower.endswith(".zip"):
        import zipfile
        entries = []
        try:
            with zipfile.ZipFile(io.BytesIO(contents)) as zf:
                for zip_info in zf.infolist():
                    if zip_info.is_dir():
                        continue
                    inner_filename = zip_info.filename
                    if inner_filename.lower().endswith((".csv", ".xlsx", ".xls", ".txt")):
                        inner_contents = zf.read(zip_info)
                        try:
                            # Use the inner filename as the source
                            extracted_entries = read_all_text_from_file(inner_filename, inner_contents)
                            # Update the source_file to indicate it came from the zip
                            for entry in extracted_entries:
                                entry["source_file"] = f"{source_file}/{entry.get('source_file', inner_filename)}"
                            entries.extend(extracted_entries)
                        except Exception:
                            pass
        except Exception as e:
            raise ValueError(f"Error processing zip file: {e}")
        return entries

    if filename_lower.endswith(".txt"):
        lines = contents.decode("utf-8", errors="replace").splitlines()
        entries: List[Dict[str, object]] = []
        for idx, line in enumerate(lines, start=1):
            raw_text = line.strip()
            if not raw_text:
                continue
            cleaned_text = preprocess_text(raw_text)
            entries.append(
                {
                    "text": raw_text,
                    "cleaned_text": cleaned_text,
                    "sha256": _sha256(cleaned_text),
                    "source_file": source_file,
                    "row_number": idx,
                    "column_name": "text",
                    "cell_ref": f"A{idx}",
                }
            )
        return entries

    if filename_lower.endswith(".csv"):
        df = pd.read_csv(io.BytesIO(contents))
    elif filename_lower.endswith(".xlsx") or filename_lower.endswith(".xls"):
        df = pd.read_excel(io.BytesIO(contents), sheet_name=0)
    else:
        raise ValueError("Unsupported file format. Supported: CSV, XLSX, XLS, TXT")

    skip_names = {
        "s.no",
        "s.no.",
        "sno",
        "sr",
        "sr.no",
        "serial",
        "index",
        "id",
        "#",
        "no.",
    }

    entries: List[Dict[str, object]] = []
    total_rows = len(df.index)

    for col_index, col in enumerate(df.columns):
        col_name = str(col)
        col_name_normalized = col_name.strip().lower().replace(" ", "")
        if col_name_normalized in skip_names:
            continue

        series = df[col]
        if total_rows == 0:
            continue

        empty_mask = series.isna() | series.astype(str).str.strip().eq("")
        numeric_mask = pd.to_numeric(series, errors="coerce").notna() & ~empty_mask

        if empty_mask.mean() > 0.8:
            continue
        if numeric_mask.mean() > 0.8:
            continue

        col_letter = _column_letter(col_index)

        for row_index, value in enumerate(series.tolist(), start=1):
            if value is None or (isinstance(value, float) and pd.isna(value)):
                continue
            raw_text = str(value).strip()
            if not raw_text:
                continue

            cleaned_text = preprocess_text(raw_text)
            row_number = row_index
            cell_ref = f"{col_letter}{row_number + 1}"

            entries.append(
                {
                    "text": raw_text,
                    "cleaned_text": cleaned_text,
                    "sha256": _sha256(cleaned_text),
                    "source_file": source_file,
                    "row_number": row_number,
                    "column_name": col_name,
                    "cell_ref": cell_ref,
                }
            )

    return entries
