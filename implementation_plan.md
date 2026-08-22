# Phase 0 — Prove the Pipeline: ExamPaper Refine

Turn uploaded exam papers (PDFs, scans, phone photos) into clean, AI-rewritten, beautifully typeset PDF documents. This phase validates the core pipeline before building the full product.

## User Review Required

> [!IMPORTANT]
> **Core concept clarification**: Based on our discussion, the key differentiator of this project is that the AI **rewrites** the exam paper into a clean typeset document — not just OCR + cleanup. The pipeline detects the document type and chooses the best output format (LaTeX for math-heavy, HTML/CSS for general), then always renders to a final PDF. This is more ambitious than the original note's "cleaned derivative" — please confirm this is the direction.

> [!WARNING]
> **Cost at scale**: Gemini API calls for full document rewriting will cost more than simple OCR extraction. For Phase 0 benchmarking, this is fine. For production, we should measure cost-per-paper and consider caching/batching strategies. On your old-PC VPS, the API calls will still cost money even if hosting is free.

## Open Questions

> [!IMPORTANT]
> 1. **LaTeX compilation**: To generate PDFs from LaTeX, we need a TeX distribution (e.g., TeX Live ~4GB). For Phase 0, should we install it locally, or use a lightweight alternative like `tectonic` (~50MB)?
> 2. **Sample papers**: Can you drop 5–10 sample exam papers into `f:\call\test_papers\`? A mix of digital PDFs, scans, and phone photos would be ideal. Math-heavy and text-only papers both.
> 3. **Gemini API key**: We'll store it in a `.env` file. Is your key for `generativelanguage.googleapis.com` (AI Studio) or Vertex AI?

## Proposed Changes

### Project Structure

The Phase 0 project will live in `f:\call\` with this layout:

```
f:\call\
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py              # FastAPI app entry point
│   │   ├── config.py            # Settings (env vars, paths)
│   │   ├── models.py            # SQLAlchemy + Pydantic models
│   │   ├── database.py          # SQLite setup
│   │   └── routers/
│   │       ├── __init__.py
│   │       ├── upload.py         # Upload endpoints
│   │       ├── papers.py         # Browse/search endpoints
│   │       └── process.py        # Processing status endpoints
│   ├── pipeline/
│   │   ├── __init__.py
│   │   ├── orchestrator.py       # Pipeline coordinator
│   │   ├── preprocessor.py       # Image cleanup (OpenCV)
│   │   ├── extractor.py          # Text extraction (PyMuPDF + OCR)
│   │   ├── analyzer.py           # Gemini: structure + metadata extraction
│   │   ├── rewriter.py           # Gemini: rewrite into typeset format
│   │   ├── renderer.py           # LaTeX/HTML → PDF conversion
│   │   └── schemas.py            # Versioned JSON schemas for pipeline output
│   ├── storage/
│   │   ├── __init__.py
│   │   └── local.py              # Local filesystem storage (S3-compatible interface)
│   ├── requirements.txt
│   ├── .env.example
│   └── README.md
├── test_papers/                   # Sample papers for benchmarking
├── data/                          # Runtime data (SQLite DB, stored files)
│   ├── originals/                 # Immutable uploaded files
│   ├── derivatives/               # Cleaned/rewritten outputs
│   └── exampaper.db               # SQLite database
├── benchmarks/                    # Phase 0 benchmark results
│   └── results.md
├── LICENSE                        # MIT License
└── README.md                      # Project overview
```

---

### Component 1: Core Data Models

#### [NEW] [models.py](file:///f:/call/backend/app/models.py)

SQLAlchemy models + Pydantic schemas for:

- **ExamPaper**: `id`, `title`, `source_sha256`, `original_file_path`, `university`, `course_code`, `course_name`, `year`, `semester`, `exam_type`, `language`, `status` (uploaded → processing → needs_review → published → failed), `upload_time`, `quality_score`, `extraction_confidence`
- **PaperDerivative**: `id`, `exam_paper_id`, `version`, `file_path`, `derivative_type` (cleaned_scan | rewritten_latex | rewritten_html | final_pdf), `pipeline_version`, `ocr_engine`, `model_version`, `created_at`
- **Question**: `id`, `exam_paper_id`, `parent_question_id`, `display_number`, `normalized_order`, `text`, `marks`, `page_start`, `page_end`, `extraction_confidence`, `topics`
- **ProcessingLog**: `id`, `exam_paper_id`, `stage`, `status`, `started_at`, `completed_at`, `error_details`, `metrics` (JSON)

#### [NEW] [database.py](file:///f:/call/backend/app/database.py)

SQLite async setup with `aiosqlite`. Designed so switching to PostgreSQL later only requires changing the connection string.

#### [NEW] [schemas.py](file:///f:/call/backend/pipeline/schemas.py)

Versioned Pydantic models for pipeline stage outputs:
- `ExtractionResult`: raw OCR text, per-page confidence, embedded text vs OCR breakdown
- `StructureResult`: parsed questions, marks, metadata, document type classification
- `RewriteResult`: generated LaTeX/HTML/Markdown content, format chosen, render instructions

---

### Component 2: Processing Pipeline

This is the heart of Phase 0. Each stage is independent and idempotent.

#### [NEW] [preprocessor.py](file:///f:/call/backend/pipeline/preprocessor.py)

**Input**: Uploaded file (PDF or image)
**Output**: Normalized page images ready for OCR

- Detect file type (PDF vs image)
- For PDFs: extract pages using PyMuPDF, check for embedded text
- For images: validate, normalize orientation (EXIF)
- Apply OpenCV preprocessing: deskew, denoise, contrast correction, adaptive thresholding
- Generate SHA-256 fingerprint of original
- Output: list of page images + embedded text (if any)

#### [NEW] [extractor.py](file:///f:/call/backend/pipeline/extractor.py)

**Input**: Preprocessed page images
**Output**: Raw text with per-page confidence scores

- Per-page strategy:
  - If embedded text exists and is high quality → use it (PyMuPDF)
  - Otherwise → OCR with Tesseract (baseline)
- Record: which method was used per page, confidence score, processing time
- For Phase 0 benchmarking: optionally run both methods and compare

#### [NEW] [analyzer.py](file:///f:/call/backend/pipeline/analyzer.py)

**Input**: Extracted text + page images
**Output**: Structured document data (questions, metadata, document type)

- Call Gemini 2.0 Flash Lite with:
  - The extracted text
  - Page images (for low-confidence pages or complex layouts)
  - A structured output schema (Pydantic model → JSON Schema)
- Extract:
  - Document type classification (math-heavy, text-only, mixed, diagram-heavy)
  - Questions with sub-questions, marks, page references
  - Metadata: university, course, year, semester, exam type, language
  - Topics/tags per question
- Validate: numbering consistency, mark totals, page references

#### [NEW] [rewriter.py](file:///f:/call/backend/pipeline/rewriter.py)

**Input**: Structured document data + original text + page images
**Output**: Rewritten document in the best format

This is the **key differentiator** — the AI rewrites the exam paper:

- Based on document type classification:
  - **Math-heavy** → Generate LaTeX document
  - **Text-only** → Generate clean Markdown or HTML
  - **Mixed** → Generate LaTeX (better equation support)
  - **Diagram-heavy** → Generate HTML with placeholder notes for diagrams
- Prompt engineering:
  - Preserve exact question wording, numbering, and marks
  - Faithfully reproduce equations, tables, and formatting
  - Add proper document structure (headers, sections, page breaks)
  - Do NOT add, remove, or modify any exam content
- Output: source file (`.tex`, `.html`, or `.md`) + format metadata

#### [NEW] [renderer.py](file:///f:/call/backend/pipeline/renderer.py)

**Input**: Rewritten source file
**Output**: Final PDF

- LaTeX → PDF: using `tectonic` or `pdflatex`
- HTML → PDF: using `weasyprint` (Python library, no external deps)
- Markdown → HTML → PDF: via `markdown` + `weasyprint`
- Always produce a PDF as the final output

#### [NEW] [orchestrator.py](file:///f:/call/backend/pipeline/orchestrator.py)

Coordinates the full pipeline:

```
Upload → Preprocess → Extract → Analyze → Rewrite → Render → Store
```

- Runs stages sequentially for Phase 0 (async workers in Phase 1)
- Logs timing, errors, and confidence at each stage
- Stores intermediate outputs for debugging and benchmarking
- If any stage fails, marks the paper with error details and stops

---

### Component 3: Storage Layer

#### [NEW] [local.py](file:///f:/call/backend/storage/local.py)

Local filesystem storage with an interface that mirrors S3 operations:
- `store_original(file, sha256)` → saves to `data/originals/`
- `store_derivative(paper_id, version, type, file)` → saves to `data/derivatives/`
- `get_file(path)` → returns file for download
- Later: swap in MinIO or S3 by implementing the same interface

---

### Component 4: API Endpoints

#### [NEW] [main.py](file:///f:/call/backend/app/main.py)

FastAPI app with CORS, startup/shutdown, and router registration.

#### [NEW] [upload.py](file:///f:/call/backend/app/routers/upload.py)

- `POST /api/upload` — Upload a PDF or image file
  - Validates file type (PDF, PNG, JPG, JPEG, TIFF)
  - Computes SHA-256, checks for duplicates
  - Stores original, creates DB record
  - Kicks off processing pipeline (synchronous for Phase 0)
  - Returns paper ID and status

#### [NEW] [papers.py](file:///f:/call/backend/app/routers/papers.py)

- `GET /api/papers` — List all papers with filtering (university, course, year, status)
- `GET /api/papers/{id}` — Get paper details (metadata, questions, processing history)
- `GET /api/papers/{id}/download/original` — Download original file
- `GET /api/papers/{id}/download/refined` — Download the rewritten PDF

#### [NEW] [process.py](file:///f:/call/backend/app/routers/process.py)

- `GET /api/papers/{id}/status` — Processing status and stage details
- `POST /api/papers/{id}/reprocess` — Trigger reprocessing (idempotent)

---

### Component 5: Configuration & Setup

#### [NEW] [config.py](file:///f:/call/backend/app/config.py)

Pydantic Settings class reading from `.env`:
- `GEMINI_API_KEY`
- `GEMINI_MODEL` (default: `gemini-2.0-flash-lite`)
- `DATA_DIR` (default: `../data`)
- `DATABASE_URL` (default: `sqlite+aiosqlite:///data/exampaper.db`)
- `MAX_FILE_SIZE_MB` (default: `50`)
- `ALLOWED_EXTENSIONS`

