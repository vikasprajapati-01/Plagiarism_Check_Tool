"""Unified detection pipeline orchestrator.

Runs all enabled detection methods concurrently for each input text and
combines their results into a single PipelineRunResult.
"""

import asyncio
import logging
import uuid
from typing import Any, Dict, List, Optional, Tuple

from app.core.config import settings
from app.core.models import (
    DuplicatePairResult,
    MethodsConfig,
    PipelineRunResult,
    WebAiEntryResult,
)
from app.services.ai_detector import detect_ai_content
from app.services.cross_compare import compare_columns_within_rows, run_cross_comparison
from app.services.license_detector import detect_license
from app.services.preprocessor import read_all_text_from_file
from app.services.web_scanner import scan_text_online

logger = logging.getLogger(__name__)


def _count_written_rows_in_files(files: List[Tuple[str, bytes]]) -> int:
    import io
    import pandas as pd
    total_rows = 0
    for filename, contents in files:
        filename_lower = filename.lower()
        try:
            if filename_lower.endswith(".csv"):
                df = pd.read_csv(io.BytesIO(contents))
                sheets = {"": df}
            elif filename_lower.endswith((".xlsx", ".xls")):
                sheets = pd.read_excel(io.BytesIO(contents), sheet_name=None)
            else:
                continue

            for sheet_name, df in sheets.items():
                if len(df) == 0:
                    continue
                header_set = {
                    str(col).strip().lower()
                    for col in df.columns
                    if col is not None and not pd.isna(col)
                }
                for _, row in df.iterrows():
                    vals = [
                        str(v).strip().lower()
                        for v in row
                        if v is not None and not pd.isna(v) and str(v).strip() != ""
                    ]
                    if not vals:
                        continue
                    if all(v in header_set for v in vals):
                        continue
                    total_rows += 1
        except Exception as exc:
            logger.warning("Failed to count rows in %s: %s", filename, exc)
    return total_rows


