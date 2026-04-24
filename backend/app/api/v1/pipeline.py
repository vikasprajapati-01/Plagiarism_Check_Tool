"""Pipeline trigger endpoints.

POST /run            — accepts uploaded files, runs the full detection pipeline.
POST /run-on-server  — runs the pipeline on already-registered server-side batches.
"""

import io
import json
import logging
from typing import Annotated, List, Optional

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse

from app.core.models import MethodsConfig, PipelineResult, PipelineRunResult, ServerPipelineRequest
from app.core.config import settings
from app.services.pipeline_runner import run_full_pipeline, run_pipeline
from app.storage.repository import async_fetch_all_texts_by_batch, async_fetch_all_texts_with_batch_info

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


@router.post("/run")
async def run_pipeline_endpoint(
    request: Request,
    files: Annotated[
        List[UploadFile],
        File(description="One or more CSV / XLSX / TXT files."),
    ] = [],
    reference_batch_ids: Optional[str] = Form(None),  # JSON array string
    methods: Optional[str] = Form(None),               # JSON object string
    comparison_scope: str = Form("both"),
    min_words_for_ai: int = Form(10),
    min_words_for_web: int = Form(10),
    min_words_for_cell_exact: int = Form(3),
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

    # ── Validate comparison scope ──────────────────────────────────────────
    allowed_scopes = {"files", "database", "both"}
    if comparison_scope not in allowed_scopes:
        raise HTTPException(
            status_code=422,
            detail="Invalid 'comparison_scope'. Must be one of: files, database, both.",
        )

    # ── Read input texts from uploaded files ──────────────────────────────────
    if not files:
        raise HTTPException(
            status_code=400, detail="Provide at least one file."
        )

    parsed_files: List[tuple[str, bytes]] = []
    for upload in files:
        contents = await upload.read()
        parsed_files.append((upload.filename or "upload.txt", contents))

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

    reference_texts_with_info: List[dict] = []
    if comparison_scope in {"database", "both"}:
        reference_texts_with_info = await async_fetch_all_texts_with_batch_info()
        if batch_ids:
            reference_texts_with_info = [
                ref for ref in reference_texts_with_info if ref.get("batch_id") in batch_ids
            ]

    logger.info(
        "Pipeline run: %d files, %d reference entries, scope=%s, methods=%s",
        len(parsed_files), len(reference_texts_with_info), comparison_scope, methods_config.model_dump(),
    )

    result = await run_full_pipeline(
        files=parsed_files,
        comparison_scope=comparison_scope,
        reference_texts_with_info=reference_texts_with_info,
        methods_config=methods_config,
        sbert_model=sbert_model,
        ai_model=ai_model,
        threshold=75.0,
        fuzzy_threshold=settings.FUZZY_THRESHOLD,
        semantic_threshold=settings.SEMANTIC_THRESHOLD,
        web_scan_timeout=settings.WEB_SCAN_TIMEOUT,
        web_scan_retries=settings.WEB_SCAN_RETRIES,
        min_words_for_ai=min_words_for_ai,
        min_words_for_web=min_words_for_web,
        min_words_for_cell_exact=min_words_for_cell_exact,
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