#### [NEW] [.env.example](file:///f:/call/backend/.env.example)

Template for environment variables.

#### [NEW] [requirements.txt](file:///f:/call/backend/requirements.txt)

```
fastapi>=0.110.0
uvicorn[standard]>=0.28.0
pydantic>=2.6.0
pydantic-settings>=2.1.0
sqlalchemy>=2.0.28
aiosqlite>=0.20.0
PyMuPDF>=1.24.0
google-genai>=1.0.0
python-multipart>=0.0.9
jinja2>=3.1.3
httpx>=0.27.0
opencv-python-headless>=4.9.0
Pillow>=10.2.0
pytesseract>=0.3.10
weasyprint>=61.0
python-dotenv>=1.0.0
```

---

### Component 6: Production-Friendly Open Source Setup

#### [NEW] [README.md](file:///f:/call/README.md)

Project overview covering:
- What ExamPaper Refine does
- Quick start guide
- Architecture overview
- Contributing guidelines
- License (MIT)

#### [NEW] [LICENSE](file:///f:/call/LICENSE)

MIT License.

---

## Production Cost Strategy (for your old PC VPS)

For zero/minimal cost self-hosting:

| Service | Phase 0 (Dev) | Production (Free/Cheap) |
|---|---|---|
| **Database** | SQLite | PostgreSQL (free, self-hosted) |
| **File Storage** | Local filesystem | Local filesystem or MinIO (free, self-hosted) |
| **Search** | SQLite FTS | Meilisearch (free, self-hosted) |
| **Task Queue** | Synchronous | Celery + Redis (free, self-hosted) |
| **LLM** | Gemini API (pay per use) | Gemini API (only cost) |
| **PDF Rendering** | tectonic + weasyprint | Same (free) |
| **Web Server** | uvicorn | Caddy or nginx (free) |
| **Hosting** | Local | Your old PC as VPS (free) |

