"""Pipeline trigger endpoints.

POST /run            — accepts uploaded files, runs the full detection pipeline.
POST /run-on-server  — runs the pipeline on already-registered server-side batches.
"""

import io
import json
import logging
from typing import Annotated, List, Optional, Tuple

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse

from app.core.models import MethodsConfig, PipelineResult, PipelineRunResult, ServerPipelineRequest
from app.core.config import settings
from app.services.pipeline_runner import run_full_pipeline, run_pipeline
from app.storage.repository import async_fetch_all_texts_by_batch

logger = logging.getLogger(__name__)
router = APIRouter()


def _get_models(request: Request):
    """Retrieve pre-loaded models from app.state. Raises 503 if not ready."""
    sbert = getattr(request.app.state, "sbert_model", None)
    ai = getattr(request.app.state, "ai_model", None)
    if sbert is None or ai is None:
        raise HTTPException(
            status_code=503,
            detail="Models are not yet loaded. Retry in a moment.",
        )
    return sbert, ai


@router.post("/columns")
async def get_pipeline_columns(
    files: Annotated[
        List[UploadFile],
        File(description="One or more Excel/CSV/TXT files to inspect."),
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
            (".xlsx", ".xls", ".csv", ".txt")
        ):
            parsed_files.append((upload.filename, contents))

    if not parsed_files:
        raise HTTPException(
            status_code=400,
            detail="No supported files found. Upload .xlsx, .xls, .csv, or .txt files.",
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
        File(description="One or more CSV / XLSX / TXT files."),
    ] = [],
    reference_batch_ids: Optional[str] = Form(None),  # JSON array string
    methods: Optional[str] = Form(None),               # JSON object string
    target_column: str = Form(""),
    download_report: bool = Form(False),
    report_format: str = Form("excel"),
    color_report: bool = Form(False),
):
    """Run the full detection pipeline on uploaded files.

    - files: one or more Excel/CSV/TXT files to check.
    - reference_batch_ids: JSON array of batch UUIDs to compare against
      (e.g. '["uuid1","uuid2"]'). If omitted, all stored texts are used.
    - methods: JSON object selecting which detection methods to run.
    - download_report: reserved for future use (report served via /reports/combined).
    - report_format: reserved for future use.
    """
    sbert_model, ai_model = _get_models(request)

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
        parsed_files.append((upload.filename or "upload.txt", contents))

    # Discover columns from uploaded files
    from app.services.cross_compare import get_available_columns
    try:
        xlsx_files = [
            (fname, fbytes) for fname, fbytes in parsed_files
            if fname.lower().endswith((".xlsx", ".xls"))
        ]
        columns_by_sheet: dict = {}
        if xlsx_files:
            columns_by_sheet = get_available_columns(xlsx_files)
    except Exception as exc:
        logger.warning("Column discovery failed: %s", exc)
        columns_by_sheet = {}

    all_found_columns: set = set()
    for col_list in columns_by_sheet.values():
        all_found_columns.update(col_list)

    resolved_target: str = ""

    if not target_column or target_column.strip().lower() == "auto":
        # Auto-detect: look for Query column
        query_match = next(
            (c for c in all_found_columns if c.lower() == "query"), None
        )
        if query_match:
            resolved_target = query_match
            logger.info("Auto-detected target column: %s", resolved_target)
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

    # ── Load reference texts ──────────────────────────────────────────────────
    batch_ids: List[str] = []
    if reference_batch_ids:
        try:
            batch_ids = json.loads(reference_batch_ids)
        except Exception as exc:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid 'reference_batch_ids' JSON: {exc}",
            ) from exc

    logger.info(
        "Pipeline run: %d files, target_column=%s, methods=%s",
        len(parsed_files), resolved_target, methods_config.model_dump(),
    )

    result = await run_full_pipeline(
        files=parsed_files,
        methods_config=methods_config,
        sbert_model=sbert_model,
        ai_model=ai_model,
        target_column=resolved_target,
        threshold=75.0,
        fuzzy_threshold=settings.FUZZY_THRESHOLD,
        semantic_threshold=settings.SEMANTIC_THRESHOLD,
        web_scan_timeout=settings.WEB_SCAN_TIMEOUT,
        web_scan_retries=settings.WEB_SCAN_RETRIES,
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


@router.post("/run-on-server", response_model=PipelineResult)
async def run_pipeline_on_server(request: Request, body: ServerPipelineRequest):
    """Run the full pipeline on already-registered server-side batches.

    Useful for large datasets that are pre-uploaded via /ingest/reference/register.
    All texts in the specified batches are loaded and checked against each other.
    """
    sbert_model, ai_model = _get_models(request)

    if not body.batch_ids:
        raise HTTPException(
            status_code=400, detail="Provide at least one batch_id."
        )

    # Load all texts from the specified batches
    all_texts: List[str] = []
    for bid in body.batch_ids:
        rows = await async_fetch_all_texts_by_batch(bid)
        all_texts.extend(rows)

    if not all_texts:
        raise HTTPException(
            status_code=400,
            detail="No texts found in the specified batches.",
        )

    logger.info(
        "Server pipeline run: %d texts from %d batches, methods=%s",
        len(all_texts), len(body.batch_ids), body.methods.model_dump(),
    )

    return await run_pipeline(
        texts=all_texts,
        methods_config=body.methods,
        reference_texts=all_texts,  # cross-check within the batch set
        sbert_model=sbert_model,
        ai_model=ai_model,
        fuzzy_threshold=settings.FUZZY_THRESHOLD,
        semantic_threshold=settings.SEMANTIC_THRESHOLD,
        web_scan_timeout=settings.WEB_SCAN_TIMEOUT,
        web_scan_retries=settings.WEB_SCAN_RETRIES,
    )
