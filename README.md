# Plagiarism & Duplicate Detection Tool

**Samsung PRISM Research Project**

This project provides a unified plagiarism and duplicate detection pipeline for Excel/CSV datasets.

## Table of Contents

1. [Problem Statement](#problem-statement)
2. [System Overview](#system-overview)
3. [Architecture Diagram](#architecture-diagram)
4. [Tech Stack](#tech-stack)
5. [Repository Structure](#repository-structure)
6. [Data Flow](#data-flow)
7. [Detection Methods](#detection-methods)
8. [API Reference](#api-reference)
9. [Pipeline Output Format](#pipeline-output-format)
10. [Combined Report Format](#combined-report-format)
11. [Cleaned Report](#cleaned-report)
12. [Configuration](#configuration)
13. [How to Run Locally](#how-to-run-locally)
14. [Key Design Decisions](#key-design-decisions)

## Problem Statement

Large-scale AI training datasets sourced from Excel sheets often contain:
- **Exact duplicate** entries (identical copy-paste records)
- **Near-duplicate** entries (minor edits, typos, paraphrasing)
- **Semantically similar** content (same meaning, different words)
- **AI-generated text** (content that may not be original human writing)
- **Plagiarised web content** (scraped from online sources)
- **License/copyright violations** (content with restricted usage)

This tool detects all of the above, produces structured reports, and ensures data quality before training.

## System Overview

| Component | Technology | Role |
|---|---|---|
| Backend | Python, FastAPI | Detection services, APIs |
| Frontend | Next.js (TypeScript) | Landing page, analyzer forms |

## Architecture Diagram

![Architecture diagram](Architecture.png)

## Tech Stack

### Backend
| Library | Purpose |
|---|---|
| FastAPI | REST API framework (async) |
| pandas | Excel/CSV ingestion and cleaning |
| sentence-transformers | SBERT semantic similarity (all-MiniLM-L6-v2) |
| transformers | AI-generated content detection (GPT-2 perplexity) |
| openpyxl | Excel report export + cross-compare reports |
| python-dotenv | Environment management |
| ddgs / duckduckgo_search | Web search |
| BeautifulSoup4 | Web page text extraction |
| requests | HTTP for web scan |
| rapidfuzz (optional) | License signature similarity |
| pydantic / pydantic-settings | Request/response models + config |

### Frontend
| Library | Purpose |  
|---|---|
| Next.js 16 (App Router) | React framework |
| React 19 | UI runtime |
| TypeScript | Type-safe frontend code |
| Tailwind CSS (via PostCSS) | Styling and utility classes |
| xlsx | Excel parsing for analyze flows |

## Frontend Notes

- Pages are under `frontend/app/` using the App Router.
- **Primary interface**: `frontend/app/analyze/page.tsx` — unified pipeline scan page (file upload, method toggles, query column input, result preview, report download, cleaned-file download).
- Individual method sub-pages still exist under `analyze/`: `exact`, `fuzzy`, `semantic`, `ai-detect`, `web-scan`, `license`.
- Theme is handled by `ThemeProvider` and CSS variables in `frontend/app/globals.css`.
- Theme toggles are in `frontend/app/components/Navbar.tsx` and `frontend/app/analyze/AnalyzerLayout.tsx`.
- Frontend reads `NEXT_PUBLIC_API_BASE` (default: `http://localhost:8000`) and `NEXT_PUBLIC_CLEANED_EXCEL_ENDPOINT` (default: `${NEXT_PUBLIC_API_BASE}/api/v1/reports/cleaned`) from the environment.

## Repository Structure

```
backend/
├── requirements.txt
├── scripts/
│   └── download_models.py             # Download models locally
├── tests/
│   └── test_cross_compare.py          # cross-compare tests
└── app/
    ├── __init__.py
    ├── main.py                        # FastAPI entry point, loads SBERT + GPT-2 at startup
    ├── core/
    │   ├── __init__.py
    │   ├── config.py                  # all env vars via pydantic-settings
    │   ├── models.py                  # shared Pydantic request/response schemas
    │   └── model_cache.py             # SBERT + GPT-2 singleton loader
    ├── api/
    │   └── v1/
    │       ├── router.py              # mounts all sub-routers
    │       ├── pipeline.py            # /columns, /run
    │       ├── reports.py             # /combined and /cleaned report endpoints
    │       └── compare.py             # cross-file row/cell comparison
    └── services/
        ├── __init__.py
        ├── preprocessor.py            # reads Excel/CSV, emits per-cell entries
        ├── exact_match.py             # SHA-256 exact duplicate detection
        ├── fuzzy_match.py             # Levenshtein, Jaccard, N-gram
        ├── semantic_match.py          # SBERT cosine similarity
        ├── ai_detector.py             # GPT-2 perplexity-based AI detection
        ├── web_scanner.py             # DuckDuckGo + BeautifulSoup web scan
        ├── license_detector.py        # SPDX + copyright detection
        ├── cross_compare.py           # cross-sheet row/cell comparison
        └── pipeline_runner.py         # orchestrates all detection methods

frontend/
├── README.md
├── package.json
├── package-lock.json
├── next.config.ts
├── eslint.config.mjs
├── postcss.config.mjs
├── tsconfig.json
├── app/
│   ├── layout.tsx
│   ├── page.tsx
│   ├── globals.css
│   ├── favicon.ico
│   ├── lib/                           # (reserved for shared utilities)
│   ├── components/
│   │   ├── Navbar.tsx
│   │   ├── HeroSection.tsx
│   │   ├── AboutSection.tsx
│   │   ├── Footer.tsx
│   │   ├── DetectionSelector.tsx
│   │   ├── PreviewPanel.tsx           # report & Excel preview with download
│   │   └── ThemeProvider.tsx
│   └── analyze/
│       ├── page.tsx                   # unified pipeline scan page (PRIMARY)
│       ├── AnalyzerLayout.tsx
│       ├── folder/                    # folder-upload helper route
│       ├── exact/page.tsx
│       ├── fuzzy/page.tsx
│       ├── semantic/page.tsx
│       ├── ai-detect/page.tsx
│       ├── web-scan/page.tsx
│       └── license/page.tsx
└── public/
    ├── file.svg
    ├── globe.svg
    ├── next.svg
    ├── vercel.svg
    └── window.svg
```

## Data Flow

### Pipeline Run Flow (files to results)
1. Upload file(s) to `POST /api/v1/pipeline/run` and pick a `target_column` (or leave as `"auto"`).
2. Optionally call `POST /api/v1/pipeline/columns` first to see what columns are available.
3. Pipeline reads and normalizes entries from the target column.
4. Exact/fuzzy/semantic/AI/web/license methods run in-memory; cross-compare runs only for `.xlsx` files.
5. API returns a `PipelineRunResult` JSON payload.

## Detection Methods

| Method | Algorithm | Thresholds | File |
|---|---|---|---|
| Exact Match | SHA-256 hash comparison | 100% identical | services/exact_match.py |
| Fuzzy Match | Levenshtein, Jaccard, N-gram | 0.85 default (Jaccard 0.68, N-gram 0.765) | services/fuzzy_match.py |
| Semantic Match | SBERT cosine similarity | 0.85 | services/semantic_match.py |
| AI Detection | GPT-2 perplexity scoring | Returns confidence 0.0–1.0 | services/ai_detector.py |
| Web Scanner | DuckDuckGo + BeautifulSoup + windowed similarity | 0.50 similarity (default), 10s timeout, 1 retry | services/web_scanner.py |
| License Detector | SPDX + copyright patterns | N/A | services/license_detector.py |
| Cross-Compare | Row/Cell comparison across Excel files | 75% (default) | services/cross_compare.py |
| Pipeline Runner | Orchestrates selected methods | N/A | services/pipeline_runner.py |

## API Reference

Base URL: http://localhost:8000
Docs: http://localhost:8000/docs

### Pipeline — /api/v1/pipeline
| Method | Path | Description |
|---|---|---|
| POST | /columns | Discover available column names from uploaded files (call before `/run` to pick `target_column`); auto-suggests `Query` column if found |
| POST | /run | Unified detection run across selected methods; accepts `target_column` (or `"auto"`), `methods` JSON, `color_report` flag, and optional inline Excel download |

### Reports — /api/v1/reports
| Method | Path | Description |
|---|---|---|
| POST | /combined | Generate 3-sheet Excel report from a pipeline result; supports `color_report` flag for colour-coded rows |
| POST | /cleaned | Accept original `.xlsx` files + pipeline result JSON → return cleaned `.xlsx` (or `.zip` for multiple files) with duplicate/plagiarised rows removed |

### Compare — /api/v1/compare
| Method | Path | Description |
|---|---|---|
| POST | /cross | Cross-file row/cell comparison (JSON result, supports Query-column targeting) |
| POST | /report | Cross-file comparison report (.xlsx) |
| POST | /colored | Color-coded workbook (.xlsx) |

## Pipeline Output Format

### PipelineRunResult (top-level)
```json
{
        "pipeline_id": "a1b2c3d4-...",
        "status": "completed",
        "summary": {
                "total_files": 2,
                "total_row_duplicates": 3,
                "total_cell_duplicates": 1
        },
        "row_duplicates": [
                {
                        "original": "file1.xlsx-Row 10",
                        "duplicate": "file2.xlsx-Row 10",
                        "type": "Near",
                        "similarity_pct": 84.0
                }
        ],
        "cell_duplicates": [],
        "web_ai_results": [
                {
                        "original": "file1.xlsx-A10",
                        "plagiarised": "No",
                        "source": "N/A",
                        "ai_detected_pct": 12.0
                }
        ]
}
```

## Combined Report Format

The combined Excel report (`POST /reports/combined`) includes three sheets:
1. **Row-to-Row** — duplicate row pairs with similarity %
2. **Cell-to-Cell** — duplicate cell pairs with similarity %
3. **AI-Plagiarism** — web plagiarism + AI detection results per cell

Set `color_report: true` in the request body to enable colour-coded row highlights:
- 🔴 Red — Exact duplicates / web-plagiarised entries
- 🟡 Yellow — Near-duplicate rows
- 🟢 Green — Non-plagiarised entries
- AI Detected (%) cell shading: ≥80 % → red, ≥50 % → orange, ≥20 % → yellow

## Cleaned Report

`POST /reports/cleaned` strips flagged rows from the original `.xlsx` file(s) and returns a sanitised workbook.

**Rules applied:**
- `row_duplicates` / `cell_duplicates` — the *duplicate* side row is deleted; the *original* row is kept.
- `web_ai_results` — the row is deleted only when `plagiarised == "Yes"`; AI-only entries are left untouched.
- Only `.xlsx` files are processed (CSV files are ignored).
- Row 1 (header) is **never** deleted.
- Single file → returns `.xlsx`; multiple files → returns `.zip`.

## Configuration

### Backend — `backend/.env`

```env
# ML Models
EMBEDDING_MODEL=all-MiniLM-L6-v2
GPT2_MODEL=gpt2

# Detection thresholds
FUZZY_THRESHOLD=0.85
SEMANTIC_THRESHOLD=0.85

# Web scanner
WEB_SCAN_TIMEOUT=10        # seconds per HTTP request
WEB_SCAN_RETRIES=1         # retries per query
WEB_SCAN_MAX_QUERIES=1     # DuckDuckGo queries per cell
WEB_SCAN_MAX_RESULTS=2     # URLs fetched per query
WEB_SCAN_MAX_SCAN_TIME=25  # max seconds per cell scan
WEB_SCAN_OVERALL_TIMEOUT=60 # hard cap for the whole web-scan phase

# Logging
LOG_LEVEL=INFO
```

### Frontend — `frontend/.env.local`

```env
NEXT_PUBLIC_API_BASE=http://localhost:8000
# Override only if the cleaned-file endpoint differs from the default:
# NEXT_PUBLIC_CLEANED_EXCEL_ENDPOINT=http://localhost:8000/api/v1/reports/cleaned
```

## How to Run Locally

### Backend
```bash
cd backend
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload
```

### Frontend
```bash
cd frontend
npm install
npm run dev
```

## Key Design Decisions

| Decision | Reason |
|---|---|
| FastAPI over Flask/Django | Async-first APIs for concurrent web scanning and batch inference |
| SBERT all-MiniLM-L6-v2 | Balanced performance for sentence-level similarity |
| GPT-2 AI detector | High-accuracy AI detection with swap via env var |
| DuckDuckGo web scan | No API key required; controlled retries and timeout |
| Per-cell provenance | Enables exact row/column traceability in reports |
| Startup model cache | Single-load model initialization via lifespan |
