"""Cross-comparison endpoints for comparing cells/rows across Excel sheets."""

import io
from typing import List, Optional

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import StreamingResponse

from app.services.cross_compare import (
    run_cross_comparison,
    generate_comparison_report,
    generate_colored_workbook,
)

router = APIRouter()


@router.post("/cross")
async def cross_compare(
    files: List[UploadFile] = File(...),
    threshold: float = Form(75.0),
    compare_rows: bool = Form(True),
    compare_cells: bool = Form(True),
):
    """
    Compare all cells and rows across uploaded Excel files.

    Upload one or more .xlsx files. The service will:
    1. Parse all sheets from every file
    2. Compare every row against every other row (cross-sheet, cross-file)
    3. Compare every cell against every other cell
    4. Return detected duplicates with source tracing

    Args:
        files: One or more .xlsx files to compare
        threshold: Minimum similarity % to flag (0-100, default 75)
        compare_rows: Whether to do row-to-row comparison
        compare_cells: Whether to do cell-to-cell comparison

    Returns:
        JSON with row duplicates, cell duplicates, and summary stats
    """
    parsed_files = []
    for f in files:
        contents = await f.read()
        parsed_files.append((f.filename, contents))

    row_matches, cell_matches = run_cross_comparison(
        parsed_files,
        threshold=threshold,
        do_row_compare=compare_rows,
        do_cell_compare=compare_cells,
    )

    return {
        "status": "Comparison complete",
        "threshold": threshold,
        "row_duplicates": [
            {
                "original": m.original_label,
                "duplicate": m.duplicate_label,
                "type": m.match_type,
                "similarity": m.similarity,
                "original_text": m.original_text,
                "duplicate_text": m.duplicate_text,
            }
            for m in row_matches
        ],
        "cell_duplicates": [
            {
                "original": m.original_label,
                "duplicate": m.duplicate_label,
                "type": m.match_type,
                "similarity": m.similarity,
                "original_text": m.original_text,
                "duplicate_text": m.duplicate_text,
            }
            for m in cell_matches
        ],
        "summary": {
            "total_row_duplicates": len(row_matches),
            "exact_row_matches": sum(1 for m in row_matches if m.match_type == "Exact"),
            "near_row_matches": sum(1 for m in row_matches if m.match_type == "Near"),
            "total_cell_duplicates": len(cell_matches),
            "exact_cell_matches": sum(1 for m in cell_matches if m.match_type == "Exact"),
            "near_cell_matches": sum(1 for m in cell_matches if m.match_type == "Near"),
        },
    }


@router.post("/report")
async def cross_compare_report(
    files: List[UploadFile] = File(...),
    threshold: float = Form(75.0),
    compare_rows: bool = Form(True),
    compare_cells: bool = Form(True),
):
    """
    Run cross-comparison and return a downloadable .xlsx report.

    The report contains:
        Sheet 1: Row Duplicates — all row-to-row duplicate pairs
        Sheet 2: Cell Duplicates — all cell-to-cell duplicate pairs
        Sheet 3: Summary — overall statistics
    """
    parsed_files = []
    for f in files:
        contents = await f.read()
        parsed_files.append((f.filename, contents))

    row_matches, cell_matches = run_cross_comparison(
        parsed_files,
        threshold=threshold,
        do_row_compare=compare_rows,
        do_cell_compare=compare_cells,
    )

    report_bytes = generate_comparison_report(row_matches, cell_matches)

    return StreamingResponse(
        io.BytesIO(report_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": "attachment; filename=cross_comparison_report.xlsx"
        },
    )


@router.post("/colored")
async def cross_compare_colored(
    file: UploadFile = File(...),
    threshold: float = Form(75.0),
):
    """
    Run cross-comparison and return a color-coded copy of the input workbook.

    Color Index:
        Red/Pink   → Exact Row-to-Row Duplicates
        Orange     → Near  Row-to-Row Duplicates
        Green      → Exact Cell-to-Cell Duplicates
        Lt Yellow  → Near  Cell-to-Cell Duplicates
    """
    contents = await file.read()

    row_matches, cell_matches = run_cross_comparison(
        [(file.filename, contents)],
        threshold=threshold,
    )

    colored_bytes = generate_colored_workbook(contents, row_matches, cell_matches)

    return StreamingResponse(
        io.BytesIO(colored_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f"attachment; filename=colored_{file.filename}"
        },
    )
