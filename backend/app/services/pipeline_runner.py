"""Unified detection pipeline orchestrator.

Runs all enabled detection methods concurrently for each input text and
combines their results into a single PipelineResult.

Risk hierarchy: none < low < medium < high
Overall risk per entry = highest risk across all enabled methods.
"""

import asyncio
import io
import logging
import uuid
import zipfile
from typing import Any, Dict, List, Optional, Tuple

from app.core.config import settings
from app.core.models import (
    AIDetectionResult,
    DuplicatePairResult,
    EntryMethodResults,
    EntryResult,
    ExactMatchResult,
    FuzzyMatchResult,
    LicenseDetectionResult,
    MethodsConfig,
    PipelineResult,
    PipelineRunResult,
    PipelineSummary,
    RiskBreakdown,
    SemanticMatchResult,
    WebAiEntryResult,
    WebScanMatchItem,
    WebScanResult,
)
from app.services.ai_detector import detect_ai_content
from app.services.cross_compare import run_cross_comparison
from app.services.exact_match import sha256_hash
from app.services.fuzzy_match import is_fuzzy_duplicate
from app.services.license_detector import detect_license
from app.services.preprocessor import preprocess_text, read_all_text_from_file
from app.services.semantic_match import cosine_similarity
from app.services.web_scanner import scan_text_online

logger = logging.getLogger(__name__)

# Risk ordering for comparison
_RISK_ORDER: Dict[str, int] = {"none": 0, "low": 1, "medium": 2, "high": 3}


def _higher_risk(a: str, b: str) -> str:
    """Return the higher of two risk level strings."""
    return a if _RISK_ORDER.get(a, 0) >= _RISK_ORDER.get(b, 0) else b


def _ai_risk(confidence: float, is_ai: bool) -> str:
    """Map AI detection confidence to a risk level."""
    if not is_ai:
        return "none"
    if confidence >= 0.90:
        return "high"
    if confidence >= 0.75:
        return "medium"
    return "low"


def _semantic_risk(similarity: Optional[float], is_dup: bool) -> str:
    """Map semantic similarity score to a risk level."""
    if not is_dup or similarity is None:
        return "none"
    if similarity >= 0.95:
        return "high"
    if similarity >= 0.85:
        return "medium"
    return "low"


def _fuzzy_risk(scores: dict, is_dup: bool) -> str:
    """Map fuzzy scores to a risk level."""
    if not is_dup:
        return "none"
    best = max(scores.values()) if scores else 0.0
    if best >= 0.95:
        return "high"
    if best >= 0.85:
        return "medium"
    return "low"


async def _run_exact(
    text: str,
    preprocessed: str,
    reference_texts: List[str],
) -> ExactMatchResult:
    """Check for exact (SHA-256) duplicate against reference_texts."""
    text_hash = sha256_hash(preprocessed)
    ref_map = {sha256_hash(preprocess_text(r)): r for r in reference_texts}
    matched = ref_map.get(text_hash)
    return ExactMatchResult(
        is_duplicate=matched is not None,
        matched_text=matched,
    )


async def _run_fuzzy(
    text: str,
    reference_texts: List[str],
    threshold: float,
) -> FuzzyMatchResult:
    """Find the best fuzzy match in reference_texts."""
    is_dup, matched, scores = await is_fuzzy_duplicate(text, reference_texts, threshold)
    return FuzzyMatchResult(
        is_duplicate=is_dup,
        scores=scores or {},
        matched_text=matched,
    )


async def _run_semantic(
    idx: int,
    input_vecs: List[List[float]],
    reference_texts: List[str],
    ref_vecs: List[List[float]],
    threshold: float,
) -> SemanticMatchResult:
    """Find the best semantic match for one input text."""
    if not ref_vecs:
        return SemanticMatchResult(is_duplicate=False)

    query_vec = input_vecs[idx]
    best_score = -1.0
    best_match: Optional[str] = None

    for j, ref_vec in enumerate(ref_vecs):
        score = cosine_similarity(query_vec, ref_vec)
        if score > best_score:
            best_score = score
            best_match = reference_texts[j]

    is_dup = best_score >= threshold
    return SemanticMatchResult(
        is_duplicate=is_dup,
        similarity=round(best_score, 4) if best_score >= 0 else None,
        matched_text=best_match if is_dup else None,
    )


async def _run_ai(text: str, detector: Any) -> AIDetectionResult:
    """Run AI-content detection on one text."""
    result = await detect_ai_content(text, detector)
    return AIDetectionResult(
        is_ai_generated=result["label"] == "AI",
        confidence=result["confidence"],
        label=result["label"],
    )


