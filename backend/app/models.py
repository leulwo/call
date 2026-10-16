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
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import relationship

from app.database import Base


# ── Enums ──────────────────────────────────────────────────────────────────────


class PaperStatus(str, enum.Enum):
    """Processing lifecycle of an exam paper."""

    QUEUED = "queued"
    UPLOADED = "uploaded"
    VALIDATING = "validating"
    PREPROCESSING = "preprocessing"
    EXTRACTING = "extracting"
    ANALYZING = "analyzing"
    REWRITING = "rewriting"
    RENDERING = "rendering"
    STORING = "storing"
    COMPLETED = "completed"
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


def _enum_values(enum_type: type[enum.Enum]) -> list[str]:
    """Persist enum values (the API strings), not Python member names."""
    return [member.value for member in enum_type]


class ExamPaper(Base):
    """An uploaded exam paper and its metadata."""

    __tablename__ = "exam_papers"

    id = Column(String(12), primary_key=True, default=_generate_id)
    title = Column(String(500), nullable=True)
    description = Column(Text, nullable=True)
    original_filename = Column(String(500), nullable=False)
    source_sha256 = Column(String(64), nullable=False, unique=True, index=True)
    original_file_path = Column(String(1000), nullable=False)

    # Metadata (populated by analyzer)
    university = Column(String(300), nullable=True)
    university_type = Column(String(50), nullable=True)  # public, private, other, unknown
    study_year = Column(String(50), nullable=True)  # freshman, sophomore, junior, senior, graduate
    department = Column(String(300), nullable=True)
    course_code = Column(String(50), nullable=True)
    course_name = Column(String(300), nullable=True)
    year = Column(Integer, nullable=True)
    semester = Column(String(50), nullable=True)
    exam_type = Column(String(100), nullable=True)  # midterm, final, quiz, etc.
    metadata_json = Column(Text, nullable=True)  # raw + resolved upload context
    # No btree index: Postgres caps index rows at ~2704 bytes and extracted
    # text regularly exceeds that. Full-text search should use a GIN index.
    extracted_text = Column(Text, nullable=True)
    language = Column(String(50), default="en")
    instructor = Column(String(300), nullable=True)

    # Classification
    document_type = Column(Enum(DocumentType, values_callable=_enum_values), nullable=True)
    page_count = Column(Integer, nullable=True)
    has_embedded_text = Column(Integer, default=0)  # SQLite boolean

    # Processing
    status = Column(Enum(PaperStatus, values_callable=_enum_values), default=PaperStatus.QUEUED, index=True)
    current_stage = Column(String(50), nullable=True)
    stage_progress = Column(Integer, default=0)  # 0 to 100 or stage index
    failed_stage = Column(String(50), nullable=True)
    email = Column(String(255), nullable=True)  # Optional submitter email for completion notice
    quality_score = Column(Float, nullable=True)
    extraction_confidence = Column(Float, nullable=True)
    save_count = Column(Integer, default=0, nullable=False)
    like_count = Column(Integer, default=0, nullable=False)
    pipeline_version = Column(String(50), default="0.1.0")

    # Authenticated uploader (null = anonymous legacy upload)
    uploader_id = Column(Uuid, nullable=True, index=True)
    uploader_name = Column(String(120), nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), default=_utcnow)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

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
    reports = relationship(
        "PaperReport", back_populates="paper", cascade="all, delete-orphan"
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
    derivative_type = Column(Enum(DerivativeType, values_callable=_enum_values), nullable=False)
    checksum = Column(String(64), nullable=True)

    # Processing provenance
    pipeline_version = Column(String(50), nullable=True)
    ocr_engine = Column(String(100), nullable=True)
    model_version = Column(String(100), nullable=True)
    parameters = Column(JSON, nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), default=_utcnow)

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


