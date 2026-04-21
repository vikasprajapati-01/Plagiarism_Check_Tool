"""Text normalisation and file-reading utilities for ingestion and detection pipelines.

Logic preserved — identical to services/preprocess.py.
"""

import io
import re
import unicodedata
from typing import Iterable, List, Tuple

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
) -> Tuple[List[str], List[str]]:
    """Read every text value from ALL columns in a CSV, XLSX/XLS, or TXT file.

    Pure-numeric columns (e.g. prices, IDs) are automatically skipped.
    Each non-null cell in a text column becomes one entry in the returned list.

    Args:
        filename: Original file name (used to detect format).
        contents: Raw file bytes.

    Returns:
        (rows, columns_read) where
          rows         – flat list of non-null text values from all text columns
          columns_read – names of the columns that were included
    """
    filename = filename.lower()

    if filename.endswith(".txt"):
        lines = contents.decode("utf-8", errors="replace").splitlines()
        rows = [ln.strip() for ln in lines if ln.strip()]
        return rows, ["text"]

    if filename.endswith(".csv"):
        df = pd.read_csv(io.BytesIO(contents), dtype=str)
    elif filename.endswith(".xlsx") or filename.endswith(".xls"):
        df = pd.read_excel(io.BytesIO(contents), dtype=str)
    else:
        raise ValueError("Unsupported file format. Supported: CSV, XLSX, XLS, TXT")

    text_columns: List[str] = []
    rows: List[str] = []

    for col in df.columns:
        col_values = df[col].dropna().astype(str)
        if col_values.empty:
            continue
        # Skip columns where every value is a bare number
        numeric_mask = col_values.str.match(r"^-?\d+(\.\d+)?$")
        if numeric_mask.all():
            continue
        text_columns.append(str(col))
        rows.extend(col_values.tolist())

    # Fallback: if every column looked numeric, include them all anyway
    if not rows:
        for col in df.columns:
            rows.extend(df[col].dropna().astype(str).tolist())
        text_columns = [str(c) for c in df.columns]

    return rows, text_columns
