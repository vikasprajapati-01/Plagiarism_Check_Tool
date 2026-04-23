"""
Cross-Cell & Cross-Row Comparison Service
==========================================

Compares every cell/row against every other cell/row across all sheets
in one or more Excel workbooks, using exact + fuzzy detection.

Outputs:
    1. A comparison report (.xlsx) listing all duplicate pairs
    2. A color-coded copy of the input workbook highlighting duplicates

Color Index:
    Red/Pink  → Exact Row-to-Row Duplicates
    Orange    → Near  Row-to-Row Duplicates
    Green     → Exact Cell-to-Cell Duplicates
    Lt Yellow → Near  Cell-to-Cell Duplicates

Usage:
    from app.services.cross_compare import run_cross_comparison, generate_comparison_report

    row_matches, cell_matches = run_cross_comparison(
        [("Dataset1.xlsx", file_bytes_1), ("Dataset2.xlsx", file_bytes_2)],
        threshold=75.0,
    )
    report_bytes = generate_comparison_report(row_matches, cell_matches)
"""

import io
from dataclasses import dataclass, field
from itertools import combinations
from typing import Dict, List, Optional, Set, Tuple

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from app.services.preprocess import preprocess_text
from app.services.fuzzy import levenshtein_similarity


# ==============================================================================
# DATA MODELS
# ==============================================================================


@dataclass
class CellRef:
    """Reference to a single cell value with its source location."""

    file_name: str
    sheet_name: str
    row: int          # 1-indexed (Excel row)
    col: int          # 1-indexed (Excel column)
    col_letter: str   # "A", "B", etc.
    raw_value: str
    cleaned_value: str = ""

    def __post_init__(self):
        self.cleaned_value = preprocess_text(self.raw_value) if self.raw_value else ""

    @property
    def label(self) -> str:
        return f"{self.file_name} > {self.sheet_name} > Cell {self.col_letter}{self.row}"


@dataclass
class RowRef:
    """Reference to a complete data row with all its cells."""

    file_name: str
    sheet_name: str
    row: int
    cells: List[CellRef] = field(default_factory=list)
    combined_raw: str = ""
    combined_cleaned: str = ""

    def __post_init__(self):
        self.combined_raw = " | ".join(c.raw_value for c in self.cells if c.raw_value)
        self.combined_cleaned = preprocess_text(self.combined_raw)

    @property
    def label(self) -> str:
        return f"{self.file_name} > {self.sheet_name} > Row {self.row}"


@dataclass
class MatchPair:
    """A single detected duplicate pair with source tracing."""

    original_label: str     # e.g. "Dataset1.xlsx > Sheet1 > Row 2"
    duplicate_label: str    # e.g. "Dataset1.xlsx > Sheet1 > Cell B10"
    original_text: str
    duplicate_text: str
    match_type: str         # "Exact" or "Near"
    similarity: float       # 0-100
    level: str              # "Row" or "Cell"
    # Source coordinates (for color-coding the input workbook)
    original_sheet: str = ""
    original_row: int = 0
    original_col: int = 0   # 0 = entire row
    duplicate_sheet: str = ""
    duplicate_row: int = 0
    duplicate_col: int = 0


# ==============================================================================
# COLOR CONSTANTS
# ==============================================================================

FILL_EXACT_ROW = PatternFill(start_color="FF9999", end_color="FF9999", fill_type="solid")
FILL_NEAR_ROW = PatternFill(start_color="FFD699", end_color="FFD699", fill_type="solid")
FILL_EXACT_CELL = PatternFill(start_color="99FF99", end_color="99FF99", fill_type="solid")
FILL_NEAR_CELL = PatternFill(start_color="FFFFCC", end_color="FFFFCC", fill_type="solid")

_HEADER_FILL = PatternFill(start_color="1F4E79", end_color="1F4E79", fill_type="solid")
_HEADER_FONT = Font(bold=True, color="FFFFFF", size=11)
_THIN_BORDER = Border(
    left=Side(style="thin"), right=Side(style="thin"),
    top=Side(style="thin"), bottom=Side(style="thin"),
)

# Serial-number column names to auto-skip
_SERIAL_HEADERS = {
    "s. no.", "s.no.", "s. no", "sno", "s no", "#", "sr", "sr.",
    "sr. no.", "sl. no.", "sl.no.", "sl no", "no.", "no",
}


