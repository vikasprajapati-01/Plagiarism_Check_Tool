"""Combined report endpoint — POST /reports/combined.

Accepts a PipelineResult JSON body and returns a multi-sheet Excel file:
  Sheet 1: Summary
  Sheet 2: Exact Matches
  Sheet 3: Fuzzy Matches
  Sheet 4: Semantic Matches
  Sheet 5: AI Detection
  Sheet 6: Web Scan
  Sheet 7: License Check
"""

import io
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter()

_EXCEL_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

try:
    import pandas as pd
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter
    _EXCEL_AVAILABLE = True
except ImportError:
    _EXCEL_AVAILABLE = False

# ── Colour constants ──────────────────────────────────────────────────────────
_RISK_COLORS = {"high": "FF4C4C", "medium": "FFB347", "low": "FFD700", "none": "90EE90"}
_HEADER_COLOR = "1F4E79"


def _header_fill():
    return PatternFill(start_color=_HEADER_COLOR, end_color=_HEADER_COLOR, fill_type="solid")


def _header_font():
    return Font(bold=True, color="FFFFFF", size=11)


def _thin_border():
    s = Side(style="thin")
    return Border(left=s, right=s, top=s, bottom=s)


def _style_sheet(ws, title: str, df) -> None:
    """Apply standard header styling to one worksheet."""
    ws.insert_rows(1)
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=max(len(df.columns), 1))
    tc = ws.cell(row=1, column=1)
    tc.value = title
    tc.font = Font(bold=True, size=14, color=_HEADER_COLOR)
    tc.alignment = Alignment(horizontal="center", vertical="center")

    ws.insert_rows(2)
    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=max(len(df.columns), 1))
    sc = ws.cell(row=2, column=1)
    sc.value = f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    sc.font = Font(italic=True, size=9, color="666666")
    sc.alignment = Alignment(horizontal="center")

    ws.insert_rows(3)

    header_row = 4
    for col_idx in range(1, len(df.columns) + 1):
        cell = ws.cell(row=header_row, column=col_idx)
        cell.fill = _header_fill()
        cell.font = _header_font()
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = _thin_border()

    data_start = header_row + 1
    for row_idx in range(data_start, data_start + len(df)):
        for col_idx in range(1, len(df.columns) + 1):
            cell = ws.cell(row=row_idx, column=col_idx)
            cell.border = _thin_border()
            cell.alignment = Alignment(vertical="center", wrap_text=True)

    # Auto-width (capped)
    for col_idx, col_name in enumerate(df.columns, start=1):
        max_w = max(len(str(col_name)), 12)
        ws.column_dimensions[get_column_letter(col_idx)].width = min(max_w + 4, 60)

    ws.freeze_panes = ws.cell(row=data_start, column=1)


# ── Inline request schema (pipeline result shape) ─────────────────────────────

class CombinedReportRequest(BaseModel):
    """Accepts the JSON body returned by POST /pipeline/run."""

    pipeline_id: str
    status: str = "completed"
    summary: Dict[str, Any]
    results: List[Dict[str, Any]]


