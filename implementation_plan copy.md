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
- **Task Queue Integration**: Introduce Celery and Redis to handle the pipeline asynchronously. This prevents the FastAPI upload endpoint from blocking and allows parallel processing of multiple papers.
- **Webhooks & Polling**: Add WebSocket support or Webhooks so the frontend can receive real-time updates as a paper moves through `preprocess → extract → analyze → rewrite → render`.
- **Granular Retries**: Allow retrying specific failed stages (e.g., if rendering fails due to LaTeX syntax, only retry the rewrite/render steps) instead of restarting the entire pipeline.

### Phase 2: Frontend Web Application
- **Tech Stack**: Next.js (React) + Tailwind CSS + TypeScript + Framer Motion + Lottie (`dotlottie-react` / `@lottiefiles/react-lottie-player`).
- **Design Philosophy**: Minimalist, clean, and distraction-free UI enriched with vector SVG illustrations, interactive Lottie animations (`.lottie` / `.json`), smooth transitions, and Lucide icons.
- **Homepage & Categorized Catalog**: Display papers cleanly grouped by intuitive categories (e.g., University, Course, Exam Type, Subject Area, Year) with quick-access cards.
- **Upload & Thank You Flow**: Drag-and-drop upload zone with animated Lottie feedback during processing. Once completed, the website immediately thanks the user for contributing and offers the direct download for the refined PDF.
- **Optional "Report Inaccuracy" Button**: Students are never forced or prompted to review code. If a student notices a mistake later while viewing a paper, they can optionally click a "Report Inaccuracy" button, describe what's wrong (e.g. *"Question 3 equation is missing a minus sign"*), and submit it to trigger an automated AI fix.

### Phase 3: Advanced Pipeline & Deep Search Features
- **Categorized Deep PDF Search Engine**: High-performance search engine combining SQLite FTS5 / Meilisearch (for exact keyword/word extraction from specific PDFs) + Vector Search (RAG with Qdrant/pgvector for semantic question matching). Allows users to search for specific words or formulas within any paper and see results cleanly categorized.
- **Diagram & Graph Support**: Detect diagrams in the original paper, extract them, and strategically place them back into the rewritten document.
- **Multi-page Batching**: Handle massive 100-page exams by chunking Gemini API calls to avoid token limits.

### Phase 4: Production Deployment (Old PC VPS)
- **Dockerization**: Create a `docker-compose.yml` to spin up FastAPI, PostgreSQL, Redis, Celery workers, and the Next.js frontend with a single command.
- **Reverse Proxy & SSL**: Configure Caddy or Nginx to serve the app securely over HTTPS.
- **Automated Backups**: Scripts to back up the PostgreSQL database and stored original/derivative files to external storage.
