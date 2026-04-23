"""Pipeline trigger endpoints.

POST /run            — accepts uploaded files, runs the full detection pipeline.
POST /run-on-server  — runs the pipeline on already-registered server-side batches.
"""

import json
import logging
from typing import Annotated, List, Optional

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile

from app.core.models import MethodsConfig, PipelineResult, ServerPipelineRequest
from app.core.config import settings
from app.services.pipeline_runner import run_pipeline
from app.services.preprocessor import read_all_text_from_file
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


@router.post("/run", response_model=PipelineResult)
async def run_pipeline_endpoint(
    request: Request,
    files: Annotated[
        List[UploadFile],
        File(description="One or more CSV / XLSX / TXT files."),
    ] = [],
    reference_batch_ids: Optional[str] = Form(None),  # JSON array string
    methods: Optional[str] = Form(None),               # JSON object string
    download_report: bool = Form(False),
    report_format: str = Form("excel"),
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

    input_texts: List[str] = []
    for upload in files:
        contents = await upload.read()
        try:
            rows, _ = read_all_text_from_file(upload.filename or "upload.txt", contents)
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail=f"Error reading '{upload.filename}': {exc}",
            ) from exc
        input_texts.extend(rows)

    if not input_texts:
        raise HTTPException(status_code=400, detail="No text found in the uploaded files.")

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

    reference_texts: List[str] = []
    if batch_ids:
        for bid in batch_ids:
            texts = await async_fetch_all_texts_by_batch(bid)
            reference_texts.extend(texts)
    else:
        reference_texts = await async_fetch_all_texts_by_batch()

    logger.info(
        "Pipeline run: %d input texts, %d reference texts, methods=%s",
        len(input_texts), len(reference_texts), methods_config.model_dump(),
    )

    return await run_pipeline(
        texts=input_texts,
        methods_config=methods_config,
        reference_texts=reference_texts,
        sbert_model=sbert_model,
        ai_model=ai_model,
        fuzzy_threshold=settings.FUZZY_THRESHOLD,
        semantic_threshold=settings.SEMANTIC_THRESHOLD,
        web_scan_timeout=settings.WEB_SCAN_TIMEOUT,
        web_scan_retries=settings.WEB_SCAN_RETRIES,
    )


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
