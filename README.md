# Plagiarism & Duplicate Detection Tool

**Samsung PRISM Research Project**

This project provides a unified plagiarism and duplicate detection pipeline for Excel/CSV/TXT datasets (plus ZIP bundles of those files)

## Table of Contents

1. [Problem Statement](#problem-statement)
2. [System Overview](#system-overview)
3. [Architecture Diagram](#architecture-diagram)
4. [Tech Stack](#tech-stack)
5. [Repository Structure](#repository-structure)
6. [Database Schema](#database-schema)
7. [Data Flow](#data-flow)
8. [Detection Methods](#detection-methods)
9. [API Reference](#api-reference)
10. [Pipeline Output Format](#pipeline-output-format)
11. [Combined Report Format](#combined-report-format)
12. [Cleaned Report](#cleaned-report)
13. [Configuration](#configuration)
14. [How to Run Locally](#how-to-run-locally)
15. [Key Design Decisions](#key-design-decisions)

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
| Backend | Python, FastAPI | Detection services, database access, APIs |
| Frontend | Next.js (TypeScript) | Landing page, analyzer forms, batch registration |
| Database | PostgreSQL + pgvector (Supabase) | Reference batches, per-cell data, embeddings |

## Architecture Diagram

![Architecture diagram](Architecture.png)

## Tech Stack

### Backend
| Library | Purpose |
|---|---|
| FastAPI | REST API framework (async) |
| PostgreSQL + pgvector | Relational data + vector embeddings |
| asyncpg / psycopg2 | Async and sync Postgres drivers |
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
| pdfjs-dist | PDF parsing for analyze flows |
| xlsx | Excel parsing for analyze flows |

## Frontend Notes

- Pages are under `frontend/app/` using the App Router.
- **Primary interface**: `frontend/app/analyze/page.tsx` — unified pipeline scan page (file upload, method toggles, column selection, result preview, report download, cleaned-file download).
- Individual method sub-pages still exist under `analyze/`: `exact`, `fuzzy`, `semantic`, `ai-detect`, `web-scan`, `license`, `cross-batch`.
- Theme is handled by `ThemeProvider` and CSS variables in `frontend/app/globals.css`.
- Theme toggles are in `frontend/app/components/Navbar.tsx` and `frontend/app/analyze/AnalyzerLayout.tsx`.
- Frontend reads `NEXT_PUBLIC_API_BASE` (default: `http://localhost:8000`) and `NEXT_PUBLIC_CLEANED_EXCEL_ENDPOINT` (default: `${NEXT_PUBLIC_API_BASE}/api/v1/reports/cleaned`) from the environment.

## Repository Structure

```
backend/
├── requirements.txt
├── scripts/
│   └── check_db.py                    # DB connectivity check
│   └── compare_server.py               # minimal compare-only FastAPI server
│   └── demo_query_column.py            # sample workbook + Query-column demo
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
    │       ├── batches.py             # list/delete/rename batches
    │       ├── ingest.py              # file upload, preprocessing, batch registration
    │       ├── pipeline.py            # /columns, /run, /run-on-server
    │       ├── reports.py             # /combined and /cleaned report endpoints
    │       └── compare.py             # cross-file row/cell comparison
    ├── services/
    │   ├── __init__.py
    │   ├── preprocessor.py            # reads Excel/CSV/TXT (+ ZIP bundles), emits per-cell entries
    │   ├── exact_match.py             # SHA-256 exact duplicate detection
    │   ├── fuzzy_match.py             # Levenshtein, Jaccard, N-gram
    │   ├── semantic_match.py          # SBERT cosine similarity
    │   ├── ai_detector.py             # GPT-2 perplexity-based AI detection
    │   ├── web_scanner.py             # DuckDuckGo + BeautifulSoup web scan
    │   ├── license_detector.py        # SPDX + copyright detection
    │   ├── cross_compare.py           # cross-sheet row/cell comparison
    │   └── pipeline_runner.py         # orchestrates all detection methods
    └── storage/
        └── repository.py              # all DB queries via asyncpg pool

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
│   ├── analyze/
│   │   ├── page.tsx                   # unified pipeline scan page (PRIMARY)
│   │   ├── AnalyzerLayout.tsx
│   │   ├── folder/                    # folder-upload helper route
│   │   ├── exact/page.tsx
│   │   ├── fuzzy/page.tsx
│   │   ├── semantic/page.tsx
│   │   ├── ai-detect/page.tsx
│   │   ├── web-scan/page.tsx
│   │   ├── license/page.tsx
│   │   └── cross-batch/page.tsx
│   └── register/
│       └── page.tsx
└── public/
    ├── file.svg
    ├── globe.svg
    ├── next.svg
    ├── vercel.svg
    └── window.svg
```

## Database Schema

```sql
CREATE TABLE reference_batch (
        id uuid primary key default gen_random_uuid(),
        name text,
        created_at timestamptz default now()
);

CREATE TABLE reference_text (
        id uuid primary key default gen_random_uuid(),
        batch_id uuid references reference_batch(id) on delete cascade,
        raw_text text not null,
        cleaned_text text not null,
        sha256 text not null,
        source text,
        license text,
        created_at timestamptz default now(),
        source_file text,
        row_number integer,
        column_name text,
        cell_ref text
);

CREATE TABLE reference_embedding (
        ref_id uuid primary key references reference_text(id) on delete cascade,
        embedding vector(384)
);

CREATE TABLE pipeline_result (
        id uuid primary key default gen_random_uuid(),
        created_at timestamptz default now(),
        status text not null default 'pending',
        methods_used jsonb,
        source_files text[],
        total_entries integer default 0,
        flagged_count integer default 0,
        summary jsonb,
        error_message text
);

CREATE TABLE duplicate_pair (
        id uuid primary key default gen_random_uuid(),
        pipeline_result_id uuid not null references pipeline_result(id) on delete cascade,
        created_at timestamptz default now(),
        original_file text not null,
        original_row integer not null,
        original_col text,
        original_cell_ref text,
        original_text text not null,
        duplicate_file text not null,
        duplicate_row integer not null,
        duplicate_col text,
        duplicate_cell_ref text,
        duplicate_text text not null,
        detection_type text not null,
        method text not null,
        similarity_pct float not null
);

CREATE TABLE web_ai_result (
        id uuid primary key default gen_random_uuid(),
        pipeline_result_id uuid not null references pipeline_result(id) on delete cascade,
        created_at timestamptz default now(),
        source_file text not null,
        row_number integer not null,
        column_name text,
        cell_ref text,
        original_text text not null,
        is_plagiarised boolean default false,
        source_url text,
        ai_detected_pct float default 0.0
);
```

## Data Flow

### Register Flow (Excel/CSV/TXT to reference_text)
1. Upload file(s) to `POST /api/v1/ingest/reference/register`.
2. `preprocessor.read_all_text_from_file()` reads all sheets (Excel) or CSV/TXT:
   - Skips index-like columns (S.No, ID, etc.) and mostly numeric/empty columns.
   - Emits one entry per non-empty cell with `source_file`, `row_number`, `column_name`, and `cell_ref`.
3. Each entry is normalized via `preprocess_text()` and hashed (SHA-256).
4. Rows are inserted into `reference_text` with full position metadata.
5. Optional: SBERT embeddings are generated and stored in `reference_embedding`.

### Pipeline Run Flow (files to results)
1. Upload file(s) to `POST /api/v1/pipeline/run` and pick a `target_column` (or leave as `"auto"`).
2. Optionally call `POST /api/v1/pipeline/columns` first to see what columns are available.
3. Pipeline reads and normalizes entries from the target column.
4. Exact/fuzzy/semantic/AI/web/license methods run in-memory; cross-compare runs only for `.xlsx` files (and `.xlsx` inside ZIPs).
5. API returns a `PipelineRunResult` JSON payload (results are not stored in the database).

### Server-side Pipeline Flow (registered batches only)
1. Call `POST /api/v1/pipeline/run-on-server` with batch IDs and selected methods.
2. All texts from the batches are loaded and cross-checked against each other.
3. API returns a `PipelineResult` JSON payload.

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

### Ingest — /api/v1/ingest
| Method | Path | Description |
|---|---|---|
| POST | /input/data | Preview file contents (original + cleaned); CSV/XLSX/XLS/TXT |
| POST | /preprocess | Clean and preview text; optional CSV/Excel download; CSV/XLSX/XLS/TXT |
| POST | /reference/register | Register files as reference batches with cell positions; CSV/XLSX/XLS/TXT |

### Pipeline — /api/v1/pipeline
| Method | Path | Description |
|---|---|---|
| POST | /columns | Discover available column names from uploaded files (call before `/run` to pick `target_column`); auto-suggests `Query` column if found |
| POST | /run | Unified detection run across selected methods; accepts `target_column` (or `"auto"`), `methods` JSON, `color_report` flag, and optional inline Excel download |
| POST | /run-on-server | Run pipeline on stored batches only |

### Batches — /api/v1/batches
| Method | Path | Description |
|---|---|---|
| GET | / | List all batches with entry counts |
| DELETE | /{batch_id} | Delete a batch and all related data |
| PATCH | /{batch_id} | Rename a batch |

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

### PipelineResult (top-level)
```json
{
        "pipeline_id": "a1b2c3d4-...",
        "status": "completed",
        "summary": {
                "total_entries": 3,
                "flagged": 1,
                "risk_breakdown": {"high": 0, "medium": 1, "low": 0, "none": 2}
        },
        "results": [
                {
                        "entry_id": 1,
                        "original_text": "...",
                        "overall_risk": "medium",
                        "methods": {
                                "exact": {"is_duplicate": false, "matched_text": null, "batch": null},
                                "fuzzy": {"is_duplicate": true, "scores": {"levenshtein": 0.91, "jaccard": 0.78, "ngram": 0.86}, "matched_text": "..."},
                                "semantic": {"is_duplicate": false, "similarity": null, "matched_text": null},
                                "ai_detection": {"is_ai_generated": false, "confidence": 0.11, "label": "Human"},
                                "web_scan": {"found_online": false, "sources": [], "error": null},
                                "license_check": {"has_license": false, "licenses": [], "risk_level": "none"}
                        }
                }
        ]
}
```

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
- Only `.xlsx` files are processed (CSV/TXT are ignored).
- Row 1 (header) is **never** deleted.
- Single file → returns `.xlsx`; multiple files → returns `.zip`.

## Configuration

### Backend — `backend/.env`

```env
# Database
DATABASE_URL=postgresql://user:password@host:port/dbname
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=your-anon-key
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key

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

### Database (Supabase)
1. Create a project at https://supabase.com.
2. Enable pgvector: `CREATE EXTENSION IF NOT EXISTS vector;`
3. Run the schema in the Database Schema section.
4. Set `DATABASE_URL` in backend/.env.

## Key Design Decisions

| Decision | Reason |
|---|---|
| FastAPI over Flask/Django | Async-first APIs for concurrent web scanning and batch inference |
| PostgreSQL + pgvector | Single store for structured data and embeddings |
| SBERT all-MiniLM-L6-v2 | Balanced performance for sentence-level similarity |
| GPT-2 AI detector | High-accuracy AI detection with swap via env var |
| DuckDuckGo web scan | No API key required; controlled retries and timeout |
| Per-cell provenance | Enables exact row/column traceability in reports |
| Startup model cache | Single-load model initialization via lifespan |
