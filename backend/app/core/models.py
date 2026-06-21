"""
Shared Pydantic request/response schemas used across the pipeline API.

All API endpoints import their models from here — no inline BaseModel
subclasses in the router files.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel, Field


# ── Pipeline method selector ──────────────────────────────────────────────────

class MethodsConfig(BaseModel):
    """Which detection methods to enable for a given pipeline run."""

    exact: bool = True
    fuzzy: bool = True
    semantic: bool = True
    ai_detection: bool = True
    web_scan: bool = True
    license_check: bool = True


# ── Full pipeline result models ───────────────────────────────────────────────

class DuplicatePairResult(BaseModel):
    original: str
    duplicate: str
    type: str
    similarity_pct: float


class WebAiEntryResult(BaseModel):
    original: str
    plagiarised: str
    source: str
    ai_detected_pct: float


class PipelineRunResult(BaseModel):
    pipeline_id: str
    status: str
    summary: dict
    row_duplicates: List[DuplicatePairResult]
    cell_duplicates: List[DuplicatePairResult]
    web_ai_results: List[WebAiEntryResult]