# ==============================================================================
# PARSING — Extract cells & rows from Excel workbooks
# ==============================================================================


def parse_excel_file(
    file_name: str,
    contents: bytes,
) -> Tuple[List[RowRef], List[CellRef]]:
    """
    Parse ALL sheets from an Excel workbook.

    Returns:
        (rows, cells) — each element carries full source tracing.

    Automatically skips:
        - Header rows (row 1 of each sheet)
        - Serial number columns (S. No., #, etc.)
        - Empty rows and cells
    """
    wb = load_workbook(io.BytesIO(contents), read_only=True, data_only=True)
    all_rows: List[RowRef] = []
    all_cells: List[CellRef] = []

    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        headers: List[str] = []
        skip_cols: Set[int] = set()  # 1-indexed columns to skip

        for row_idx, row in enumerate(ws.iter_rows(values_only=False), start=1):
            # Row 1 = headers — detect which columns to skip
            if row_idx == 1:
                for col_idx, cell in enumerate(row, start=1):
                    header_val = str(cell.value).strip().lower() if cell.value else ""
                    headers.append(header_val)
                    if header_val in _SERIAL_HEADERS:
                        skip_cols.add(col_idx)
                continue

            row_cells: List[CellRef] = []
            has_data = False

            for col_idx, cell in enumerate(row, start=1):
                if col_idx in skip_cols:
                    continue

                value = str(cell.value).strip() if cell.value is not None else ""
                if not value or value.lower() == "none":
                    continue

                has_data = True
                cell_ref = CellRef(
                    file_name=file_name,
                    sheet_name=sheet_name,
                    row=row_idx,
                    col=col_idx,
                    col_letter=get_column_letter(col_idx),
                    raw_value=value,
                )
                row_cells.append(cell_ref)
                all_cells.append(cell_ref)

            if has_data and row_cells:
                row_ref = RowRef(
                    file_name=file_name,
                    sheet_name=sheet_name,
                    row=row_idx,
                    cells=row_cells,
                )
                all_rows.append(row_ref)

    wb.close()
    return all_rows, all_cells


# ==============================================================================
# COMPARISON ENGINE
# ==============================================================================


def compare_rows(
    rows: List[RowRef],
    threshold: float = 75.0,
) -> List[MatchPair]:
    """
    O(n²) row-to-row comparison across all sheets/files.

    Compares the combined text of each row (all columns joined).
    Returns matches above the similarity threshold.
    """
    matches: List[MatchPair] = []

    for i, j in combinations(range(len(rows)), 2):
        a, b = rows[i], rows[j]

        # Skip comparing a row against itself
        if a.file_name == b.file_name and a.sheet_name == b.sheet_name and a.row == b.row:
            continue

        if not a.combined_cleaned or not b.combined_cleaned:
            continue

        # Quick exact check
        if a.combined_cleaned == b.combined_cleaned:
            matches.append(MatchPair(
                original_label=a.label, duplicate_label=b.label,
                original_text=a.combined_raw, duplicate_text=b.combined_raw,
                match_type="Exact", similarity=100.0, level="Row",
                original_sheet=a.sheet_name, original_row=a.row,
                duplicate_sheet=b.sheet_name, duplicate_row=b.row,
            ))
            continue

        # Fuzzy check
        sim = levenshtein_similarity(a.combined_cleaned, b.combined_cleaned) * 100
        if sim >= threshold:
            matches.append(MatchPair(
                original_label=a.label, duplicate_label=b.label,
                original_text=a.combined_raw, duplicate_text=b.combined_raw,
                match_type="Near", similarity=round(sim, 1), level="Row",
                original_sheet=a.sheet_name, original_row=a.row,
                duplicate_sheet=b.sheet_name, duplicate_row=b.row,
            ))

    return matches