async def _run_web(text: str, timeout: int, retries: int) -> WebScanResult:
    """Scan the web for plagiarism of one text."""
    raw = await scan_text_online(text, timeout=timeout, retries=retries)
    sources = [
        WebScanMatchItem(
            url=m.url,
            title=m.title,
            snippet=m.snippet,
            page_excerpt=m.page_excerpt,
            similarity_scores=m.similarity_scores,
            best_score=m.best_score,
            fingerprint=m.fingerprint,
        )
        for m in raw.matches
    ]
    return WebScanResult(
        found_online=raw.is_plagiarism,
        sources=sources,
        error=raw.error,
    )


async def _run_license(text: str) -> LicenseDetectionResult:
    """Run license/copyright detection on one text."""
    raw = await detect_license(text)
    licenses = [
        {
            "license_name": m.license_name,
            "spdx_id": m.spdx_id,
            "confidence": m.confidence,
            "license_url": m.license_url,
            "snippet": m.snippet,
        }
        for m in raw.licenses_detected
    ]
    return LicenseDetectionResult(
        has_license=raw.has_license,
        licenses=licenses,
        risk_level=raw.risk_level,
    )


# ── Main pipeline entry point ─────────────────────────────────────────────────

async def run_pipeline(
    texts: List[str],
    methods_config: MethodsConfig,
    reference_texts: List[str],
    sbert_model: Any,
    ai_model: Any,
    fuzzy_threshold: float = 0.85,
    semantic_threshold: float = 0.85,
    web_scan_timeout: int = 10,
    web_scan_retries: int = 3,
) -> PipelineResult:
    """Orchestrate all detection methods and return a unified PipelineResult.

    Steps:
      1. Preprocess all input and reference texts once.
      2. If semantic is enabled, encode all texts in a single batch forward pass.
      3. For each text, run all enabled methods concurrently via asyncio.gather().
      4. Combine per-method results and derive overall_risk per entry.
      5. Build and return PipelineResult with summary statistics.
    """
    pipeline_id = str(uuid.uuid4())
    logger.info(
        "Pipeline %s started: %d texts, methods=%s",
        pipeline_id, len(texts), methods_config.model_dump(),
    )

    # Step 1: Preprocess
    preprocessed_inputs = [preprocess_text(t) for t in texts]
    preprocessed_refs = [preprocess_text(r) for r in reference_texts]

    # Step 2: Encode all texts in one batch (avoids N separate forward passes)
    input_vecs: List[List[float]] = []
    ref_vecs: List[List[float]] = []

    if methods_config.semantic and sbert_model is not None:
        loop = asyncio.get_event_loop()
        all_texts = preprocessed_inputs + preprocessed_refs
        if all_texts:
            from app.services.semantic_match import encode_texts as _encode
            from functools import partial
            all_vecs = await loop.run_in_executor(
                None, partial(_encode, all_texts, sbert_model, False)
            )
            input_vecs = all_vecs[: len(texts)]
            ref_vecs = all_vecs[len(texts):]

    # Step 3 & 4: Per-entry processing
    entry_results: List[EntryResult] = []

    for idx, (raw_text, preprocessed) in enumerate(zip(texts, preprocessed_inputs)):
        tasks = {}

        if methods_config.exact:
            tasks["exact"] = _run_exact(raw_text, preprocessed, reference_texts)
        if methods_config.fuzzy:
            tasks["fuzzy"] = _run_fuzzy(raw_text, reference_texts, fuzzy_threshold)
        if methods_config.semantic and input_vecs:
            tasks["semantic"] = _run_semantic(idx, input_vecs, reference_texts, ref_vecs, semantic_threshold)
        if methods_config.ai_detection and ai_model is not None:
            tasks["ai_detection"] = _run_ai(raw_text, ai_model)
        if methods_config.web_scan:
            tasks["web_scan"] = _run_web(raw_text, web_scan_timeout, web_scan_retries)
        if methods_config.license_check:
            tasks["license_check"] = _run_license(raw_text)

        # Run all enabled methods concurrently
        keys = list(tasks.keys())
        results = await asyncio.gather(*tasks.values(), return_exceptions=True)
        method_results: Dict[str, Any] = {}
        for key, result in zip(keys, results):
            if isinstance(result, Exception):
                logger.warning("Method %s failed for entry %d: %s", key, idx, result)
            else:
                method_results[key] = result

        # Derive overall_risk
        overall_risk = "none"

        if "exact" in method_results:
            r: ExactMatchResult = method_results["exact"]
            if r.is_duplicate:
                overall_risk = _higher_risk(overall_risk, "high")

        if "fuzzy" in method_results:
            r2: FuzzyMatchResult = method_results["fuzzy"]
            overall_risk = _higher_risk(overall_risk, _fuzzy_risk(r2.scores, r2.is_duplicate))

        if "semantic" in method_results:
            r3: SemanticMatchResult = method_results["semantic"]
            overall_risk = _higher_risk(overall_risk, _semantic_risk(r3.similarity, r3.is_duplicate))

        if "ai_detection" in method_results:
            r4: AIDetectionResult = method_results["ai_detection"]
            overall_risk = _higher_risk(overall_risk, _ai_risk(r4.confidence, r4.is_ai_generated))

        if "web_scan" in method_results:
            r5: WebScanResult = method_results["web_scan"]
            if r5.found_online:
                overall_risk = _higher_risk(overall_risk, "medium")

        if "license_check" in method_results:
            r6: LicenseDetectionResult = method_results["license_check"]
            overall_risk = _higher_risk(overall_risk, r6.risk_level)

        entry_results.append(EntryResult(
            entry_id=idx + 1,
            original_text=raw_text,
            overall_risk=overall_risk,
            methods=EntryMethodResults(
                exact=method_results.get("exact"),
                fuzzy=method_results.get("fuzzy"),
                semantic=method_results.get("semantic"),
                ai_detection=method_results.get("ai_detection"),
                web_scan=method_results.get("web_scan"),
                license_check=method_results.get("license_check"),
            ),
        ))

    # Step 5: Build summary
    flagged = sum(1 for e in entry_results if e.overall_risk != "none")
    breakdown = RiskBreakdown(
        high=sum(1 for e in entry_results if e.overall_risk == "high"),
        medium=sum(1 for e in entry_results if e.overall_risk == "medium"),
        low=sum(1 for e in entry_results if e.overall_risk == "low"),
        none=sum(1 for e in entry_results if e.overall_risk == "none"),
    )

    logger.info(
        "Pipeline %s completed: %d entries, %d flagged", pipeline_id, len(texts), flagged
    )

    return PipelineResult(
        pipeline_id=pipeline_id,
        status="completed",
        summary=PipelineSummary(
            total_entries=len(texts),
            flagged=flagged,
            risk_breakdown=breakdown,
        ),
        results=entry_results,
    )


