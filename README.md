# Plagiarism and Duplicate Detection Tool (Samsung PRISM)

## Problem Statement

This tool is built to validate AI training datasets stored as Excel (`.xlsx`, `.xls`) and CSV files. It ensures the high quality of training data by detecting and filtering out exact duplicates, near-duplicates, semantically similar content, AI-generated text, web-plagiarised content, and license/copyright violations. It provides a detailed, multi-sheet Excel risk report and can generate a cleaned version of the original dataset with flagged rows safely removed.

## System Overview

| Component | Technology | Role |
| --- | --- | --- |
| **Backend API** | FastAPI (Python) | Orchestrates the detection pipeline, processes files, and generates reports. |
| **Frontend UI** | Next.js (React) | Provides the interface for file uploads, selecting detection modes, and viewing results. |
| **AI / NLP Models** | PyTorch, Hugging Face | Powers semantic similarity embeddings and AI-content perplexity detection. |

## Tech Stack

### Backend
| Library | Purpose |
| --- | --- |
| `fastapi`, `uvicorn`, `starlette` | API framework and ASGI server |
| `pydantic`, `pydantic-settings` | Data validation and configuration management |
| `pandas`, `openpyxl` | CSV and Excel file parsing and report generation |
| `torch`, `transformers` | Deep learning framework and GPT-2 models for AI detection |
| `sentence-transformers` | Embeddings generation for semantic matching |
| `RapidFuzz`, `Levenshtein` | String distance algorithms for fuzzy/near-duplicate matching |
| `beautifulsoup4`, `ddgs` | Web scraping and DuckDuckGo search for web plagiarism detection |

### Frontend
| Library | Version | Purpose |
| --- | --- | --- |
| `next` | `16.2.1` | React framework for UI rendering |
| `react`, `react-dom` | `19.2.4` | Component-based UI library |
| `tailwindcss` | `^4` | Utility-first CSS framework |
| `xlsx` | `^0.18.5` | Client-side Excel parsing for report preview |

## Repository Structure

```text
backend/
├── .env
├── .gitignore
├── requirements.txt
├── scripts/
│   ├── download_models.py
│   ├── generate_test_data.py
│   ├── api_report.xlsx
│   └── api_response.json
├── tests/
│   └── test_cross_compare.py
└── app/
    ├── main.py
    ├── core/
    │   ├── config.py
    │   ├── models.py
    │   └── model_cache.py
    ├── api/v1/
    │   ├── router.py
    │   ├── pipeline.py
    │   ├── compare.py
    │   └── reports.py
    └── services/
        ├── preprocessor.py
        ├── cross_compare.py
        ├── pipeline_runner.py
        ├── ai_detector.py
        ├── web_scanner.py
        ├── exact_match.py
        ├── fuzzy_match.py
        ├── semantic_match.py
        └── license_detector.py

frontend/
├── package.json
└── app/
    ├── layout.tsx
    ├── page.tsx
    ├── components/
    │   ├── AboutSection.tsx
    │   ├── DetectionSelector.tsx
    │   ├── Footer.tsx
    │   ├── HeroSection.tsx
    │   ├── Navbar.tsx
    │   ├── PreviewPanel.tsx
    │   └── ThemeProvider.tsx
    └── analyze/
        ├── page.tsx
        ├── AnalyzerLayout.tsx
        ├── ai-detect/page.tsx
        ├── exact/page.tsx
        ├── folder/page.tsx
        ├── fuzzy/page.tsx
        ├── license/page.tsx
        ├── semantic/page.tsx
        └── web-scan/page.tsx
```

## Detection Methods

| Method | Algorithm | Threshold | File |
| --- | --- | --- | --- |
| **Exact Match** | SHA-256 Hashing | 100% | `exact_match.py` |
| **Fuzzy Match** | Levenshtein, Jaccard, N-gram | 0.85 | `fuzzy_match.py` |
| **Semantic Match** | SentenceTransformers (Cosine Sim) | 0.85 | `semantic_match.py` |
| **AI Detection** | GPT-2 Perplexity Scoring | >= 50.0% AI | `ai_detector.py` |
| **Web Scan** | DDG Search + Windowed Levenshtein | 0.5 | `web_scanner.py` |
| **License Check** | SPDX Keyword + Signature Similarity | 0.3 | `license_detector.py` |
| **Cross Compare** | Row/Cell Cross-Workbook Levenshtein | 75.0% | `cross_compare.py` |

