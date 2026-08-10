"""ExamPaper Refine - Database models and Pydantic schemas."""

from __future__ import annotations

import enum
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, Field
from sqlalchemy import (
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from app.database import Base


# ── Enums ──────────────────────────────────────────────────────────────────────


class PaperStatus(str, enum.Enum):
    """Processing lifecycle of an exam paper."""

    UPLOADED = "uploaded"
    VALIDATING = "validating"
    PREPROCESSING = "preprocessing"
    EXTRACTING = "extracting"
    ANALYZING = "analyzing"
    REWRITING = "rewriting"
    RENDERING = "rendering"
    NEEDS_REVIEW = "needs_review"
    PUBLISHED = "published"
    REJECTED = "rejected"
    FAILED = "failed"


class DerivativeType(str, enum.Enum):
    """Types of derived files generated from an original."""

    CLEANED_SCAN = "cleaned_scan"
    REWRITTEN_LATEX = "rewritten_latex"
    REWRITTEN_HTML = "rewritten_html"
    REWRITTEN_MARKDOWN = "rewritten_markdown"
    FINAL_PDF = "final_pdf"


class DocumentType(str, enum.Enum):
    """Classification of document content type."""

    MATH_HEAVY = "math_heavy"
    TEXT_ONLY = "text_only"
    MIXED = "mixed"
    DIAGRAM_HEAVY = "diagram_heavy"


class ProcessingStage(str, enum.Enum):
    """Individual stages of the processing pipeline."""

    UPLOAD = "upload"
    PREPROCESS = "preprocess"
    EXTRACT = "extract"
    ANALYZE = "analyze"
    REWRITE = "rewrite"
    RENDER = "render"


class StageStatus(str, enum.Enum):
    """Status of an individual processing stage."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


# ── SQLAlchemy Models ──────────────────────────────────────────────────────────


def _generate_id() -> str:
    return uuid4().hex[:12]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ExamPaper(Base):
    """An uploaded exam paper and its metadata."""

    __tablename__ = "exam_papers"

    id = Column(String(12), primary_key=True, default=_generate_id)
    title = Column(String(500), nullable=True)
    original_filename = Column(String(500), nullable=False)
    source_sha256 = Column(String(64), nullable=False, unique=True, index=True)
    original_file_path = Column(String(1000), nullable=False)

    # Metadata (populated by analyzer)
    university = Column(String(300), nullable=True)
    department = Column(String(300), nullable=True)
    course_code = Column(String(50), nullable=True)
    course_name = Column(String(300), nullable=True)
    year = Column(Integer, nullable=True)
    semester = Column(String(50), nullable=True)
    exam_type = Column(String(100), nullable=True)  # midterm, final, quiz, etc.
    language = Column(String(50), default="en")
    instructor = Column(String(300), nullable=True)

    # Classification
    document_type = Column(Enum(DocumentType), nullable=True)
    page_count = Column(Integer, nullable=True)
    has_embedded_text = Column(Integer, default=0)  # SQLite boolean

    # Processing
    status = Column(Enum(PaperStatus), default=PaperStatus.UPLOADED, index=True)
    quality_score = Column(Float, nullable=True)
    extraction_confidence = Column(Float, nullable=True)
    pipeline_version = Column(String(50), default="0.1.0")

    # Timestamps
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)

    # Relationships
    derivatives = relationship(
        "PaperDerivative", back_populates="paper", cascade="all, delete-orphan"
    )
    questions = relationship(
        "Question", back_populates="paper", cascade="all, delete-orphan"
    )
    processing_logs = relationship(
        "ProcessingLog", back_populates="paper", cascade="all, delete-orphan"
    )


class PaperDerivative(Base):
    """A derived file generated from an exam paper (cleaned scan, rewritten doc, final PDF)."""

    __tablename__ = "paper_derivatives"

    id = Column(String(12), primary_key=True, default=_generate_id)
    exam_paper_id = Column(
        String(12), ForeignKey("exam_papers.id", ondelete="CASCADE"), nullable=False
    )
    version = Column(Integer, default=1)
    file_path = Column(String(1000), nullable=False)
    derivative_type = Column(Enum(DerivativeType), nullable=False)
    checksum = Column(String(64), nullable=True)

    # Processing provenance
    pipeline_version = Column(String(50), nullable=True)
    ocr_engine = Column(String(100), nullable=True)
    model_version = Column(String(100), nullable=True)
    parameters = Column(JSON, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=_utcnow)

    # Relationships
    paper = relationship("ExamPaper", back_populates="derivatives")


class Question(Base):
    """An extracted question from an exam paper."""

    __tablename__ = "questions"

    id = Column(String(12), primary_key=True, default=_generate_id)
    exam_paper_id = Column(
        String(12), ForeignKey("exam_papers.id", ondelete="CASCADE"), nullable=False
    )
    parent_question_id = Column(
        String(12), ForeignKey("questions.id", ondelete="SET NULL"), nullable=True
    )

    # Question data
    display_number = Column(String(20), nullable=True)  # "1", "2a", "3.ii"
    normalized_order = Column(Integer, nullable=True)
    text = Column(Text, nullable=False)
    marks = Column(Float, nullable=True)

    # Location in original document
    page_start = Column(Integer, nullable=True)
    page_end = Column(Integer, nullable=True)

    # Quality
    extraction_confidence = Column(Float, nullable=True)
    extraction_version = Column(String(50), nullable=True)

    # Topics / tags stored as JSON array
    topics = Column(JSON, nullable=True)

    # Relationships
    paper = relationship("ExamPaper", back_populates="questions")
    sub_questions = relationship(
        "Question",
        backref="parent",
        remote_side=[id],
        cascade="all, delete-orphan",
        single_parent=True,
    )


class ProcessingLog(Base):
    """Log entry for a processing stage."""

    __tablename__ = "processing_logs"

    id = Column(String(12), primary_key=True, default=_generate_id)
    exam_paper_id = Column(
        String(12), ForeignKey("exam_papers.id", ondelete="CASCADE"), nullable=False
    )
    stage = Column(Enum(ProcessingStage), nullable=False)
    status = Column(Enum(StageStatus), default=StageStatus.PENDING)

    # Timing
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    # Results
    error_details = Column(Text, nullable=True)
    metrics = Column(JSON, nullable=True)  # stage-specific metrics

    # Relationships
    paper = relationship("ExamPaper", back_populates="processing_logs")


# ── Pydantic Response Schemas ──────────────────────────────────────────────────


class PaperSummary(BaseModel):
    """Paper summary for list endpoints."""

    id: str
    title: Optional[str] = None
    original_filename: str
    university: Optional[str] = None
    course_code: Optional[str] = None
    course_name: Optional[str] = None
    year: Optional[int] = None
    semester: Optional[str] = None
    exam_type: Optional[str] = None
    document_type: Optional[str] = None
    status: str
    page_count: Optional[int] = None
    quality_score: Optional[float] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class QuestionSchema(BaseModel):
    """Question data for API responses."""

    id: str
    display_number: Optional[str] = None
    normalized_order: Optional[int] = None
    text: str
    marks: Optional[float] = None
    page_start: Optional[int] = None
    page_end: Optional[int] = None
    extraction_confidence: Optional[float] = None
    topics: Optional[list[str]] = None
    sub_questions: list[QuestionSchema] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class DerivativeSchema(BaseModel):
    """Derivative file info for API responses."""

    id: str
    version: int
    derivative_type: str
    pipeline_version: Optional[str] = None
    ocr_engine: Optional[str] = None
    model_version: Optional[str] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class ProcessingLogSchema(BaseModel):
    """Processing log entry for API responses."""

    stage: str
    status: str
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_details: Optional[str] = None
    metrics: Optional[dict] = None

    model_config = {"from_attributes": True}


class PaperDetail(PaperSummary):
    """Full paper details including questions, derivatives, and processing logs."""

    language: Optional[str] = None
    department: Optional[str] = None
    instructor: Optional[str] = None
    extraction_confidence: Optional[float] = None
    pipeline_version: Optional[str] = None
    updated_at: Optional[datetime] = None
    questions: list[QuestionSchema] = Field(default_factory=list)
    derivatives: list[DerivativeSchema] = Field(default_factory=list)
    processing_logs: list[ProcessingLogSchema] = Field(default_factory=list)


class UploadResponse(BaseModel):
    """Response after uploading a paper."""

    id: str
    status: str
    message: str


class ProcessingStatusResponse(BaseModel):
    """Current processing status of a paper."""

    id: str
    status: str
    stages: list[ProcessingLogSchema] = Field(default_factory=list)
    current_stage: Optional[str] = None
    error: Optional[str] = None