> [!TIP]
> The **only recurring cost** will be Gemini API calls. Everything else runs on your hardware for free. Gemini Flash Lite is very cheap — roughly $0.01–0.03 per paper depending on length.

---

## Verification Plan

### Phase 0 Benchmarks

With your sample papers, we will measure and record:

1. **Preprocessing quality**: Visual comparison of original vs preprocessed pages
2. **OCR accuracy**: Character/word error rate (embedded text vs Tesseract)
3. **Structure extraction**: Question boundary accuracy (manual check against source)
4. **Metadata accuracy**: University, course, year correctly identified
5. **Rewrite fidelity**: Does the rewritten document faithfully preserve all content?
6. **Render quality**: Is the final PDF clean and readable?
7. **Pipeline timing**: How long does each stage take?
8. **Failure modes**: Which paper types fail, and why?

### Manual Verification

1. Upload 5–10 sample papers through the API
2. Compare original → rewritten PDF side by side
3. Check that no exam content was added, removed, or altered
4. Verify math equations are correctly typeset
5. Record results in `benchmarks/results.md`

---

## Future Phases

Now that Phase 0 (the core synchronous pipeline) is successfully proven and implemented, here is the roadmap for the next phases to build out the full platform:

### Phase 1: Robust Asynchronous Architecture