## Detection Modes

The pipeline orchestrator supports two primary processing modes (`detection_mode` parameter):

1. **Row-wise Mode**:
   - **Input**: User uploads one or multiple Excel/CSV workbooks. The tool automatically attempts to isolate a target column (e.g., `"Query"`) via the `target_column` parameter, or operates globally on all cells.
   - **Comparison**: Compares each row against all others across all uploaded workbooks to find structural duplicates. Additionally, runs all NLP/AI detections sequentially on target texts.
   - **Output**: Returns global duplicate pairs across files, along with web, AI, and license violations.

2. **Column-wise Mode**:
   - **Input**: User uploads exactly one file and specifies two distinct column names (`col1_name` and `col2_name`).
   - **Comparison**: Performs cross-comparison exclusively between the two selected columns within the same row. NLP/AI scanning is only performed on rows that are flagged as duplicates during this internal cross-compare step.
   - **Output**: Returns structural matches constrained to the two specific columns, saving immense computational time by bypassing AI scans for non-matching rows.

## API Reference

### Pipeline Router (`/api/v1/pipeline`)
| Method | Path | Description |
| --- | --- | --- |
| `POST` | `/columns` | Discovers available column headers from an uploaded Excel/CSV file to assist with column-wise targeting selection. |
| `POST` | `/run` | Main execution endpoint. Runs the full unified detection pipeline across all enabled methods on the uploaded datasets. |

### Compare Router (`/api/v1/compare`)
| Method | Path | Description |
| --- | --- | --- |
| `POST` | `/cross` | Performs isolated cross-workbook structural duplicate detection (row and cell level) and returns JSON results. |
| `POST` | `/report` | Runs isolated cross-comparison and directly returns a downloadable `.xlsx` report. |
| `POST` | `/colored` | Returns a copy of the input workbook with exact and near-duplicate rows/cells structurally highlighted with background colors. |

### Reports Router (`/api/v1/reports`)
| Method | Path | Description |
| --- | --- | --- |
| `POST` | `/cleaned` | Generates a cleaned Excel output with structurally duplicate and plagiarised rows removed based on prior JSON match lists. |
| `POST` | `/combined` | Generates a comprehensive multi-sheet Excel risk dashboard report from raw pipeline JSON results. |

## Pipeline Output Format

### JSON Response (`PipelineRunResult`)

```json
{
  "pipeline_id": "uuid-string",
  "status": "completed",
  "summary": {
    "total_files": 1,
    "total_rows": 100,
    "total_row_duplicates": 5,
    "total_cell_duplicates": 10,
    "exact_row_matches": 2,
    "near_row_matches": 3,
    "exact_cell_matches": 4,
    "near_cell_matches": 6,
    "plagiarised_entries": 12,
    "ai_detected_entries": 8,
    "web_ai_total_entries": 100,
    "web_ai_returned_entries": 12
  },
  "row_duplicates": [
    {
      "original": "Original row content",
      "duplicate": "Duplicate row content",
      "type": "Exact",
      "similarity_pct": 100.0
    }
  ],
  "cell_duplicates": [...],
  "web_ai_results": [
    {
      "original": "Original text",
      "plagiarised": "Matched plagiarised snippet",
      "source": "https://example.com/source",
      "ai_detected_pct": 85.5
    }
  ]
}
```

## Report Sheets

The combined Excel report generated by `/api/v1/reports/combined` contains four distinct sheets:

1. **Row-to-Row**
   - **Columns:** `Original`, `Duplicate`, `Type`, `Similarity (%)`
   - **Data:** Highlights entire rows matched as exact or near duplicates across the dataset.

2. **Cell-to-Cell**
   - **Columns:** `Original`, `Duplicate`, `Type`, `Similarity (%)`
   - **Data:** Highlights specific cell contents matched as duplicates, bypassing overly short strings.

3. **AI-Plagiarism**
   - **Columns:** `Original`, `Plagiarised`, `Source`, `AI Detected (%)`
   - **Data:** Details web plagiarism hits (with source URLs) alongside AI-generated probability percentages.

