"""Pipeline trigger endpoints.

POST /columns  — return column names found across all uploaded Excel/CSV files.
POST /run      — accepts uploaded files, runs the full detection pipeline.
"""

import io
import json
import logging
from typing import Annotated, List, Optional, Tuple

import pandas as pd

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse

from app.core.models import MethodsConfig, PipelineRunResult
from app.core.config import settings
from app.services.pipeline_runner import run_full_pipeline

logger = logging.getLogger(__name__)
router = APIRouter()


def _get_models(request: Request):
    """Retrieve pre-loaded models from app.state. Raises 503 if SBERT not ready.

    GPT-2 may be None when torch/transformers are absent — AI detection
    degrades gracefully in that case rather than blocking the whole pipeline.
    """
    sbert = getattr(request.app.state, "sbert_model", None)
    if sbert is None:
        raise HTTPException(
            status_code=503,
            detail="SBERT model is not yet loaded. Retry in a moment.",
        )
    gpt2_tokenizer = getattr(request.app.state, "gpt2_tokenizer", None)
    gpt2_model     = getattr(request.app.state, "gpt2_model", None)
    return sbert, gpt2_tokenizer, gpt2_model


@router.post("/columns")
async def get_pipeline_columns(
    files: Annotated[
        List[UploadFile],
        File(description="One or more Excel or CSV files to inspect."),
    ] = [],
):
    """Return all column names found across all uploaded files.

    Call this before /run to discover which columns are available.
    The user selects one as the target_column for detection.
    If a column named 'Query' is found it is suggested automatically.
    """
    if not files:
        raise HTTPException(status_code=400, detail="Provide at least one file.")

    from app.services.cross_compare import get_available_columns

    parsed_files: List[Tuple[str, bytes]] = []
    for upload in files:
        contents = await upload.read()
        if upload.filename and upload.filename.lower().endswith(
            (".xlsx", ".xls", ".csv")
        ):
            parsed_files.append((upload.filename, contents))

    if not parsed_files:
        raise HTTPException(
            status_code=400,
            detail="No supported files found. Upload .xlsx, .xls, or .csv files.",
        )

    try:
        columns_by_sheet = get_available_columns(parsed_files)
    except Exception as exc:
        logger.warning("Column discovery failed: %s", exc)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to read columns from files: {exc}",
        )

    all_columns_set = set()
    files_info = []

    for sheet_key, col_list in columns_by_sheet.items():
        parts = sheet_key.split(" > ", 1)
        fname = parts[0] if parts else sheet_key
        sname = parts[1] if len(parts) > 1 else ""
        all_columns_set.update(col_list)

        existing = next((f for f in files_info if f["filename"] == fname), None)
        if existing:
            existing["sheets"].append({"sheet": sname, "columns": col_list})
        else:
            files_info.append({
                "filename": fname,
                "sheets": [{"sheet": sname, "columns": col_list}],
            })

    all_columns = sorted(all_columns_set)
    query_found = any(c.lower() == "query" for c in all_columns)
    suggested = "Query" if query_found else (all_columns[0] if all_columns else "")

    return {
        "files": files_info,
        "all_columns": all_columns,
        "query_column_found": query_found,
        "suggested_target": suggested,
    }


