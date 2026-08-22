"""ExamPaper Refine - Versioned pipeline data schemas.

These Pydantic models define the structured data exchanged between pipeline
stages.  Every schema carries a ``schema_version`` so downstream consumers
can detect and adapt to format changes.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


SCHEMA_VERSION = "0.1.0"


# ── Preprocessor output ───────────────────────────────────────────────────────


class PageImage(BaseModel):
    """A single preprocessed page ready for OCR."""

    page_number: int
    image_path: str  # path to the saved page image
    width: int
    height: int
    has_embedded_text: bool = False
    embedded_text: Optional[str] = None
    preprocessing_applied: list[str] = Field(default_factory=list)


class PreprocessResult(BaseModel):
    """Output of the preprocessor stage."""

    schema_version: str = SCHEMA_VERSION
    source_sha256: str
    original_filename: str
    file_type: str  # "pdf", "image"
    page_count: int
    pages: list[PageImage]
    processing_time_seconds: float
    errors: list[str] = Field(default_factory=list)


# ── Extractor output ──────────────────────────────────────────────────────────


class PageText(BaseModel):
    """Extracted text for a single page."""

    page_number: int
    text: str
    method: str  # "embedded", "tesseract", "fallback"
    confidence: Optional[float] = None  # 0.0–1.0
    word_count: int = 0
    processing_time_seconds: float = 0.0


class ExtractionResult(BaseModel):
    """Output of the text extraction stage."""

    schema_version: str = SCHEMA_VERSION
    pages: list[PageText]
    overall_confidence: float = 0.0
    total_word_count: int = 0
    methods_used: list[str] = Field(default_factory=list)
    full_text: str = ""  # concatenated text of all pages
    processing_time_seconds: float = 0.0


# ── Analyzer output ───────────────────────────────────────────────────────────


class ExtractedQuestion(BaseModel):
    """A question parsed from the exam paper."""

    display_number: str  # "1", "2a", "3(ii)"
    normalized_order: int
    text: str
    marks: Optional[float] = None
    page_start: Optional[int] = None
    page_end: Optional[int] = None
    topics: list[str] = Field(default_factory=list)
    sub_questions: list[ExtractedQuestion] = Field(default_factory=list)


class ExtractedMetadata(BaseModel):
    """Metadata extracted from the document."""

    title: Optional[str] = None
    description: Optional[str] = None
    university: Optional[str] = None
    university_type: Optional[str] = None
    study_year: Optional[str] = None
    department: Optional[str] = None
    course_code: Optional[str] = None
    course_name: Optional[str] = None
    year: Optional[int] = None
    semester: Optional[str] = None
    exam_type: Optional[str] = None  # midterm, final, quiz, assignment
    language: str = "en"
    instructor: Optional[str] = None
    total_marks: Optional[float] = None
    duration: Optional[str] = None  # "2 hours", "90 minutes"
    instructions: Optional[str] = None  # general exam instructions


class AnalysisResult(BaseModel):
    """Output of the AI analysis stage."""

    schema_version: str = SCHEMA_VERSION
    document_type: str  # "math_heavy", "text_only", "mixed", "diagram_heavy"
    metadata: ExtractedMetadata
    questions: list[ExtractedQuestion]
    total_questions: int = 0
    total_marks_found: Optional[float] = None
    confidence: float = 0.0  # overall analysis confidence
    model_used: str = ""
    processing_time_seconds: float = 0.0
    warnings: list[str] = Field(default_factory=list)


# ── Rewriter output ───────────────────────────────────────────────────────────


class RewriteResult(BaseModel):
    """Output of the AI rewriting stage."""

    schema_version: str = SCHEMA_VERSION
    format_chosen: str  # "latex", "html", "markdown"
    source_content: str  # the generated LaTeX / HTML / Markdown
    source_file_path: Optional[str] = None  # where the source was saved
    model_used: str = ""
    processing_time_seconds: float = 0.0
    warnings: list[str] = Field(default_factory=list)


# ── Renderer output ───────────────────────────────────────────────────────────


class RenderResult(BaseModel):
    """Output of the rendering stage (format → PDF)."""

    schema_version: str = SCHEMA_VERSION
    pdf_path: str
    pdf_size_bytes: int = 0
    render_engine: str  # "weasyprint", "tectonic", "pdflatex"
    processing_time_seconds: float = 0.0
    page_count: int = 0
    warnings: list[str] = Field(default_factory=list)


# ── Full pipeline result ──────────────────────────────────────────────────────


class PipelineResult(BaseModel):
    """Complete result of running the full pipeline on a document."""

    paper_id: str
    status: str  # "completed", "failed", "needs_review"
    preprocess: Optional[PreprocessResult] = None
    extraction: Optional[ExtractionResult] = None
    analysis: Optional[AnalysisResult] = None
    rewrite: Optional[RewriteResult] = None
    render: Optional[RenderResult] = None
    total_processing_time_seconds: float = 0.0
    error: Optional[str] = None
    completed_at: Optional[datetime] = None