async def run_full_pipeline(
    files: List[Tuple[str, bytes]],
    methods_config: MethodsConfig,
    sbert_model: Any,
    gpt2_tokenizer: Optional[Any],
    gpt2_model: Optional[Any],
    target_column: str = "Query",
    threshold: float = 75.0,
    fuzzy_threshold: float = 0.85,
    semantic_threshold: float = 0.85,
    web_scan_timeout: int = 10,
    web_scan_retries: int = 3,
    detection_mode: str = "row",
    col1_name: str = "",
    col2_name: str = "",
) -> PipelineRunResult:
    pipeline_id = str(uuid.uuid4())
    row_duplicates: List[DuplicatePairResult] = []
    cell_duplicates: List[DuplicatePairResult] = []
    web_ai_results: List[WebAiEntryResult] = []

    def _clamp_pct(value: float) -> float:
        return max(0.0, min(100.0, value))

    def _ai_probability(ai_payload: Optional[dict]) -> float:
        """Extract AI probability from the GPT-2 detector payload.

        The payload includes 'ai_pct' (0–100) directly. Falls back to
        the label/confidence approach for backwards compatibility.
        """
        if not ai_payload:
            return 0.0
        # Prefer the direct ai_pct field (new GPT-2 detector)
        ai_pct = ai_payload.get("ai_pct")
        if ai_pct is not None:
            try:
                return max(0.0, min(1.0, float(ai_pct) / 100.0))
            except (TypeError, ValueError):
                pass
        # Legacy fallback (label + confidence)
        label = (ai_payload.get("label") or "").strip()
        try:
            confidence = float(ai_payload.get("confidence", 0.0))
        except (TypeError, ValueError):
            confidence = 0.0
        if label == "AI":
            return max(0.0, min(1.0, confidence))
        if label == "Human":
            return max(0.0, min(1.0, 1.0 - confidence))
        return 0.0

    entries_by_file: Dict[str, List[Dict[str, object]]] = {}
    all_entries: List[Dict[str, object]] = []

    for filename, contents in files:
        try:
            entries = read_all_text_from_file(filename, contents)
            entries_by_file[filename] = entries
            all_entries.extend(entries)
        except Exception as exc:
            logger.warning("Failed to read file %s: %s", filename, exc)
            entries_by_file[filename] = []

    # Count total written data rows across all uploaded files/sheets
    # (excludes completely empty rows and duplicate header/query rows)
    total_rows: int = _count_written_rows_in_files(files)

    try:
        loop = asyncio.get_running_loop()
        from functools import partial

        # Only XLSX files are used for cross-comparison (openpyxl requirement)
        compare_files: List[Tuple[str, bytes]] = [
            (fname, fbytes)
            for fname, fbytes in files
            if fname.lower().endswith((".xlsx", ".xls"))
        ]

        row_matches, cell_matches = [], []

        if detection_mode == "column":
            # Column-wise: compare col1_name vs col2_name within each row.
            # row_duplicates stays empty; cell_duplicates is populated.
            if compare_files and (methods_config.exact or methods_config.fuzzy):
                fname_cw, fbytes_cw = compare_files[0]
                col_matches = await loop.run_in_executor(
                    None,
                    partial(
                        compare_columns_within_rows,
                        fname_cw,
                        fbytes_cw,
                        col1_name,
                        col2_name,
                        threshold,
                    ),
                )
                cell_matches = col_matches
            # row_matches stays []
        else:
            # Row-wise (default): existing unchanged behaviour.
            if compare_files:
                row_matches, cell_matches = await loop.run_in_executor(
                    None,
                    partial(
                        run_cross_comparison,
                        compare_files,
                        threshold,
                        do_row_compare=methods_config.exact or methods_config.fuzzy,
                        do_cell_compare=methods_config.exact or methods_config.fuzzy,
                        target_column=target_column,
                    ),
                )

        row_duplicates = [
            DuplicatePairResult(
                original=f"{m.original_label}",
                duplicate=f"{m.duplicate_label}",
                type=m.match_type,
                similarity_pct=_clamp_pct(m.similarity),
            )
            for m in row_matches
        ]
        cell_duplicates = [
            DuplicatePairResult(
                original=f"{m.original_label}",
                duplicate=f"{m.duplicate_label}",
                type=m.match_type,
                similarity_pct=_clamp_pct(m.similarity),
            )
            for m in cell_matches
        ]
    except Exception as exc:
        logger.warning("Cross comparison failed: %s", exc)

    target_entries = []
    if methods_config.web_scan or methods_config.ai_detection or methods_config.license_check:
        if detection_mode == "column":
            # Only run on rows that were flagged as duplicate pairs.
            # Parse row indices from cell_duplicates labels ("filename-RowN-colname").
            flagged_row_indices: set = set()
            for pair in cell_duplicates:
                for label in [pair.original, pair.duplicate]:
                    parts = label.split("-Row")
                    if len(parts) >= 2:
                        row_part = parts[1].split("-")[0]
                        try:
                            flagged_row_indices.add(int(row_part))
                        except ValueError:
                            pass

            col_names_lower = {
                col1_name.strip().lower(),
                col2_name.strip().lower(),
            }
            for entries in entries_by_file.values():
                for entry in entries:
                    col = entry.get("column_name", "").strip().lower()
                    if col not in col_names_lower:
                        continue
                    row_num = entry.get("row_number")
                    if row_num not in flagged_row_indices:
                        continue
                    raw_text = entry.get("text", "")
                    if not raw_text or not raw_text.strip():
                        continue
                    target_entries.append(entry)
        else:
            # Row-wise: existing behavior unchanged.
            _target_cols_lower: set = {target_column.strip().lower()}
            for entries in entries_by_file.values():
                for entry in entries:
                    col = entry.get("column_name", "").strip().lower()
                    if col not in _target_cols_lower:
                        continue
                    raw_text = entry.get("text", "")
                    if not raw_text or not raw_text.strip():
                        continue
                    target_entries.append(entry)

    # Cap concurrent web/AI/license tasks so we don't flood the thread pool
    # or blow the global WEB_SCAN_OVERALL_TIMEOUT on large uploads.
    _max_concurrency = 4
    _entry_semaphore = asyncio.Semaphore(_max_concurrency)

    async def _bounded_process(entry: dict) -> Optional[WebAiEntryResult]:
        async with _entry_semaphore:
            return await _process_single_entry(entry)

    async def _process_single_entry(entry: dict) -> Optional[WebAiEntryResult]:
        raw_text = entry.get("text", "")
        run_ai = methods_config.ai_detection and gpt2_model is not None
        run_web = methods_config.web_scan
        run_license = methods_config.license_check

        if not (run_ai or run_web or run_license):
            return None

        tasks_inner: Dict[str, Any] = {}
        if run_web:
            tasks_inner["web_scan"] = scan_text_online(
                raw_text,
                timeout=web_scan_timeout,
                retries=web_scan_retries,
                max_queries=settings.WEB_SCAN_MAX_QUERIES,
                max_results_per_query=settings.WEB_SCAN_MAX_RESULTS,
                max_scan_time=settings.WEB_SCAN_MAX_SCAN_TIME,
            )
        if run_ai:
            tasks_inner["ai_detection"] = detect_ai_content(
                raw_text, gpt2_tokenizer, gpt2_model
            )
        if run_license:
            tasks_inner["license_check"] = detect_license(raw_text)

        try:
            inner_results = await asyncio.gather(
                *tasks_inner.values(), return_exceptions=True
            )
        except asyncio.CancelledError:
            logger.warning(
                "Entry processing cancelled for: %.60s", raw_text
            )
            return None

        method_results_inner: Dict[str, Any] = {}
        for key, res in zip(tasks_inner.keys(), inner_results):
            if isinstance(res, Exception):
                logger.warning(
                    "Method %s failed for entry: %s", key, res
                )
            else:
                method_results_inner[key] = res

        web_result = method_results_inner.get("web_scan")
        ai_result = method_results_inner.get("ai_detection")

        is_plagiarised = False
        source_url: Optional[str] = None
        if web_result is not None:
            is_plagiarised = getattr(web_result, "is_plagiarism", False)
            matches_list = getattr(web_result, "matches", []) or []
            if matches_list:
                source_url = getattr(matches_list[0], "url", None)

        ai_pct = _clamp_pct(round(_ai_probability(ai_result) * 100, 1))

        if ai_pct < 50.0 and not is_plagiarised:
            return None

        source_str = source_url if source_url else "N/A"
        plagiarised_str = "Yes" if is_plagiarised else "No"

        sheet = entry.get("sheet_name") or ""
        sheet_part = f"-{sheet}" if sheet else ""
        return WebAiEntryResult(
            original=f"{entry.get('source_file')}{sheet_part}-{entry.get('cell_ref')}",
            plagiarised=plagiarised_str,
            source=source_str,
            ai_detected_pct=ai_pct,
        )

    if target_entries:
        try:
            tasks = [asyncio.create_task(_bounded_process(e)) for e in target_entries]
            done, pending = await asyncio.wait(
                tasks,
                timeout=settings.WEB_SCAN_OVERALL_TIMEOUT,
            )

            for t in done:
                try:
                    res = t.result()
                except Exception as exc:
                    logger.warning("Entry processing error: %s", exc)
                    continue

                if res is not None:
                    web_ai_results.append(res)

            if pending:
                logger.warning(
                    "Web/AI detection block timed out after %ds — "
                    "returning %d/%d completed results",
                    settings.WEB_SCAN_OVERALL_TIMEOUT,
                    len(done),
                    len(tasks),
                )
                for t in pending:
                    t.cancel()
        except asyncio.CancelledError:
            logger.warning(
                "Web/AI detection block was cancelled — "
                "returning partial results"
            )

    summary = {
        "total_files": len(files),
        "total_rows": total_rows,
        "total_row_duplicates": len(row_duplicates),
        "total_cell_duplicates": len(cell_duplicates),
        "exact_row_matches": sum(1 for r in row_duplicates if r.type == "Exact"),
        "near_row_matches": sum(1 for r in row_duplicates if r.type == "Near"),
        "exact_cell_matches": sum(1 for r in cell_duplicates if r.type == "Exact"),
        "near_cell_matches": sum(1 for r in cell_duplicates if r.type == "Near"),
        "plagiarised_entries": sum(1 for r in web_ai_results if r.plagiarised == "Yes"),
        "ai_detected_entries": sum(1 for r in web_ai_results if r.ai_detected_pct > 50.0),
        "web_ai_total_entries": len(target_entries),
        "web_ai_returned_entries": len(web_ai_results),
    }

    return PipelineRunResult(
        pipeline_id=pipeline_id,
        status="completed",
        summary=summary,
        row_duplicates=row_duplicates,
        cell_duplicates=cell_duplicates,
        web_ai_results=web_ai_results,
    )
