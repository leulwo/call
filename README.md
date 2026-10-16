# ExamPaper Refine

> Turn messy exam papers into clean, beautifully typeset PDFs — powered by AI.

**ExamPaper Refine** is an open-source platform that takes uploaded exam papers (PDFs, scans, phone photos) and transforms them into clean, professionally typeset documents. The system uses AI to understand document structure, extract questions and metadata, and rewrite the paper using the best format for its content (LaTeX for math, HTML/CSS for general text), always outputting a final PDF.

## ✨ Features

- **Upload anything**: PDFs, scanned documents, phone photos
- **Immutable originals**: Your uploads are preserved exactly as-is for audit
- **AI-powered rewriting**: Gemini rebuilds the paper into a clean typeset document
- **Smart format selection**: LaTeX for math-heavy papers, HTML for general text
- **Structured extraction**: Questions, sub-questions, marks, and metadata
- **Searchable catalog**: Browse, filter, and download refined papers
- **Fully open source**: MIT licensed, self-hostable, zero vendor lock-in

## 🚀 Quick Start

### Prerequisites

- Python 3.11+
- [Tesseract OCR](https://github.com/tesseract-ocr/tesseract) installed and on PATH
- A [Google Gemini API key](https://aistudio.google.com/apikey)

### Setup

```bash
# Clone the repository
git clone https://github.com/your-username/exampaper-refine.git
cd exampaper-refine

# Create virtual environment
python -m venv .venv

# Activate (Windows)
.venv\Scripts\activate

# Activate (Linux/Mac)
source .venv/bin/activate

# Install dependencies
pip install -r backend/requirements.txt

# Configure environment
cp backend/.env.example backend/.env
# Edit backend/.env and add your GEMINI_API_KEY

# Run the development server
cd backend
uvicorn app.main:app --reload --port 8000
```

### API Usage

```bash
# Upload a paper
curl -X POST http://localhost:8000/api/upload \
  -F "file=@exam_paper.pdf" \
  -F "university=Example University" \
  -F "course_code=MATH101"

# List all papers
curl http://localhost:8000/api/papers

# Download refined PDF
curl -O http://localhost:8000/api/papers/{id}/download/refined
```

## 🏗️ Architecture

```
Upload → Preprocess → Extract → Analyze → Rewrite → Render → Store
  │         │            │          │          │         │        │
  │     deskew,      PyMuPDF    Gemini     Gemini   LaTeX/   SQLite +
  │     denoise,    Tesseract  structure   rewrite  HTML→PDF  local FS
  │     contrast                                    
  └─ store original (immutable)
```

### Tech Stack

| Layer | Technology |
|---|---|
| **API** | FastAPI + Pydantic |
| **Database** | SQLite (dev) → PostgreSQL (prod) |
| **Storage** | Local filesystem (dev) → MinIO/S3 (prod) |
| **OCR** | PyMuPDF (embedded text) + Tesseract |
| **AI** | Google Gemini API |
| **PDF Rendering** | WeasyPrint (HTML→PDF) |
| **Image Processing** | OpenCV + Pillow |

## 📁 Project Structure

```
exampaper-refine/
├── backend/
│   ├── app/                    # FastAPI application
│   │   ├── main.py             # App entry point
│   │   ├── config.py           # Configuration
│   │   ├── models.py           # Database models
│   │   ├── database.py         # DB setup
│   │   └── routers/            # API endpoints
│   ├── pipeline/               # Processing pipeline
│   │   ├── orchestrator.py     # Pipeline coordinator
│   │   ├── preprocessor.py     # Image cleanup
│   │   ├── extractor.py        # Text extraction
│   │   ├── analyzer.py         # AI structure extraction
│   │   ├── rewriter.py         # AI document rewriting
│   │   ├── renderer.py         # Format → PDF
│   │   └── schemas.py          # Pipeline data schemas
│   └── storage/                # File storage abstraction
├── test_papers/                # Sample papers for testing
├── data/                       # Runtime data
└── benchmarks/                 # Benchmark results
```

## 🤝 Contributing

Contributions are welcome! Please read the contributing guidelines (coming soon) before submitting a pull request.

## 📄 License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.