**Goal**: Make the pipeline non-blocking so users don't wait 60+ seconds on the upload endpoint. Support 5–20 concurrent uploads with parallel processing, automatic retries, rate limiting, and optional email notifications.

---

#### 1.1 Task Queue: Celery + Redis

Introduce Celery as the async task runner, backed by Redis as the message broker and result backend.

##### [NEW] `backend/worker.py`
Celery app configuration:
- Broker: `redis://localhost:6379/0`
- Result backend: `redis://localhost:6379/1`
- Task serializer: JSON
- Concurrency: 2–4 worker processes (adjustable via `--concurrency` flag)
- Task time limit: 300s (hard kill), soft limit: 240s (graceful)

##### [MODIFY] `backend/pipeline/orchestrator.py`
- Extract the current synchronous `process_paper()` function into a Celery task decorated with `@celery_app.task(bind=True, max_retries=3)`.
- Each pipeline stage (preprocess, extract, analyze, rewrite, render) updates the paper's `status` in the database as it progresses, enabling the frontend to poll for granular progress.
- Stage progression updates: `queued → preprocessing → extracting → analyzing → rewriting → rendering → completed` (or `failed`).

##### [MODIFY] `backend/app/routers/upload.py`
- Change `POST /api/upload` to be **non-blocking**: store the original file, create the DB record with `status=queued`, dispatch the Celery task, and immediately return the `paper_id` + `status=queued` (HTTP 202 Accepted).
- Response includes a polling URL: `/api/papers/{id}/status`.

##### [NEW] `backend/tasks/pipeline_task.py`
The Celery task that wraps the orchestrator:
```python
@celery_app.task(bind=True, max_retries=3, default_retry_delay=30)
def process_paper_task(self, paper_id: str):
    # Run the pipeline, update DB status at each stage
    # On failure: retry with exponential backoff
```

##### Infrastructure
- **Redis**: Install via `winget install Redis.Redis` (dev) or run via Docker in production.
- **Starting workers**: `celery -A worker worker --loglevel=info --concurrency=4`

---

#### 1.2 Database Migration: SQLite → PostgreSQL

Migrate from SQLite to PostgreSQL for proper concurrent write support across multiple Celery workers.

##### [MODIFY] `backend/app/database.py`
- Replace `sqlite+aiosqlite` connection string with `postgresql+asyncpg`.
- Add connection pool settings: `pool_size=10`, `max_overflow=20`.