async def run_full_pipeline(
    files: List[Tuple[str, bytes]],
    methods_config: MethodsConfig,
    sbert_model: Any,
    ai_model: Any,
    target_column: str = "Query",
    threshold: float = 75.0,
    fuzzy_threshold: float = 0.85,
    semantic_threshold: float = 0.85,
    web_scan_timeout: int = 10,
    web_scan_retries: int = 3,
) -> PipelineRunResult:
    pipeline_id = str(uuid.uuid4())
    row_duplicates: List[DuplicatePairResult] = []
    cell_duplicates: List[DuplicatePairResult] = []
    web_ai_results: List[WebAiEntryResult] = []

    def _clamp_pct(value: float) -> float:
        return max(0.0, min(100.0, value))

    def _ai_probability(ai_payload: Optional[dict]) -> float:
        """Convert detector payload into probability that text is AI-generated.

        detect_ai_content() returns a dict with:
          - label: "AI" | "Human" | "Unknown"
          - confidence: score for the predicted label
        For "Human" predictions, P(AI) is approximated as (1 - confidence).
        """
        if not ai_payload:
            return 0.0
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

    def _extract_xlsx_from_zip(filename: str, contents: bytes) -> List[Tuple[str, bytes]]:
        if not filename.lower().endswith(".zip"):
            return []
        extracted: List[Tuple[str, bytes]] = []
        try:
            with zipfile.ZipFile(io.BytesIO(contents)) as zf:
                for zip_info in zf.infolist():
                    if zip_info.is_dir():
                        continue
                    inner_name = zip_info.filename
                    if inner_name.lower().endswith(".xlsx"):
                        extracted.append((inner_name, zf.read(zip_info)))
        except Exception as exc:
            logger.warning("Failed to extract XLSX from %s: %s", filename, exc)
        return extracted

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

    try:
        loop = asyncio.get_event_loop()
        from functools import partial

        compare_files: List[Tuple[str, bytes]] = []
        for fname, fbytes in files:
            if fname.lower().endswith(".xlsx"):
                compare_files.append((fname, fbytes))
            elif fname.lower().endswith(".zip"):
                compare_files.extend(_extract_xlsx_from_zip(fname, fbytes))

        row_matches, cell_matches = [], []
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
        for entries in entries_by_file.values():
            for entry in entries:
                col = entry.get("column_name", "").strip().lower()
                if col != target_column.strip().lower():
                    continue
                raw_text = entry.get("text", "")
                if not raw_text or not raw_text.strip():
                    continue
                target_entries.append(entry)

    # Throttle web/AI/license processing so large uploads don't overwhelm the executor
    # and trigger the global WEB_SCAN_OVERALL_TIMEOUT.
    _max_concurrency = 4
    _entry_semaphore = asyncio.Semaphore(_max_concurrency)

    async def _bounded_process(entry: dict) -> Optional[WebAiEntryResult]:
        async with _entry_semaphore:
            return await _process_single_entry(entry)

    async def _process_single_entry(entry: dict) -> Optional[WebAiEntryResult]:
        raw_text = entry.get("text", "")
        run_ai = methods_config.ai_detection and ai_model is not None
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
                raw_text, ai_model
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

        return WebAiEntryResult(
            original=f"{entry.get('source_file')}-{entry.get('cell_ref')}",
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