class MetadataResolution(Base):
    """Cached canonical metadata discovered from user input or the web."""

    __tablename__ = "metadata_resolutions"
    __table_args__ = (UniqueConstraint("field", "query_key", name="uq_metadata_resolution_field_key"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    field = Column(String(50), nullable=False, index=True)
    query_key = Column(String(400), nullable=False, index=True)
    raw_value = Column(String(500), nullable=False)
    canonical_value = Column(String(500), nullable=False)
    university_type = Column(String(50), nullable=True)
    source = Column(String(100), nullable=False, default="user")
    confidence = Column(Float, nullable=True)
    payload = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)


class ProcessingLog(Base):
    """Log entry for a processing stage."""

    __tablename__ = "processing_logs"

    id = Column(String(12), primary_key=True, default=_generate_id)
    exam_paper_id = Column(
        String(12), ForeignKey("exam_papers.id", ondelete="CASCADE"), nullable=False
    )
    stage = Column(Enum(ProcessingStage, values_callable=_enum_values), nullable=False)
    status = Column(Enum(StageStatus, values_callable=_enum_values), default=StageStatus.PENDING)

    # Timing
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    # Retries
    retry_count = Column(Integer, default=0)
    last_retry_at = Column(DateTime(timezone=True), nullable=True)

    # Results
    error_details = Column(Text, nullable=True)
    metrics = Column(JSON, nullable=True)  # stage-specific metrics

    # Relationships
    paper = relationship("ExamPaper", back_populates="processing_logs")


class PaperReport(Base):
    """A moderation report submitted from a document's more-actions menu."""

    __tablename__ = "paper_reports"

    id = Column(String(12), primary_key=True, default=_generate_id)
    exam_paper_id = Column(
        String(12), ForeignKey("exam_papers.id", ondelete="CASCADE"), nullable=False
    )
    reason = Column(String(80), nullable=False)
    details = Column(Text, nullable=True)
    status = Column(String(30), nullable=False, default="open")
    review_note = Column(Text, nullable=True)  # AI/human adjudication note
    created_at = Column(DateTime(timezone=True), default=_utcnow)

    paper = relationship("ExamPaper", back_populates="reports")


# ── Per-user library (cloud-persisted saves/likes/views/collections) ──────────


class PaperSave(Base):
    """A document saved by a signed-in user."""

    __tablename__ = "paper_saves"

    user_id = Column(Uuid, primary_key=True)
    paper_id = Column(
        String(12), ForeignKey("exam_papers.id", ondelete="CASCADE"), primary_key=True
    )
    created_at = Column(DateTime(timezone=True), default=_utcnow)

    paper = relationship("ExamPaper")


class PaperLike(Base):
    """A document liked by a signed-in user."""

    __tablename__ = "paper_likes"

    user_id = Column(Uuid, primary_key=True)
    paper_id = Column(
        String(12), ForeignKey("exam_papers.id", ondelete="CASCADE"), primary_key=True
    )
    created_at = Column(DateTime(timezone=True), default=_utcnow)

    paper = relationship("ExamPaper")


class PaperView(Base):
    """A signed-in user's view history entry (one row per paper)."""

    __tablename__ = "paper_views"

    user_id = Column(Uuid, primary_key=True)
    paper_id = Column(
        String(12), ForeignKey("exam_papers.id", ondelete="CASCADE"), primary_key=True
    )
    view_count = Column(Integer, nullable=False, default=1)
    last_viewed_at = Column(DateTime(timezone=True), default=_utcnow)

    paper = relationship("ExamPaper")


class UserCollection(Base):
    """A named collection of documents owned by a signed-in user."""

    __tablename__ = "user_collections"

    id = Column(String(36), primary_key=True, default=_generate_id)
    user_id = Column(Uuid, nullable=False, index=True)
    name = Column(String(80), nullable=False)
    created_at = Column(DateTime(timezone=True), default=_utcnow)

    items = relationship(
        "UserCollectionItem", cascade="all, delete-orphan", back_populates="collection"
    )


class UserCollectionItem(Base):
    """A paper inside a user's collection."""

    __tablename__ = "user_collection_items"

    collection_id = Column(
        String(36), ForeignKey("user_collections.id", ondelete="CASCADE"), primary_key=True
    )
    paper_id = Column(
        String(12), ForeignKey("exam_papers.id", ondelete="CASCADE"), primary_key=True
    )
    created_at = Column(DateTime(timezone=True), default=_utcnow)

    collection = relationship("UserCollection", back_populates="items")


# ── Pydantic Response Schemas ──────────────────────────────────────────────────


class PaperSummary(BaseModel):
    """Paper summary for list endpoints."""

    id: str
    title: Optional[str] = None
    description: Optional[str] = None
    original_filename: str
    university: Optional[str] = None
    university_type: Optional[str] = None
    study_year: Optional[str] = None
    department: Optional[str] = None
    course_code: Optional[str] = None
    course_name: Optional[str] = None
    year: Optional[int] = None
    semester: Optional[str] = None
    exam_type: Optional[str] = None
    document_type: Optional[str] = None
    status: str
    page_count: Optional[int] = None
    quality_score: Optional[float] = None
    save_count: int = 0
    like_count: int = 0
    uploader_name: Optional[str] = None
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
    sub_questions: Optional[list[QuestionSchema]] = None

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
    retry_count: Optional[int] = 0
    error_details: Optional[str] = None
    metrics: Optional[dict] = None

    model_config = {"from_attributes": True}


class PaperDetail(PaperSummary):
    """Full paper details including questions, derivatives, and processing logs."""

    language: Optional[str] = None
    instructor: Optional[str] = None
    email: Optional[str] = None
    extraction_confidence: Optional[float] = None
    pipeline_version: Optional[str] = None
    updated_at: Optional[datetime] = None
    metadata_json: Optional[str] = None
    questions: list[QuestionSchema] = Field(default_factory=list)
    derivatives: list[DerivativeSchema] = Field(default_factory=list)
    processing_logs: list[ProcessingLogSchema] = Field(default_factory=list)


class PaperInteractionRequest(BaseModel):
    kind: str = Field(pattern="^(save|unsave|like|unlike)$")


class PaperReportRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=80)
    details: Optional[str] = Field(default=None, max_length=2000)


class UploadResponse(BaseModel):
    """Response after uploading a paper."""

    id: str
    status: str
    message: str
    polling_url: str


class StageProgressInfo(BaseModel):
    """Granular per-stage status for polling."""

    name: str
    status: str  # pending, running, completed, failed, skipped
    duration_s: Optional[float] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error: Optional[str] = None


class ProcessingStatusResponse(BaseModel):
    """Current processing status of a paper with full stage breakdown."""

    id: str
    status: str
    current_stage: Optional[str] = None
    current_stage_index: int = 0
    total_stages: int = 6
    stages: list[StageProgressInfo] = Field(default_factory=list)
    download_url: Optional[str] = None
    failed_stage: Optional[str] = None
    error: Optional[str] = None