def compare_cells(
    cells: List[CellRef],
    threshold: float = 75.0,
) -> List[MatchPair]:
    """
    O(n²) cell-to-cell comparison across all sheets/files.

    Compares individual cell values. Skips very short values (< 3 chars
    after preprocessing) to avoid false positives on trivial matches.
    """
    matches: List[MatchPair] = []

    for i, j in combinations(range(len(cells)), 2):
        a, b = cells[i], cells[j]

        # Skip same cell
        if (a.file_name == b.file_name and a.sheet_name == b.sheet_name
                and a.row == b.row and a.col == b.col):
            continue

        # Skip trivially short values
        if len(a.cleaned_value) < 3 or len(b.cleaned_value) < 3:
            continue

        # Exact check
        if a.cleaned_value == b.cleaned_value:
            matches.append(MatchPair(
                original_label=a.label, duplicate_label=b.label,
                original_text=a.raw_value, duplicate_text=b.raw_value,
                match_type="Exact", similarity=100.0, level="Cell",
                original_sheet=a.sheet_name, original_row=a.row,
                original_col=a.col,
                duplicate_sheet=b.sheet_name, duplicate_row=b.row,
                duplicate_col=b.col,
            ))
            continue

        # Fuzzy check
        sim = levenshtein_similarity(a.cleaned_value, b.cleaned_value) * 100
        if sim >= threshold:
            matches.append(MatchPair(
                original_label=a.label, duplicate_label=b.label,
                original_text=a.raw_value, duplicate_text=b.raw_value,
                match_type="Near", similarity=round(sim, 1), level="Cell",
                original_sheet=a.sheet_name, original_row=a.row,
                original_col=a.col,
                duplicate_sheet=b.sheet_name, duplicate_row=b.row,
                duplicate_col=b.col,
            ))

    return matches


# ==============================================================================
# MAIN PIPELINE
# ==============================================================================


def run_cross_comparison(
    files: List[Tuple[str, bytes]],
    threshold: float = 75.0,
    do_row_compare: bool = True,
    do_cell_compare: bool = True,
) -> Tuple[List[MatchPair], List[MatchPair]]:
    """
    Main entry point: parse file(s) and run cross comparisons.

    Args:
        files: List of (filename, file_bytes) tuples.
        threshold: Minimum similarity % to flag (0-100).
        do_row_compare: Run row-to-row comparison.
        do_cell_compare: Run cell-to-cell comparison.

    Returns:
        (row_matches, cell_matches)
    """
    all_rows: List[RowRef] = []
    all_cells: List[CellRef] = []

    for file_name, contents in files:
        rows, cells = parse_excel_file(file_name, contents)
        all_rows.extend(rows)
        all_cells.extend(cells)

    row_matches = compare_rows(all_rows, threshold) if do_row_compare else []
    cell_matches = compare_cells(all_cells, threshold) if do_cell_compare else []

    # Sort by similarity descending
    row_matches.sort(key=lambda m: m.similarity, reverse=True)
    cell_matches.sort(key=lambda m: m.similarity, reverse=True)

    return row_matches, cell_matches


# ==============================================================================
# REPORT GENERATION — Output report with duplicate pairs
# ==============================================================================


def generate_comparison_report(
    row_matches: List[MatchPair],
    cell_matches: List[MatchPair],
) -> bytes:
    """
    Generate a styled .xlsx report with all detected duplicate pairs.

    Sheets:
        1. Row Duplicates — row-to-row matches
        2. Cell Duplicates — cell-to-cell matches
        3. Summary — statistics

    Columns: Original | Duplicate | Type | Similarity (%)
    """
    wb = Workbook()

    # Sheet 1: Row duplicates
    ws_rows = wb.active
    ws_rows.title = "Row Duplicates"
    _write_matches_sheet(ws_rows, row_matches)

    # Sheet 2: Cell duplicates
    ws_cells = wb.create_sheet("Cell Duplicates")
    _write_matches_sheet(ws_cells, cell_matches)

    # Sheet 3: Summary
    ws_summary = wb.create_sheet("Summary")
    _write_summary_sheet(ws_summary, row_matches, cell_matches)

    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def _write_matches_sheet(ws, matches: List[MatchPair]) -> None:
    """Write match results into a worksheet with styling."""
    headers = ["Original", "Duplicate", "Type", "Similarity (%)"]
    for col, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=header)
        cell.fill = _HEADER_FILL
        cell.font = _HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = _THIN_BORDER

    exact_fill = PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid")
    near_fill = PatternFill(start_color="FFEB9C", end_color="FFEB9C", fill_type="solid")

    for idx, match in enumerate(matches, 2):
        ws.cell(row=idx, column=1, value=match.original_label).border = _THIN_BORDER
        ws.cell(row=idx, column=2, value=match.duplicate_label).border = _THIN_BORDER

        type_cell = ws.cell(row=idx, column=3, value=match.match_type)
        type_cell.border = _THIN_BORDER
        type_cell.fill = exact_fill if match.match_type == "Exact" else near_fill
        type_cell.alignment = Alignment(horizontal="center")

        sim_cell = ws.cell(row=idx, column=4, value=match.similarity)
        sim_cell.border = _THIN_BORDER
        sim_cell.number_format = "0"
        sim_cell.alignment = Alignment(horizontal="center")

    # Column widths — wider to fit "file > sheet > Row/Cell" labels
    ws.column_dimensions["A"].width = 55
    ws.column_dimensions["B"].width = 55
    ws.column_dimensions["C"].width = 10
    ws.column_dimensions["D"].width = 16
    ws.freeze_panes = "A2"