##### [MODIFY] `backend/app/config.py`
- Update `DATABASE_URL` default to `postgresql+asyncpg://user:pass@localhost:5432/exampaper`.
- Add `REDIS_URL` setting (default: `redis://localhost:6379/0`).

##### [NEW] `backend/alembic/` (Migration Tool)
- Initialize Alembic for schema migrations: `alembic init alembic`.
- Create initial migration from existing SQLAlchemy models.
- This ensures all future schema changes are tracked and reproducible.

##### Data Migration Script
- One-time script to export existing SQLite data and import into PostgreSQL (if any test data needs preserving).

---

#### 1.3 Status Polling Endpoint

The frontend will poll for processing status every 3–5 seconds. Simple, reliable, no WebSocket complexity.

##### [MODIFY] `backend/app/routers/process.py`
Enhance `GET /api/papers/{id}/status` to return granular stage info:
```json
{
  "paper_id": "e10b1f44db20",
  "status": "analyzing",
  "current_stage": 4,
  "total_stages": 6,
  "stages": [
    {"name": "preprocess", "status": "completed", "duration_s": 1.6},
    {"name": "extract", "status": "completed", "duration_s": 36.9},
    {"name": "analyze", "status": "completed", "duration_s": 7.6},
    {"name": "rewrite", "status": "in_progress", "started_at": "..."},
    {"name": "render", "status": "pending"},
    {"name": "store", "status": "pending"}
  ],
  "download_url": null,
  "error": null
}
```

This gives the Phase 2 frontend everything it needs for a smooth progress bar with per-stage feedback.

---

#### 1.4 Retry Strategy: Exponential Backoff

Each pipeline stage gets 3 automatic retries with exponential backoff before marking as failed.

##### Retry Logic (in `pipeline_task.py`)
- **Retry delays**: 30s → 60s → 120s (exponential backoff).
- **Retryable errors**: Gemini API timeouts, rate limits (HTTP 429), transient network errors.
- **Non-retryable errors**: Invalid file format, corrupted image, schema validation failure.
- After 3 failed retries, the paper is marked `status=failed` with `error_details` stored in the `processing_logs` table.
- The existing `POST /api/papers/{id}/reprocess` endpoint remains available for manual retry.

##### [MODIFY] `backend/app/models.py`
- Add `retry_count` and `last_retry_at` fields to `ProcessingLog`.
- Add `failed_stage` field to `ExamPaper` so the UI knows which stage broke.

---

#### 1.5 Rate Limiting

Protect the public upload endpoint from abuse using IP-based rate limiting.

##### [NEW] `backend/app/middleware/rate_limit.py`
- Use `slowapi` (built on top of `limits` library, integrates natively with FastAPI).
- Limits:
  - `POST /api/upload`: **5 uploads per IP per hour** (adjustable via config).
  - `GET /api/papers/*`: **60 requests per IP per minute** (generous for polling).
  - `POST /api/papers/{id}/reprocess`: **10 per IP per hour**.
- Returns HTTP 429 with a clear message and `Retry-After` header.

##### [MODIFY] `backend/requirements.txt`
Add new dependencies:
```
celery>=5.4.0
redis>=5.0.0
asyncpg>=0.30.0
alembic>=1.13.0
slowapi>=0.1.9
aiosmtplib>=3.0.0
```

---

#### 1.6 Optional Email Notification

If a user provides an email address during upload, send them a notification when their paper is ready.

##### [MODIFY] `backend/app/routers/upload.py`
- Add optional `email` field to the upload form (not required).

##### [NEW] `backend/services/email_notifier.py`
- Lightweight async email sender using `aiosmtplib`.
- Sends a simple "Your paper is ready!" email with the download link.
- Configurable via `.env`: `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`, `SMTP_FROM`.
- If SMTP is not configured, email notifications are silently skipped (no errors).

##### [MODIFY] `backend/pipeline/orchestrator.py`
- At the end of successful processing, check if the paper has an associated email and trigger the notification.

---

#### 1.7 Project Structure After Phase 1

