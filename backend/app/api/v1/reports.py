"""Combined report endpoint — POST /reports/combined.

Accepts a PipelineRunResult-style JSON body and returns a 3-sheet Excel file.
"""

import io
import logging
from typing import List

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
_HEADER_COLOR = "1F4E79"
_ROW_EXACT_COLOR = "FFCCCC"
_ROW_NEAR_COLOR = "FFF2CC"
_ROW_PLAG_YES_COLOR = "FFCCCC"
_ROW_PLAG_NO_COLOR = "C6EFCE"
_AI_RED = "FFCCCC"
_AI_ORANGE = "FFE0CC"
_AI_YELLOW = "FFF2CC"


# ── Inline request schema (pipeline result shape) ─────────────────────────────

class CombinedReportRequest(BaseModel):
    pipeline_id: str
    status: str = "completed"
    comparison_scope: str = "both"
    summary: dict
    row_duplicates: List[dict]
    cell_duplicates: List[dict]
    web_ai_results: List[dict]
    color_report: bool = False


def generate_pipeline_report(
    pipeline_id: str,
    row_duplicates: list,
    cell_duplicates: list,
    web_ai_results: list,
    color_report: bool = False,
) -> bytes:
    def _build_pair_df(pairs: List[dict]) -> "pd.DataFrame":
        rows = [
            {
                "Original": row.get("original") or "",
                "Duplicate": row.get("duplicate") or "",
                "Type": row.get("type") or "",
                "Similarity (%)": row.get("similarity_pct", 0.0),
            }
            for row in pairs
        ]
        return pd.DataFrame(rows, columns=["Original", "Duplicate", "Type", "Similarity (%)"])

    def _build_web_ai_df(items: List[dict]) -> "pd.DataFrame":
        rows = [
            {
                "Original": row.get("original") or "",
                "Plagiarised": row.get("plagiarised") or "No",
                "Source": row.get("source") or "N/A",
                "AI Detected (%)": row.get("ai_detected_pct", 0.0),
            }
            for row in items
        ]
        df = pd.DataFrame(
            rows,
            columns=["Original", "Plagiarised", "Source", "AI Detected (%)"],
        )
        if not df.empty:
            df["Source"] = df["Source"].replace("", "N/A").fillna("N/A")
        return df

    df_rows = _build_pair_df(row_duplicates)
    df_cells = _build_pair_df(cell_duplicates)
    df_web_ai = _build_web_ai_df(web_ai_results)

    column_widths = {
        "Original": 55,
        "Duplicate": 55,
        "Type": 10,
        "Similarity (%)": 16,
        "Plagiarised": 14,
        "Source": 45,
        "AI Detected (%)": 18,
    }

    sheets = [
        ("Row-to-Row", df_rows),
        ("Cell-to-Cell", df_cells),
        ("AI-Plagiarism", df_web_ai),
    ]

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        for sheet_name, df in sheets:
            df.to_excel(writer, sheet_name=sheet_name, index=False, startrow=0)
            ws = writer.sheets[sheet_name]

            header_row = 1
            for col_idx in range(1, len(df.columns) + 1):
                cell = ws.cell(row=header_row, column=col_idx)
                cell.font = Font(bold=True, size=11, color="FFFFFF")
                cell.fill = PatternFill(start_color=_HEADER_COLOR, end_color=_HEADER_COLOR, fill_type="solid")
                cell.border = Border(
                    left=Side(style="thin"),
                    right=Side(style="thin"),
                    top=Side(style="thin"),
                    bottom=Side(style="thin"),
                )
                cell.alignment = Alignment(horizontal="center", vertical="center")

            data_start = 2
            data_end = data_start + len(df) - 1
            if len(df) > 0:
                for row_idx in range(data_start, data_end + 1):
                    for col_idx in range(1, len(df.columns) + 1):
                        cell = ws.cell(row=row_idx, column=col_idx)
                        cell.border = Border(
                            left=Side(style="thin"),
                            right=Side(style="thin"),
                            top=Side(style="thin"),
                            bottom=Side(style="thin"),
                        )
                        cell.alignment = Alignment(vertical="center", wrap_text=True)

            for col_idx, col_name in enumerate(df.columns, start=1):
                width = column_widths.get(col_name)
                if width:
                    ws.column_dimensions[get_column_letter(col_idx)].width = width

            if color_report and len(df) > 0:
                if sheet_name in {"Row-to-Row", "Cell-to-Cell"}:
                    type_idx = list(df.columns).index("Type") + 1
                    for row_idx in range(data_start, data_end + 1):
                        type_value = ws.cell(row=row_idx, column=type_idx).value
                        if type_value == "Exact":
                            fill = PatternFill(start_color=_ROW_EXACT_COLOR, end_color=_ROW_EXACT_COLOR, fill_type="solid")
                        elif type_value == "Near":
                            fill = PatternFill(start_color=_ROW_NEAR_COLOR, end_color=_ROW_NEAR_COLOR, fill_type="solid")
                        else:
                            fill = None
                        if fill:
                            for col_idx in range(1, len(df.columns) + 1):
                                ws.cell(row=row_idx, column=col_idx).fill = fill

                if sheet_name == "AI-Plagiarism":
                    plag_idx = list(df.columns).index("Plagiarised") + 1
                    ai_idx = list(df.columns).index("AI Detected (%)") + 1
                    for row_idx in range(data_start, data_end + 1):
                        plag_value = ws.cell(row=row_idx, column=plag_idx).value
                        if plag_value == "Yes":
                            row_fill = PatternFill(start_color=_ROW_PLAG_YES_COLOR, end_color=_ROW_PLAG_YES_COLOR, fill_type="solid")
                        elif plag_value == "No":
                            row_fill = PatternFill(start_color=_ROW_PLAG_NO_COLOR, end_color=_ROW_PLAG_NO_COLOR, fill_type="solid")
                        else:
                            row_fill = None

                        if row_fill:
                            for col_idx in range(1, len(df.columns) + 1):
                                ws.cell(row=row_idx, column=col_idx).fill = row_fill

                        ai_cell = ws.cell(row=row_idx, column=ai_idx)
                        try:
                            ai_value = float(ai_cell.value or 0)
                        except (TypeError, ValueError):
                            ai_value = 0

                        ai_fill = None
                        if ai_value >= 80:
                            ai_fill = PatternFill(start_color=_AI_RED, end_color=_AI_RED, fill_type="solid")
                        elif ai_value >= 50:
                            ai_fill = PatternFill(start_color=_AI_ORANGE, end_color=_AI_ORANGE, fill_type="solid")
                        elif ai_value >= 20:
                            ai_fill = PatternFill(start_color=_AI_YELLOW, end_color=_AI_YELLOW, fill_type="solid")

                        if ai_fill:
                            ai_cell.fill = ai_fill

            ws.freeze_panes = "A2"

    return buf.getvalue()


@router.post("/combined")
async def combined_report(body: CombinedReportRequest):
    """Generate a 3-sheet Excel report from a pipeline run result."""
    if not _EXCEL_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail="openpyxl or pandas not installed. Run: pip install openpyxl pandas",
        )
    report_bytes = generate_pipeline_report(
        pipeline_id=body.pipeline_id,
        row_duplicates=body.row_duplicates,
        cell_duplicates=body.cell_duplicates,
        web_ai_results=body.web_ai_results,
        color_report=body.color_report,
    )

    filename = f"pipeline_{body.pipeline_id[:8]}_report.xlsx"
    return StreamingResponse(
        io.BytesIO(report_bytes),
        media_type=_EXCEL_MEDIA_TYPE,
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