@router.post("/combined")
async def combined_report(body: CombinedReportRequest):
    """Generate a multi-sheet Excel report from a PipelineResult.

    Paste the full JSON returned by /pipeline/run as the request body.
    Returns a .xlsx file download.
    """
    if not _EXCEL_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail="openpyxl or pandas not installed. Run: pip install openpyxl pandas",
        )

    results = body.results
    if not results:
        raise HTTPException(status_code=400, detail="No results provided.")

    # ── Sheet 1: Summary ──────────────────────────────────────────────────────
    summary = body.summary
    breakdown = summary.get("risk_breakdown", {})
    summary_rows = [
        {"Metric": "Pipeline ID", "Value": body.pipeline_id},
        {"Metric": "Status", "Value": body.status},
        {"Metric": "Total Entries", "Value": summary.get("total_entries", 0)},
        {"Metric": "Flagged", "Value": summary.get("flagged", 0)},
        {"Metric": "High Risk", "Value": breakdown.get("high", 0)},
        {"Metric": "Medium Risk", "Value": breakdown.get("medium", 0)},
        {"Metric": "Low Risk", "Value": breakdown.get("low", 0)},
        {"Metric": "No Risk", "Value": breakdown.get("none", 0)},
    ]
    df_summary = pd.DataFrame(summary_rows)

    # ── Sheet 2–7: Per-method sheets ──────────────────────────────────────────
    exact_rows, fuzzy_rows, semantic_rows, ai_rows, web_rows, lic_rows = [], [], [], [], [], []

    for entry in results:
        eid = entry.get("entry_id")
        text = entry.get("original_text", "")[:300]
        risk = entry.get("overall_risk", "none")
        methods = entry.get("methods") or {}

        # Exact
        ex = methods.get("exact") or {}
        exact_rows.append({
            "#": eid, "Text": text, "Overall Risk": risk,
            "Is Duplicate": ex.get("is_duplicate", False),
            "Matched Text": ex.get("matched_text") or "—",
            "Batch": ex.get("batch") or "—",
        })

        # Fuzzy
        fz = methods.get("fuzzy") or {}
        sc = fz.get("scores") or {}
        fuzzy_rows.append({
            "#": eid, "Text": text, "Overall Risk": risk,
            "Is Duplicate": fz.get("is_duplicate", False),
            "Levenshtein": sc.get("levenshtein", "—"),
            "Jaccard": sc.get("jaccard", "—"),
            "N-gram": sc.get("ngram", "—"),
            "Matched Text": fz.get("matched_text") or "—",
        })

        # Semantic
        sem = methods.get("semantic") or {}
        semantic_rows.append({
            "#": eid, "Text": text, "Overall Risk": risk,
            "Is Duplicate": sem.get("is_duplicate", False),
            "Similarity": sem.get("similarity", "—"),
            "Matched Text": sem.get("matched_text") or "—",
        })

        # AI Detection
        ai = methods.get("ai_detection") or {}
        ai_rows.append({
            "#": eid, "Text": text, "Overall Risk": risk,
            "Is AI Generated": ai.get("is_ai_generated", False),
            "Label": ai.get("label", "—"),
            "Confidence": ai.get("confidence", "—"),
        })

        # Web Scan
        ws_data = methods.get("web_scan") or {}
        sources = ws_data.get("sources") or []
        if sources:
            for src in sources:
                web_rows.append({
                    "#": eid, "Text": text, "Overall Risk": risk,
                    "Found Online": ws_data.get("found_online", False),
                    "URL": src.get("url", "—"),
                    "Best Score": src.get("best_score", "—"),
                    "Title": src.get("title", "—"),
                })
        else:
            web_rows.append({
                "#": eid, "Text": text, "Overall Risk": risk,
                "Found Online": ws_data.get("found_online", False),
                "URL": "—", "Best Score": "—", "Title": "—",
            })

        # License Check
        lic = methods.get("license_check") or {}
        licenses = lic.get("licenses") or []
        if licenses:
            for lic_item in licenses:
                lic_rows.append({
                    "#": eid, "Text": text, "Overall Risk": risk,
                    "Has License": lic.get("has_license", False),
                    "License Name": lic_item.get("license_name", "—"),
                    "SPDX ID": lic_item.get("spdx_id", "—"),
                    "Confidence": lic_item.get("confidence", "—"),
                    "License URL": lic_item.get("license_url", "—"),
                })
        else:
            lic_rows.append({
                "#": eid, "Text": text, "Overall Risk": risk,
                "Has License": lic.get("has_license", False),
                "License Name": "—", "SPDX ID": "—",
                "Confidence": "—", "License URL": "—",
            })

    sheets = [
        ("Summary", df_summary),
        ("Exact Matches", pd.DataFrame(exact_rows)),
        ("Fuzzy Matches", pd.DataFrame(fuzzy_rows)),
        ("Semantic Matches", pd.DataFrame(semantic_rows)),
        ("AI Detection", pd.DataFrame(ai_rows)),
        ("Web Scan", pd.DataFrame(web_rows)),
        ("License Check", pd.DataFrame(lic_rows)),
    ]

    # ── Write to buffer ───────────────────────────────────────────────────────
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        for sheet_name, df in sheets:
            df.to_excel(writer, sheet_name=sheet_name, index=False, startrow=0)
            ws = writer.sheets[sheet_name]
            _style_sheet(ws, sheet_name, df)

    filename = f"pipeline_{body.pipeline_id[:8]}_report.xlsx"
    return StreamingResponse(
        io.BytesIO(buf.getvalue()),
        media_type=_EXCEL_MEDIA_TYPE,
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