```
backend/
├── app/
│   ├── main.py
│   ├── config.py              # + REDIS_URL, DATABASE_URL (postgres), SMTP settings
│   ├── models.py              # + retry_count, failed_stage fields
│   ├── database.py            # PostgreSQL + asyncpg
│   ├── middleware/
│   │   └── rate_limit.py      # [NEW] slowapi rate limiting
│   └── routers/
│       ├── upload.py           # Non-blocking upload (HTTP 202)
│       ├── papers.py
│       └── process.py          # Enhanced status polling
├── pipeline/
│   ├── orchestrator.py         # Updated to use Celery tasks
│   ├── preprocessor.py
│   ├── extractor.py
│   ├── analyzer.py
│   ├── rewriter.py
│   ├── renderer.py
│   ├── figure_generator.py
│   └── schemas.py
├── tasks/
│   └── pipeline_task.py        # [NEW] Celery task definitions
├── services/
│   └── email_notifier.py       # [NEW] Optional email notifications
├── storage/
│   └── local.py
├── alembic/                    # [NEW] Database migrations
│   ├── env.py
│   └── versions/
├── worker.py                   # [NEW] Celery app entry point
└── requirements.txt            # Updated with new deps
```

---

#### Verification Plan for Phase 1

1. **Async Upload Test**: Upload a paper via `/api/upload` → confirm immediate HTTP 202 response → poll `/api/papers/{id}/status` → confirm stages progress → confirm `completed` status with download URL.
2. **Concurrency Test**: Upload 5 papers simultaneously → confirm all 5 are queued and processed in parallel by Celery workers.
3. **Retry Test**: Temporarily break the Gemini API key → upload a paper → confirm 3 retry attempts with exponential backoff → confirm `failed` status with error details.
4. **Rate Limit Test**: Send 6 rapid uploads from the same IP → confirm the 6th is rejected with HTTP 429.
5. **Email Test**: Upload with an email address → confirm notification email is sent on completion.
6. **PostgreSQL Test**: Confirm all existing API endpoints work correctly against PostgreSQL instead of SQLite.

### Phase 2: Frontend Web Application — "PaperFlow"

**Goal**: Build a content-first, digital-library / ebook-store experience for academic exam papers. Zero marketing fluff, frictionless 1-click downloads, clean categorization, and subtle interactive micro-animations powered by the assets in `public/`.

---

#### 2.0 Design Decisions (Locked)

