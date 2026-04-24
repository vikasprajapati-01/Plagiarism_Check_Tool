"""
Shared Pydantic request/response schemas used across the entire pipeline API.

All API endpoints import their models from here — no inline BaseModel
subclasses in the router files.
"""

from __future__ import annotations

from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


# ── Pipeline method selector ──────────────────────────────────────────────────

class MethodsConfig(BaseModel):
    """Which detection methods to enable for a given pipeline run."""

    exact: bool = True
    fuzzy: bool = True
    semantic: bool = True
    ai_detection: bool = True
    web_scan: bool = False
    license_check: bool = True


# ── Per-method result payloads ────────────────────────────────────────────────

class ExactMatchResult(BaseModel):
    """Result from the SHA-256 exact-match check."""

    is_duplicate: bool
    matched_text: Optional[str] = None
    batch: Optional[str] = None


class FuzzyMatchResult(BaseModel):
    """Result from Levenshtein / Jaccard / N-gram fuzzy matching."""

    is_duplicate: bool
    scores: Dict[str, float] = Field(default_factory=dict)
    matched_text: Optional[str] = None


class SemanticMatchResult(BaseModel):
    """Result from SBERT cosine-similarity semantic matching."""

    is_duplicate: bool
    similarity: Optional[float] = None
    matched_text: Optional[str] = None


class AIDetectionResult(BaseModel):
    """Result from the RoBERTa AI-content detector."""

    is_ai_generated: bool
    confidence: float
    label: str  # "AI" | "Human" | "Unknown"


class WebScanMatchItem(BaseModel):
    """One matched source URL from the web scanner."""

    url: str
    title: str
    snippet: str
    page_excerpt: str
    similarity_scores: Dict[str, float] = Field(default_factory=dict)
    best_score: float
    fingerprint: Dict = Field(default_factory=dict)


class WebScanResult(BaseModel):
    """Result from the DuckDuckGo web-plagiarism scan."""

    found_online: bool
    sources: List[WebScanMatchItem] = Field(default_factory=list)
    error: Optional[str] = None


class LicenseDetectionResult(BaseModel):
    """Result from the SPDX / copyright license detector."""

    has_license: bool
    licenses: List[Dict] = Field(default_factory=list)
    risk_level: str = "none"


# ── Per-entry combined result ─────────────────────────────────────────────────

class EntryMethodResults(BaseModel):
    """All method results for a single text entry."""

    exact: Optional[ExactMatchResult] = None
    fuzzy: Optional[FuzzyMatchResult] = None
    semantic: Optional[SemanticMatchResult] = None
    ai_detection: Optional[AIDetectionResult] = None
    web_scan: Optional[WebScanResult] = None
    license_check: Optional[LicenseDetectionResult] = None


class EntryResult(BaseModel):
    """Full pipeline result for one input text entry."""

    entry_id: int
    original_text: str
    overall_risk: str  # "none" | "low" | "medium" | "high"
    methods: EntryMethodResults


# ── Pipeline-level summary ────────────────────────────────────────────────────

class RiskBreakdown(BaseModel):
    """Count of entries per risk tier."""

    high: int = 0
    medium: int = 0
    low: int = 0
    none: int = 0


class PipelineSummary(BaseModel):
    """Aggregate counts across all entries."""

    total_entries: int
    flagged: int
    risk_breakdown: RiskBreakdown


class PipelineResult(BaseModel):
    """Top-level response returned by POST /pipeline/run."""

    pipeline_id: str
    status: str = "completed"
    summary: PipelineSummary
    results: List[EntryResult]


# ── Batch CRUD schemas ────────────────────────────────────────────────────────

class BatchInfo(BaseModel):
    """Summary of one stored reference batch."""

    id: str
    name: Optional[str]
    entry_count: int
    created_at: Optional[str] = None


class BatchRenameRequest(BaseModel):
    """Body for PATCH /batches/{batch_id}."""

    name: str


# ── Server-side pipeline trigger ──────────────────────────────────────────────

class ServerPipelineRequest(BaseModel):
    """Body for POST /pipeline/run-on-server."""

    batch_ids: List[str]
    methods: MethodsConfig = Field(default_factory=MethodsConfig)


# ── Full pipeline (file + db) result ─────────────────────────────────────────

class ComparisonScope(str, Enum):
    files = "files"
    database = "database"
    both = "both"


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
    comparison_scope: str
    summary: dict
    row_duplicates: List[DuplicatePairResult]
    cell_duplicates: List[DuplicatePairResult]
    web_ai_results: List[WebAiEntryResult]