def _write_summary_sheet(ws, row_matches, cell_matches) -> None:
    """Write summary statistics."""
    ws.cell(row=1, column=1, value="Cross-Comparison Summary").font = Font(
        bold=True, size=14, color="1F4E79"
    )
    ws.merge_cells("A1:D1")

    data = [
        ("", ""),
        ("Row-to-Row Duplicates", ""),
        ("  Total pairs found", len(row_matches)),
        ("  Exact matches", sum(1 for m in row_matches if m.match_type == "Exact")),
        ("  Near matches", sum(1 for m in row_matches if m.match_type == "Near")),
        ("", ""),
        ("Cell-to-Cell Duplicates", ""),
        ("  Total pairs found", len(cell_matches)),
        ("  Exact matches", sum(1 for m in cell_matches if m.match_type == "Exact")),
        ("  Near matches", sum(1 for m in cell_matches if m.match_type == "Near")),
        ("", ""),
        ("Overall", ""),
        ("  Total duplicate pairs", len(row_matches) + len(cell_matches)),
    ]

    for idx, (label, value) in enumerate(data, 3):
        label_cell = ws.cell(row=idx, column=1, value=label)
        if label and not label.startswith(" "):
            label_cell.font = Font(bold=True, size=11)
        if value != "":
            ws.cell(row=idx, column=2, value=value)

    ws.column_dimensions["A"].width = 30
    ws.column_dimensions["B"].width = 15


# ==============================================================================
# COLOR-CODED INPUT WORKBOOK — Highlight duplicates in the original file
# ==============================================================================


def generate_colored_workbook(
    contents: bytes,
    row_matches: List[MatchPair],
    cell_matches: List[MatchPair],
) -> bytes:
    """
    Create a color-coded copy of the input workbook.

    Applies fills based on the Color Index:
        Red/Pink   → Exact Row-to-Row Duplicates
        Orange     → Near  Row-to-Row Duplicates
        Green      → Exact Cell-to-Cell Duplicates
        Lt Yellow  → Near  Cell-to-Cell Duplicates

    Row-level colors take priority over cell-level colors.
    """
    wb = load_workbook(io.BytesIO(contents))

    # Build lookup sets for fast access
    # row_colors: {(sheet, row)} → fill
    row_colors: Dict[Tuple[str, int], PatternFill] = {}
    for m in row_matches:
        fill = FILL_EXACT_ROW if m.match_type == "Exact" else FILL_NEAR_ROW
        key_a = (m.original_sheet, m.original_row)
        key_b = (m.duplicate_sheet, m.duplicate_row)
        # Don't overwrite exact with near
        if key_a not in row_colors or m.match_type == "Exact":
            row_colors[key_a] = fill
        if key_b not in row_colors or m.match_type == "Exact":
            row_colors[key_b] = fill

    # cell_colors: {(sheet, row, col)} → fill
    cell_colors: Dict[Tuple[str, int, int], PatternFill] = {}
    for m in cell_matches:
        fill = FILL_EXACT_CELL if m.match_type == "Exact" else FILL_NEAR_CELL
        key_a = (m.original_sheet, m.original_row, m.original_col)
        key_b = (m.duplicate_sheet, m.duplicate_row, m.duplicate_col)
        if key_a not in cell_colors or m.match_type == "Exact":
            cell_colors[key_a] = fill
        if key_b not in cell_colors or m.match_type == "Exact":
            cell_colors[key_b] = fill

    # Apply colors to each sheet
    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        for row in ws.iter_rows(min_row=2):  # skip header
            row_idx = row[0].row
            row_key = (sheet_name, row_idx)

            if row_key in row_colors:
                # Entire row gets row-level color
                for cell in row:
                    cell.fill = row_colors[row_key]
            else:
                # Check individual cells for cell-level color
                for cell in row:
                    cell_key = (sheet_name, row_idx, cell.column)
                    if cell_key in cell_colors:
                        cell.fill = cell_colors[cell_key]

    # Add Color Index legend to the first sheet
    _add_color_legend(wb[wb.sheetnames[0]])

    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def _add_color_legend(ws) -> None:
    """Add a Color Index legend to the right side of the sheet."""
    # Find the rightmost used column
    legend_col = ws.max_column + 2

    ws.cell(row=1, column=legend_col, value="Color Index").font = Font(bold=True, size=11)

    legend_items = [
        ("Exact Row-to-Row Duplicates", FILL_EXACT_ROW),
        ("Near Row-to-Row Duplicates", FILL_NEAR_ROW),
        ("Exact Cell-to-Cell Duplicates", FILL_EXACT_CELL),
        ("Near Cell-to-Cell Duplicates", FILL_NEAR_CELL),
    ]

    for idx, (label, fill) in enumerate(legend_items, 2):
        cell = ws.cell(row=idx, column=legend_col, value=label)
        cell.fill = fill
        cell.font = Font(size=10)

    ws.column_dimensions[get_column_letter(legend_col)].width = 32