| Decision | Choice |
|---|---|
| **App Name** | PaperFlow |
| **Theme** | Light mode only (clean, warm academic feel) |
| **Color Palette** | Warm tones — amber, cream, warm slate, crisp white surfaces |
| **Layout Style** | **Digital Library / E-Book Store** (content-first shelves & racks, no generic SaaS marketing banners) |
| **Download Experience** | **Frictionless 1-Click Download** directly from paper cards, detail pages, and upload success |
| **Asset Library** | Assets mapped from `public/` (Streamline SVGs, UnDraw, Lordicon JSON animations, and Lottie) |
| **Tailwind** | v3 (stable, class-based config) |
| **Frontend Location** | `f:\call\frontend\` (monorepo, same Git repo as backend) |

---

#### 2.1 Asset Mapping from `public/`

We will integrate the assets located in `public/`:

| Feature / UI Context | Asset File in `public/` | Usage |
|---|---|---|
| **Search Bar** | `wired-outline-19-magnifier-hover-spin.json` | Animated search trigger |
| **Upload Dropzone** | `Cloud-Upload--Streamline-Ultimate.svg` & `Upload-File--Streamline-Brooklyn.svg` | Drag-and-drop illustrations |
| **Processing Progress** | `loading.lottie` & `undraw_progress-bar_o44f.svg` | Real-time stage tracker |
| **Thank You / Completed** | `Thank-You-2--Streamline-Brooklyn.svg` & `Thank-You-3--Streamline-Brooklyn.svg` | Post-upload celebration card |
| **Empty Search / Catalog** | `Empty-Folder-E-Commerce--Streamline-Brooklyn.svg` & `No-Files-3--Streamline-Brooklyn.svg` | No-results empty states |
| **AI Typeset Badge** | `Artificial-Intelligence-1--Streamline-Brooklyn.svg` | "AI Typeset & Refined" badge |
| **Report Inaccuracy** | `wired-outline-1140-warning-triangle-hover-enlarge.json` | Non-intrusive report button icon |
| **404 Page** | `404 error page with cat.lottie` / `Page-Not-Found-1--Streamline-Brooklyn.svg` | Not found route |

---

#### 2.2 Design System & Tokens

##### Color Palette
```
Primary Accent:   #D97706 (amber-600)       — 1-click Download buttons, active tabs
Primary Hover:    #B45309 (amber-700)       — hover states
Primary Light:    #FEF3C7 (amber-100)       — badges, pill highlights
Secondary Text:   #78350F (amber-900)       — section rack titles, author/course names
Background:       #FAF8F5 (warm parchment)  — digital library backdrop
Card Surface:     #FFFFFF (pure white)      — paper book/card containers
Card Border:      #F1ECE4 (warm stone-200)  — delicate book borders & dividers
Text Main:        #1C1917 (stone-900)       — primary typography
Text Muted:       #78716C (stone-500)       — metadata (year, course code, university)
Success / Ready:  #059669 (emerald-600)     — "Refined PDF Available" status dot
```

##### Typography
- **Headings & Library Titles**: `Inter` / `Outfit` — clean, crisp, editorial
- **Body & Metadata**: `Inter` — optimal readability for course numbers and dates
- **LaTeX / Math preview**: `KaTeX` & `JetBrains Mono`

---

#### 2.3 Page 1: Homepage (`/`) — The Digital Exam Library

Designed like an **E-Book Store / Open Library catalog**:

##### 1. Sticky Header & Omnisearch Bar
- Minimal top bar with PaperFlow logo and quick links (`Library`, `Upload Paper`).
- Centerpiece **Omnisearch Bar** with the animated magnifier icon:
  - Instant live filter as you type (course code, university, topic, or keyword).
  - Quick filter chips immediately underneath: `All`, `📐 Math & Physics`, `💻 CompSci`, `⚡ Engineering`, `🧪 Sciences`.

##### 2. "Featured / Recently Refined" Shelf (Horizontal Book-Rack)
- Carousel / scrollable shelf displaying recently refined exam papers.
- Each paper card resembles a clean academic book cover with:
  - University Crest/Badge & Year tag (e.g., `AASTU • 2025`)
  - Course Title (`Calculus I — Final Exam`)
  - Format Badge (`LaTeX PDF`, `Math-Heavy`)
  - **Direct 1-Click `[Download PDF]` button** (with download icon) right on the card for instant access without opening a new page!
  - Secondary preview button to inspect questions and original scan.

##### 3. Categorized Subject Racks & Faceted Filter Bar
- Browse papers organized in structured racks:
  - By **University** (e.g., Addis Ababa University, AASTU, etc.)
  - By **Exam Level** (Midterm, Final, Quiz)
  - By **Year & Semester**
- Toggle between **Grid View** (book cards) and **Compact List View** (dense table for fast bulk downloading).

---

#### 2.4 Page 2: Upload Page (`/upload`)

Frictionless upload flow:

##### 1. Dropzone with Streamline SVG & Lottie
- Drag & drop area accepting PDF scans or phone photos (`.pdf`, `.png`, `.jpg`).
- Immediate file preview thumbnail and size verification.

##### 2. Quick Optional Metadata
- Auto-detected or optional fields (University, Course, Year, Semester, optional Email).
- `[Refine Paper]` prominent action button.

##### 3. Live 5-Stage Animated Progress Tracker
- `Preprocess → Extract → Analyze → Rewrite → Render`
- Active stage pulses with `loading.lottie` animation; completed stages turn emerald green with checkmarks.

##### 4. Thank You & Instant Download Card
- Displays `Thank-You-2--Streamline-Brooklyn.svg`.
- **Immediate 1-Click `[Download Refined PDF]` button**.
- Shareable paper link and "Upload Another" quick button.

---

#### 2.5 Page 3: Paper Detail (`/papers/[id]`)

- Full paper metadata and high-resolution PDF preview (via embedded viewer).
- **Sticky Download Header**: Instant 1-click download of both the Refined PDF and the Original upload.
- Collapsible Extracted Questions list.
- Optional non-intrusive "Report Inaccuracy" button (modal with warning icon) for students to report any equation or OCR issues for automated AI re-fixing.

---

#### 2.6 Project Structure (`f:\call\frontend\`)

```
f:\call\frontend\
├── public/                 # Assets (SVGs, Lottie, JSONs already provided)
├── src/
│   ├── app/
│   │   ├── layout.tsx      # Root layout & warm theme setup
│   │   ├── page.tsx        # Homepage (Digital Library & Racks)
│   │   ├── globals.css     # Tailwind & library styles
│   │   ├── upload/
│   │   │   └── page.tsx    # Upload & live progress
│   │   └── papers/
│   │       └── [id]/
│   │           └── page.tsx # Paper detail & embedded reader
│   ├── components/
│   │   ├── layout/
│   │   │   ├── Navbar.tsx
│   │   │   └── Footer.tsx
│   │   ├── library/
│   │   │   ├── SearchHeader.tsx   # Omnisearch bar & quick chips
│   │   │   ├── ShelfRow.tsx       # Horizontal book/paper shelf
│   │   │   ├── PaperCard.tsx      # Book-cover card with 1-click download
│   │   │   ├── FilterSidebar.tsx  # University / Year / Course filters
│   │   │   └── CompactListView.tsx # Dense download table view
│   │   ├── upload/
│   │   │   ├── DropZone.tsx
│   │   │   ├── ProgressTracker.tsx
│   │   │   └── ThankYouCard.tsx
│   │   ├── paper/
│   │   │   ├── PaperViewer.tsx
│   │   │   ├── QuestionAccordion.tsx
│   │   │   └── ReportModal.tsx
│   │   └── ui/
│   │       ├── Button.tsx
│   │       ├── Badge.tsx
│   │       └── LottieIcon.tsx     # Player for .lottie & .json icons
│   ├── lib/
│   │   ├── api.ts          # FastAPI backend client
│   │   ├── types.ts        # TypeScript schemas
│   │   └── utils.ts
│   └── hooks/
│       ├── usePapers.ts    # Library query & filter state
│       └── useUpload.ts    # Upload & stage polling
├── tailwind.config.ts
├── package.json
└── tsconfig.json
```

---

#### 2.7 Verification Plan for Phase 2

1. **Digital Library UI Check**: Verify homepage looks like a modern digital book repository with shelves, cover cards, and warm aesthetics.
2. **1-Click Download Test**: Verify clicking "Download" on any card immediately fetches the refined PDF without redirection.
3. **Asset Verification**: Confirm Streamline SVGs, UnDraw graphics, and Lottie animations render correctly.
4. **End-to-End Upload & Live Polling**: Upload a test paper and verify stage transitions (`1/5 → 5/5`) followed by the Thank You card.
5. **Responsive Check**: Test navigation, shelves, and downloads across mobile, tablet, and desktop.

### Phase 3: Advanced Pipeline & Deep Search Features
- **Categorized Deep PDF Search Engine**: High-performance search engine combining SQLite FTS5 / Meilisearch (for exact keyword/word extraction from specific PDFs) + Vector Search (RAG with Qdrant/pgvector for semantic question matching). Allows users to search for specific words or formulas within any paper and see results cleanly categorized.
- **Diagram & Graph Support**: Detect diagrams in the original paper, extract them, and strategically place them back into the rewritten document.
- **Multi-page Batching**: Handle massive 100-page exams by chunking Gemini API calls to avoid token limits.

### Phase 4: Production Deployment (Old PC VPS)
- **Dockerization**: Create a `docker-compose.yml` to spin up FastAPI, PostgreSQL, Redis, Celery workers, and the Next.js frontend with a single command.
- **Reverse Proxy & SSL**: Configure Caddy or Nginx to serve the app securely over HTTPS.
- **Automated Backups**: Scripts to back up the PostgreSQL database and stored original/derivative files to external storage.
