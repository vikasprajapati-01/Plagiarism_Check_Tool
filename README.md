# Plagiarism & Duplicate Detection Tool

**Samsung PRISM Research Project**

This project provides a unified plagiarism and duplicate detection pipeline for Excel/CSV/TXT datasets. It ingests files, normalizes content, stores per-cell provenance in PostgreSQL (Supabase + pgvector), and runs exact, fuzzy, semantic, AI detection, web scanning, and license checks to generate structured results and multi-sheet reports.

## Table of Contents

1. [Problem Statement](#problem-statement)
2. [System Overview](#system-overview)
3. [Tech Stack](#tech-stack)
4. [Repository Structure](#repository-structure)
5. [Database Schema](#database-schema)
6. [Data Flow](#data-flow)
7. [Detection Methods](#detection-methods)
8. [API Reference](#api-reference)
9. [Pipeline Output Format](#pipeline-output-format)
10. [Combined Report Format](#combined-report-format)
11. [Configuration](#configuration)
12. [How to Run Locally](#how-to-run-locally)
13. [Key Design Decisions](#key-design-decisions)

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
| Frontend | Next.js (TypeScript) | Upload UI, per-method analysis pages (refactor pending) |
| Database | PostgreSQL + pgvector (Supabase) | Batches, per-cell data, embeddings, pipeline results |

## Tech Stack

### Backend
| Library | Purpose |
|---|---|
| FastAPI | REST API framework (async) |
| PostgreSQL + pgvector | Relational data + vector embeddings |
| asyncpg / psycopg2 | Async and sync Postgres drivers |
| pandas | Excel/CSV ingestion and cleaning |
| sentence-transformers | SBERT semantic similarity (all-MiniLM-L6-v2) |
| transformers | AI-generated content detection (RoBERTa) |
| openpyxl | Excel report export |
| python-dotenv | Environment management |
| ddgs / BeautifulSoup4 | Web search + page text extraction |
| scikit-learn | Used internally by some detection services |

### Frontend
| Library | Purpose |  
|---|---|
| Next.js 14 (App Router) | React framework |
| TypeScript | Type-safe frontend code |
| Tailwind CSS | Styling |

## Repository Structure

```
backend/
├── .env
├── .env.example
├── requirements.txt
└── app/
        ├── main.py                      # FastAPI entry, lifespan model loading
        ├── core/
        │   ├── config.py                # pydantic-settings, all env vars
        │   ├── models.py                # shared Pydantic schemas
        │   └── model_cache.py           # SBERT + RoBERTa loaded once
        ├── api/
        │   └── v1/
        │       ├── router.py            # includes all sub-routers
        │       ├── batches.py           # list/delete/rename batches
        │       ├── ingest.py            # file upload, preprocessing, registration
        │       ├── pipeline.py          # POST /pipeline/run
        │       └── reports.py           # combined report download
        ├── services/
        │   ├── preprocessor.py          # reads Excel/CSV/TXT with cell positions
        │   ├── exact_match.py           # SHA-256 exact duplicate detection
        │   ├── fuzzy_match.py           # Levenshtein, Jaccard, N-gram, Hamming
        │   ├── semantic_match.py        # SBERT cosine similarity
        │   ├── ai_detector.py           # RoBERTa AI content detection
        │   ├── web_scanner.py           # DuckDuckGo + BeautifulSoup web scan
        │   ├── license_detector.py      # SPDX + copyright detection
        │   └── pipeline_runner.py       # orchestrates pipeline execution
        └── storage/
                └── repository.py            # all DB queries via asyncpg pool

frontend/app/
├── layout.tsx
├── page.tsx
├── components/
│   ├── Navbar.tsx
│   ├── Hero.tsx
│   ├── About.tsx
│   ├── Footer.tsx
│   └── DetectionSelector.tsx
└── analyze/
        ├── exact/page.tsx
        ├── fuzzy/page.tsx
        ├── semantic/page.tsx
        ├── ai-detect/page.tsx
        ├── web-scan/page.tsx
        ├── license/page.tsx
        └── cross-batch/page.tsx
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
2. `preprocessor.read_all_text_from_file()` reads the first sheet (Excel) or CSV/TXT and:
   - Skips index-like columns (S.No, ID, etc.) and mostly numeric/empty columns.
   - Emits one entry per non-empty cell with `source_file`, `row_number`, `column_name`, and `cell_ref`.
3. Each entry is normalized via `preprocess_text()` and hashed (SHA-256).
4. Rows are inserted into `reference_text` with full position metadata.
5. Optional: SBERT embeddings are generated and stored in `reference_embedding`.

### Pipeline Run Flow (files to results)
1. Upload file(s) to `POST /api/v1/pipeline/run` and choose methods.
2. Pipeline reads and normalizes entries with position metadata.
3. Exact/fuzzy/semantic duplication is computed and stored as `duplicate_pair` rows.
4. Web scan + AI detection output is stored in `web_ai_result` rows.
5. `pipeline_result` tracks run metadata, counts, and status.

## Detection Methods

| Method | Algorithm | Thresholds | File |
|---|---|---|---|
| Exact Match | SHA-256 hash comparison | 100% identical | services/exact_match.py |
| Fuzzy Match | Levenshtein, Jaccard, N-gram, Hamming | 0.85 / 0.70 / 0.75 / equal length | services/fuzzy_match.py |
| Semantic Match | SBERT cosine similarity | 0.85 | services/semantic_match.py |
| AI Detection | RoBERTa classifier | Returns confidence 0.0–100.0 | services/ai_detector.py |
| Web Scanner | DuckDuckGo + BeautifulSoup + windowed similarity | 10s timeout, 3 retries | services/web_scanner.py |
| License Detector | SPDX + copyright patterns | N/A | services/license_detector.py |
| Pipeline Runner | Orchestrates selected methods | N/A | services/pipeline_runner.py |

## API Reference

Base URL: http://localhost:8000
Docs: http://localhost:8000/docs

### Ingest — /api/v1/ingest
| Method | Path | Description |
|---|---|---|
| POST | /input/data | Preview file contents (original + cleaned) |
| POST | /preprocess | Clean and preview text; optional CSV/Excel download |
| POST | /reference/register | Register files as reference batches with cell positions |

### Pipeline — /api/v1/pipeline
| Method | Path | Description |
|---|---|---|
| POST | /run | Unified detection run across selected methods |

### Batches — /api/v1/batches
| Method | Path | Description |
|---|---|---|
| GET | / | List all batches with entry counts |
| DELETE | /{batch_id} | Delete a batch and all related data |
| PATCH | /{batch_id} | Rename a batch |

### Reports — /api/v1/reports
| Method | Path | Description |
|---|---|---|
| POST | /combined | Generate multi-sheet Excel report |

## Pipeline Output Format

### Duplicate Pair (exact/fuzzy/semantic)
```json
{
        "original_file": "Dataset1.xlsx",
        "original_row": 2,
        "original_col": "Query",
        "original_cell_ref": "B2",
        "original_text": "...",
        "duplicate_file": "Dataset1.xlsx",
        "duplicate_row": 10,
        "duplicate_col": "Query",
        "duplicate_cell_ref": "B10",
        "duplicate_text": "...",
        "detection_type": "Exact",
        "method": "exact",
        "similarity_pct": 100.0
}
```

### Web + AI Result
```json
{
        "source_file": "Dataset1.xlsx",
        "row_number": 2,
        "column_name": "Query",
        "cell_ref": "B2",
        "original_text": "...",
        "is_plagiarised": true,
        "source_url": "https://...",
        "ai_detected_pct": 0.0
}
```

## Combined Report Format

The combined Excel report includes three sheets:
1. Row-to-Row Duplicates: Original, Duplicate, Type, Similarity (%).
2. Cell-to-Cell Duplicates: Original, Duplicate, Type, Similarity (%).
3. Web + AI Detection: Original, Plagiarised, Source, AI Detected (%).

## Configuration

Copy backend/.env.example to backend/.env and set:

```env
DATABASE_URL=postgresql://user:password@host:port/dbname
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=your-anon-key
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key
EMBEDDING_MODEL=all-MiniLM-L6-v2
AI_DETECTION_MODEL=openai-community/roberta-large-openai-detector
FUZZY_THRESHOLD=0.85
SEMANTIC_THRESHOLD=0.85
WEB_SCAN_TIMEOUT=10
WEB_SCAN_RETRIES=3
LOG_LEVEL=INFO
```

## How to Run Locally

### Backend
```bash
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp .env.example .env
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
| RoBERTa AI detector | High-accuracy AI detection with swap via env var |
| DuckDuckGo web scan | No API key required; controlled retries and timeout |
| Per-cell provenance | Enables exact row/column traceability in reports |
| Startup model cache | Single-load model initialization via lifespan |