4. **Risk Summary**
   - **Data:** A master dashboard displaying:
     - Flagged counts and rates broken down strictly by method (Exact, Near, Semantic, AI, Web, License).
     - Overall Dataset Summary.
     - Plagiarism Risk Score (PRS) calculated via a weighted average: (Exact 40%, Near 20%, Semantic 15%, AI 10%, Web 10%, License 5%).
     - Dataset Quality Assessment labeling the dataset objectively as Low, Medium, High, or Critical Risk.

## Configuration

The environment variables configured in `backend/app/core/config.py`:

| Setting | Default Value | Description |
| --- | --- | --- |
| `EMBEDDING_MODEL` | `"all-MiniLM-L6-v2"` | SBERT model used for generating semantic embeddings. |
| `GPT2_MODEL` | `"gpt2"` | Language model used for perplexity-based AI detection. |
| `FUZZY_THRESHOLD` | `0.85` | Default similarity threshold for near-duplicate string matches. |
| `SEMANTIC_THRESHOLD` | `0.85` | Default cosine similarity threshold for semantic matches. |
| `WEB_SCAN_TIMEOUT` | `10` | Request timeout (seconds) for fetching webpage content. |
| `WEB_SCAN_RETRIES` | `1` | Retry limit for DuckDuckGo search queries. |
| `WEB_SCAN_MAX_QUERIES` | `1` | Max search queries extracted per entry for web scanning. |
| `WEB_SCAN_MAX_RESULTS` | `2` | Max search results to evaluate per query. |
| `WEB_SCAN_MAX_SCAN_TIME`| `25` | Maximum allowed time (seconds) to scan a single entry. |
| `WEB_SCAN_OVERALL_TIMEOUT`| `60`| Hard timeout (seconds) for the entire web/AI/license phase. |
| `LOG_LEVEL` | `"INFO"` | Python logging level. |

## How to Run Locally

### Backend Setup
1. Navigate to the `backend/` directory.
2. Create and activate a Python virtual environment.
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Download the ML models for offline usage (optional but recommended to avoid startup delays or SSL errors):
   ```bash
   python scripts/download_models.py
   ```
5. Start the backend server:
   ```bash
   uvicorn app.main:app --host 0.0.0.0 --port 8000
   ```
*Note: The backend operates entirely in-memory and via local files; no database connection is required or established.*

### Frontend Setup
1. Navigate to the `frontend/` directory.
2. Install dependencies:
   ```bash
   npm install
   ```
3. Start the Next.js development server:
   ```bash
   npm run dev
   ```

## Model Loading

The backend employs an **Offline-First Checkpoint Fallback Strategy** (`backend/app/core/model_cache.py`) to ensure robustness:

1. **Online Attempt**: At startup, it attempts to download `all-MiniLM-L6-v2` and `gpt2` directly from HuggingFace.
2. **Offline Fallback**: If the download fails (e.g., due to SSL or network errors), it automatically checks the local `backend/checkpoints/sbert` and `backend/checkpoints/gpt2` directories for pre-downloaded weights.
3. **Graceful Degradation**: If models are missing completely from both online sources and local checkpoints, the backend continues to start without crashing. Features relying on the missing models (semantic matching or AI detection) are safely disabled, and clear warnings are emitted in the console logs and exposed on the health (`/`) endpoint.

## Key Design Decisions

| Decision | Reason |
| --- | --- |
| **Stateless Architecture** | By eschewing a database layer entirely, the tool maintains zero external state, ensuring high portability and significantly reducing setup friction for researchers evaluating datasets. |
| **Concurrent Pipeline Execution** | CPU-bound NLP processing and I/O-bound web scanning run concurrently inside the pipeline orchestrator, bounded by semaphores and timeouts to prevent hanging on external requests. |
| **Pydantic Validation** | Enforces strict schema rules on JSON inputs and internal data flow, ensuring that Excel report generation receives predictable data shapes without hidden errors. |
| **Graceful ML Model Degradation** | Prevents the entire service from locking up if external AI model repositories are unreachable, ensuring basic structural duplicate detection remains fully functional offline. |
| **Column-Targeted Analysis** | Allows massive performance gains when evaluating known datasets by restricting O(n^2) cross-comparison algorithms solely to meaningful text columns, reducing redundant operations. |