@router.post("/run")
async def run_pipeline_endpoint(
    request: Request,
    files: Annotated[
        List[UploadFile],
        File(description="One or more Excel or CSV files."),
    ] = [],
    methods: Optional[str] = Form(None),               # JSON object string
    target_column: str = Form(""),
    download_report: bool = Form(False),
    report_format: str = Form("excel"),
    color_report: bool = Form(False),
    detection_mode: str = Form("row"),       # "row" | "column"
    target_columns: str = Form(""),          # comma-separated, used only in column mode
):
    """Run the full detection pipeline on uploaded Excel/CSV files.

    - files: one or more .xlsx, .xls, or .csv files to check.
    - methods: JSON object selecting which detection methods to run.
    - target_column: the column to run detection on (row-wise mode).
    - detection_mode: 'row' for cross-row detection, 'column' for within-row column comparison.
    - target_columns: comma-separated column names (column-wise mode only).
    - download_report: if true, return the Excel report directly instead of JSON.
    - color_report: if true, colour-code the downloaded report by severity.
    """
    sbert_model, gpt2_tokenizer, gpt2_model = _get_models(request)

    # ── Parse methods config ──────────────────────────────────────────────────
    if methods:
        try:
            methods_dict = json.loads(methods)
            methods_config = MethodsConfig(**methods_dict)
        except Exception as exc:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid 'methods' JSON: {exc}",
            ) from exc
    else:
        methods_config = MethodsConfig()

    # ── Read input texts from uploaded files ──────────────────────────────────
    if not files:
        raise HTTPException(
            status_code=400, detail="Provide at least one file."
        )

    parsed_files: List[Tuple[str, bytes]] = []
    for upload in files:
        contents = await upload.read()
        parsed_files.append((upload.filename or "upload.xlsx", contents))

    # ── Discover columns from all uploaded files (XLSX, CSV) ─────────────────
    from app.services.cross_compare import get_available_columns
    columns_by_sheet: dict = {}
    for fname, fbytes in parsed_files:
        fname_lower = fname.lower()
        try:
            if fname_lower.endswith((".xlsx", ".xls")):
                cols = get_available_columns([(fname, fbytes)])
                columns_by_sheet.update(cols)
            elif fname_lower.endswith(".csv"):
                df_hdr = pd.read_csv(io.BytesIO(fbytes), nrows=0)
                col_list = [str(c) for c in df_hdr.columns]
                if col_list:
                    columns_by_sheet[f"{fname} > Sheet1"] = col_list
        except Exception as exc:
            logger.warning("Column discovery failed for %s: %s", fname, exc)

    all_found_columns: set = set()
    for col_list in columns_by_sheet.values():
        all_found_columns.update(col_list)

    resolved_target: str = ""
    resolved_target_columns: List[str] = []

    # ── Validate detection_mode ───────────────────────────────────────────────
    if detection_mode not in ("row", "column"):
        raise HTTPException(
            status_code=422,
            detail=f"detection_mode must be 'row' or 'column', got '{detection_mode}'.",
        )

    if detection_mode == "row":
        if not target_column or target_column.strip().lower() == "auto":
            # 1. Prefer an explicit "Query" column.
            query_match = next(
                (c for c in all_found_columns if c.lower() == "query"), None
            )
            if query_match:
                resolved_target = query_match
                logger.info("Auto-detected target column: %s", resolved_target)
            elif len(all_found_columns) == 1:
                # 2. Single-column file — use it automatically.
                resolved_target = next(iter(all_found_columns))
                logger.info("Single column available, using: %s", resolved_target)
            else:
                raise HTTPException(
                    status_code=422,
                    detail={
                        "message": (
                            "No 'Query' column found in uploaded files. "
                            "Please specify target_column from the available columns."
                        ),
                        "available_columns": sorted(all_found_columns),
                    },
                )
        else:
            # User specified a column — verify it exists
            match = next(
                (c for c in all_found_columns if c.lower() == target_column.strip().lower()),
                None,
            )
            if match:
                resolved_target = match
            else:
                raise HTTPException(
                    status_code=422,
                    detail={
                        "message": (
                            f"Column '{target_column}' not found in uploaded files. "
                            "Please choose from the available columns."
                        ),
                        "available_columns": sorted(all_found_columns),
                    },
                )

    else:  # detection_mode == "column"
        # ── Column-wise validation ────────────────────────────────────────────
        # 1. Exactly one non-ZIP file
        if len(parsed_files) != 1:
            raise HTTPException(
                status_code=422,
                detail="Column-wise mode requires exactly one uploaded file.",
            )
        # 2. At least 2 column names
        col_names = [c.strip() for c in target_columns.split(",") if c.strip()]
        if len(col_names) < 2:
            raise HTTPException(
                status_code=422,
                detail="Column-wise mode requires at least 2 column names in target_columns.",
            )
        # 3. Each column must exist in the uploaded file
        missing = [
            c for c in col_names
            if not any(c.lower() == fc.lower() for fc in all_found_columns)
        ]
        if missing:
            raise HTTPException(
                status_code=422,
                detail={
                    "message": f"Column(s) not found in uploaded file: {missing}",
                    "available_columns": sorted(all_found_columns),
                },
            )
        # Canonicalise to actual case from the file
        resolved_target_columns = [
            next(fc for fc in all_found_columns if fc.lower() == c.lower())
            for c in col_names
        ]

    logger.info(
        "Pipeline run: %d files, detection_mode=%s, target_column=%s, target_columns=%s, methods=%s",
        len(parsed_files), detection_mode, resolved_target, resolved_target_columns,
        methods_config.model_dump(),
    )

    result = await run_full_pipeline(
        files=parsed_files,
        methods_config=methods_config,
        sbert_model=sbert_model,
        gpt2_tokenizer=gpt2_tokenizer,
        gpt2_model=gpt2_model,
        target_column=resolved_target,
        threshold=75.0,
        fuzzy_threshold=settings.FUZZY_THRESHOLD,
        semantic_threshold=settings.SEMANTIC_THRESHOLD,
        web_scan_timeout=settings.WEB_SCAN_TIMEOUT,
        web_scan_retries=settings.WEB_SCAN_RETRIES,
        detection_mode=detection_mode,
        target_columns=resolved_target_columns,
    )

    if download_report:
        from app.api.v1.reports import generate_pipeline_report

        report_bytes = generate_pipeline_report(
            pipeline_id=result.pipeline_id,
            row_duplicates=[r.dict() for r in result.row_duplicates],
            cell_duplicates=[r.dict() for r in result.cell_duplicates],
            web_ai_results=[r.dict() for r in result.web_ai_results],
            color_report=color_report,
        )
        filename = f"pipeline_{result.pipeline_id[:8]}_report.xlsx"
        return StreamingResponse(
            io.BytesIO(report_bytes),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )

    return result