# ==============================================================================
# DEMO & TESTING
# ==============================================================================

if __name__ == "__main__":
    print("=" * 70)
    print("CROSS-COMPARISON DEMO")
    print("=" * 70)

    # Create a sample workbook with 2 sheets for testing
    from openpyxl import Workbook as _WB

    wb = _WB()

    # Sheet 1
    ws1 = wb.active
    ws1.title = "Dataset 1"
    ws1.append(["S. No.", "Query", "Location", "Time"])
    ws1.append([1, "John playing foosball in Bangalore yesterday", "Bangalore", "yesterday"])
    ws1.append([2, "The concert I watched last week in Delhi", "Delhi", "last week"])
    ws1.append([3, "Photos of cats taken on the streets of Ooty", "Ooty", "this month"])
    ws1.append([4, "John playing foosball in Bangalore yesterday", "Bangalore", "yesterday"])
    ws1.append([5, "Japan 2025 trip photos", "Japan", "2025"])

    # Sheet 2
    ws2 = wb.create_sheet("Dataset 2")
    ws2.append(["S. No.", "Query", "Location", "Time"])
    ws2.append([1, "Joel playing table tennis in Mangalore yesterday", "Mangalore", "yesterday"])
    ws2.append([2, "The concert I watched last week in Chennai", "Chennai", "last week"])
    ws2.append([3, "Tokyo cherry blossom picnic shots from late March", "Tokyo", "late March"])
    ws2.append([4, "Japan 2025 trip photos", "Japan", "2025"])

    buf = io.BytesIO()
    wb.save(buf)
    test_bytes = buf.getvalue()

    # Run comparison
    print("\nParsing workbook...")
    row_matches, cell_matches = run_cross_comparison(
        [("TestData.xlsx", test_bytes)],
        threshold=75.0,
    )

    print(f"\n--- Row-to-Row Matches ({len(row_matches)}) ---")
    for m in row_matches:
        print(f"  {m.original_label} ↔ {m.duplicate_label}  [{m.match_type}] {m.similarity}%")

    print(f"\n--- Cell-to-Cell Matches ({len(cell_matches)}) ---")
    for m in cell_matches:
        print(f"  {m.original_label} ↔ {m.duplicate_label}  [{m.match_type}] {m.similarity}%")
        print(f"    '{m.original_text}' ↔ '{m.duplicate_text}'")

    # Generate report
    report = generate_comparison_report(row_matches, cell_matches)
    with open("cross_comparison_report.xlsx", "wb") as f:
        f.write(report)
    print(f"\n✅ Report saved: cross_comparison_report.xlsx ({len(report):,} bytes)")

    # Generate colored workbook
    colored = generate_colored_workbook(test_bytes, row_matches, cell_matches)
    with open("colored_input.xlsx", "wb") as f:
        f.write(colored)
    print(f"✅ Colored workbook saved: colored_input.xlsx ({len(colored):,} bytes)")

    print("\n" + "=" * 70)
