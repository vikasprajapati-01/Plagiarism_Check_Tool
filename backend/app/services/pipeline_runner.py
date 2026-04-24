"""Unified detection pipeline orchestrator.

Runs all enabled detection methods concurrently for each input text and
combines their results into a single PipelineResult.

Risk hierarchy: none < low < medium < high
Overall risk per entry = highest risk across all enabled methods.
"""

import asyncio
import logging
import uuid
from typing import Any, Dict, List, Optional, Tuple

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
from app.services.semantic_match import encode_texts, cosine_similarity
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
    comparison_scope: str,
    reference_texts_with_info: List[dict],
    methods_config: MethodsConfig,
    sbert_model: Any,
    ai_model: Any,
    threshold: float = 75.0,
    fuzzy_threshold: float = 0.85,
    semantic_threshold: float = 0.85,
    web_scan_timeout: int = 10,
    web_scan_retries: int = 3,
    min_words_for_ai: int = 10,
    min_words_for_web: int = 10,
    min_words_for_cell_exact: int = 3,
) -> PipelineRunResult:
    pipeline_id = str(uuid.uuid4())
    row_duplicates: List[DuplicatePairResult] = []
    cell_duplicates: List[DuplicatePairResult] = []
    web_ai_results: List[WebAiEntryResult] = []

    def _clamp_pct(value: float) -> float:
        return max(0.0, min(100.0, value))

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

    if comparison_scope in {"files", "both"}:
        try:
            loop = asyncio.get_event_loop()
            from functools import partial

            row_matches, cell_matches = await loop.run_in_executor(
                None,
                partial(
                    run_cross_comparison,
                    files,
                    threshold,
                    do_row_compare=methods_config.exact or methods_config.fuzzy,
                    do_cell_compare=methods_config.exact or methods_config.fuzzy,
                ),
            )

            filtered_cell_matches = []
            for match in cell_matches:
                original_words = len(str(match.original_text).split())
                duplicate_words = len(str(match.duplicate_text).split())
                if original_words >= min_words_for_cell_exact and duplicate_words >= min_words_for_cell_exact:
                    filtered_cell_matches.append(match)
            cell_matches = filtered_cell_matches

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

    if comparison_scope in {"database", "both"} and reference_texts_with_info:
        db_duplicate_pairs: List[DuplicatePairResult] = []
        ref_cleaned: List[str] = []
        ref_by_cleaned: Dict[str, dict] = {}
        ref_hashes: Dict[str, List[dict]] = {}

        for ref in reference_texts_with_info:
            cleaned = ref.get("cleaned_text") or preprocess_text(ref.get("raw_text", ""))
            ref["cleaned_text"] = cleaned
            ref_cleaned.append(cleaned)
            if cleaned not in ref_by_cleaned:
                ref_by_cleaned[cleaned] = ref
            ref_hash = sha256_hash(cleaned)
            ref_hashes.setdefault(ref_hash, []).append(ref)

        entry_vecs: List[List[float]] = []
        ref_vecs: List[List[float]] = []

        if methods_config.semantic and sbert_model is not None and all_entries and ref_cleaned:
            try:
                loop = asyncio.get_event_loop()
                from functools import partial

                all_texts = [e.get("cleaned_text", "") for e in all_entries] + ref_cleaned
                all_vecs = await loop.run_in_executor(
                    None, partial(encode_texts, all_texts, sbert_model, False)
                )
                entry_vecs = all_vecs[: len(all_entries)]
                ref_vecs = all_vecs[len(all_entries):]
            except Exception as exc:
                logger.warning("Semantic encoding failed: %s", exc)

        for entry_idx, entry in enumerate(all_entries):
            entry_cleaned = entry.get("cleaned_text", "")
            original_label = f"{entry.get('source_file')}-Row {entry.get('row_number')}"

            if methods_config.exact:
                try:
                    entry_hash = entry.get("sha256") or sha256_hash(entry_cleaned)
                    for ref in ref_hashes.get(entry_hash, []):
                        similarity_pct = 100.0
                        db_duplicate_pairs.append(
                            DuplicatePairResult(
                                original=original_label,
                                duplicate=f"{ref.get('batch_name')}-DB entry",
                                type="Exact",
                                similarity_pct=similarity_pct,
                            )
                        )
                except Exception as exc:
                    logger.warning("Exact DB compare failed: %s", exc)

            if methods_config.fuzzy and ref_cleaned:
                try:
                    is_dup, matched, scores = await is_fuzzy_duplicate(
                        entry_cleaned, ref_cleaned, fuzzy_threshold
                    )
                    if is_dup:
                        best_score = max(scores.values()) if scores else 0.0
                        similarity_pct = _clamp_pct(best_score * 100)
                        ref = ref_by_cleaned.get(matched or "")
                        db_duplicate_pairs.append(
                            DuplicatePairResult(
                                original=original_label,
                                duplicate=f"{(ref.get('batch_name') if ref else 'Unknown')}-DB entry",
                                type="Exact" if similarity_pct == 100.0 else "Near",
                                similarity_pct=similarity_pct,
                            )
                        )
                except Exception as exc:
                    logger.warning("Fuzzy DB compare failed: %s", exc)

            if methods_config.semantic and entry_vecs and ref_vecs:
                try:
                    query_vec = entry_vecs[entry_idx]
                    best_score = -1.0
                    best_idx = -1
                    for ref_idx, ref_vec in enumerate(ref_vecs):
                        score = cosine_similarity(query_vec, ref_vec)
                        if score > best_score:
                            best_score = score
                            best_idx = ref_idx

                    if best_score >= semantic_threshold and best_idx >= 0:
                        similarity_pct = _clamp_pct(best_score * 100)
                        ref = reference_texts_with_info[best_idx]
                        db_duplicate_pairs.append(
                            DuplicatePairResult(
                                original=original_label,
                                duplicate=f"{ref.get('batch_name')}-DB entry",
                                type="Exact" if similarity_pct == 100.0 else "Near",
                                similarity_pct=similarity_pct,
                            )
                        )
                except Exception as exc:
                    logger.warning("Semantic DB compare failed: %s", exc)

        deduped: Dict[tuple, DuplicatePairResult] = {}
        for pair in db_duplicate_pairs:
            key = (pair.original, pair.duplicate)
            if key not in deduped or pair.similarity_pct > deduped[key].similarity_pct:
                deduped[key] = pair
        row_duplicates.extend(list(deduped.values()))

    if methods_config.web_scan or methods_config.ai_detection or methods_config.license_check:
        for entries in entries_by_file.values():
            for entry in entries:
                raw_text = entry.get("text", "")
                word_count = len(str(raw_text).split())
                run_ai = methods_config.ai_detection and ai_model is not None and word_count >= min_words_for_ai
                run_web = methods_config.web_scan and word_count >= min_words_for_web
                run_license = methods_config.license_check and word_count >= min_words_for_ai

                if not (run_ai or run_web or run_license):
                    continue

                tasks: Dict[str, Any] = {}
                if run_web:
                    tasks["web_scan"] = scan_text_online(
                        raw_text,
                        timeout=web_scan_timeout,
                        retries=web_scan_retries,
                    )
                if run_ai:
                    tasks["ai_detection"] = detect_ai_content(raw_text, ai_model)
                if run_license:
                    tasks["license_check"] = detect_license(raw_text)

                results = await asyncio.gather(*tasks.values(), return_exceptions=True)
                method_results: Dict[str, Any] = {}
                for key, result in zip(tasks.keys(), results):
                    if isinstance(result, Exception):
                        logger.warning("Method %s failed for web/ai scan: %s", key, result)
                    else:
                        method_results[key] = result

                web_result = method_results.get("web_scan")
                ai_result = method_results.get("ai_detection")

                is_plagiarised = False
                source_url: Optional[str] = None
                if web_result is not None:
                    is_plagiarised = getattr(web_result, "is_plagiarism", False)
                    matches = getattr(web_result, "matches", []) or []
                    if matches:
                        source_url = getattr(matches[0], "url", None)

                ai_pct = 0.0
                if ai_result is not None:
                    label = ai_result.get("label")
                    confidence = float(ai_result.get("confidence", 0.0))
                    if label == "AI":
                        ai_pct = _clamp_pct(round(confidence * 100, 1))

                source_str = source_url if source_url else "N/A"
                plagiarised_str = "Yes" if is_plagiarised else "No"

                if run_web or run_ai:
                    web_ai_results.append(
                        WebAiEntryResult(
                            original=f"{entry.get('source_file')}-{entry.get('cell_ref')}",
                            plagiarised=plagiarised_str,
                            source=source_str,
                            ai_detected_pct=ai_pct,
                        )
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
    }

    return PipelineRunResult(
        pipeline_id=pipeline_id,
        status="completed",
        comparison_scope=comparison_scope,
        summary=summary,
        row_duplicates=row_duplicates,
        cell_duplicates=cell_duplicates,
        web_ai_results=web_ai_results,
    )
