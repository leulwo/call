"""ExamPaper Refine - Pipeline Orchestrator.

Coordinates the full document processing pipeline:
Upload -> Preprocess -> Extract -> Analyze -> Rewrite -> Render -> Store.
"""

from __future__ import annotations

import logging
import json
import shutil
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    DerivativeType,
    ExamPaper,
    PaperDerivative,
    PaperReport,
    PaperStatus,
    ProcessingLog,
    ProcessingStage,
    Question,
    StageStatus,
)
from sqlalchemy import func as sa_func, select
from services.metadata_resolver import cache_ai_resolutions, resolve_metadata_context
from services import knowledge_base
from pipeline.analyzer import analyze
from pipeline.extractor import extract_text
from pipeline.preprocessor import preprocess
from pipeline.renderer import render
from pipeline.rewriter import rewrite
from pipeline.schemas import PipelineResult, RenderResult
from storage.local import storage

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _make_original_pdf(source_path: Path, work_dir: Path, prepared_pages: Optional[list] = None) -> Path:
    """Create a readable cleaned-PDF fallback when AI typesetting is unavailable.

    The preprocessor has already rendered PDFs and cleaned image uploads. Use
    those page images here instead of simply copying the user's original file;
    this keeps the product useful when the external AI service is unavailable.
    """
    fallback_path = work_dir / "cleaned-fallback.pdf"
    page_paths = [Path(page.image_path) for page in (prepared_pages or []) if Path(page.image_path).is_file()]

    from PIL import Image

    if page_paths:
        frames = []
        for page_path in page_paths:
            with Image.open(page_path) as page_image:
                frames.append(page_image.convert("RGB"))
        frames[0].save(fallback_path, "PDF", resolution=150.0, save_all=True, append_images=frames[1:])
        return fallback_path

    if source_path.suffix.lower() == ".pdf":
        shutil.copy2(source_path, fallback_path)
        return fallback_path

    with Image.open(source_path) as image:
        frames = []
        try:
            for index in range(getattr(image, "n_frames", 1)):
                image.seek(index)
                frames.append(image.convert("RGB"))
        except EOFError:
            pass
        if not frames:
            frames = [image.convert("RGB")]
        frames[0].save(fallback_path, "PDF", resolution=150.0, save_all=True, append_images=frames[1:])
    return fallback_path


async def _log_stage(
    db: AsyncSession,
    paper_id: str,
    stage: ProcessingStage,
    status: StageStatus,
    start_time: Optional[datetime] = None,
    error_details: Optional[str] = None,
    metrics: Optional[dict] = None,
) -> ProcessingLog:
    """Record a stage transition in the database."""
    log = ProcessingLog(
        exam_paper_id=paper_id,
        stage=stage,
        status=status,
        started_at=start_time or _utcnow(),
        completed_at=_utcnow() if status in (StageStatus.COMPLETED, StageStatus.FAILED) else None,
        error_details=error_details,
        metrics=metrics or {},
    )
    db.add(log)

    stage_order = {
        ProcessingStage.PREPROCESS: (1, PaperStatus.PREPROCESSING),
        ProcessingStage.EXTRACT: (2, PaperStatus.EXTRACTING),
        ProcessingStage.ANALYZE: (3, PaperStatus.ANALYZING),
        ProcessingStage.REWRITE: (4, PaperStatus.REWRITING),
        ProcessingStage.RENDER: (5, PaperStatus.RENDERING),
    }

    # Also update the main paper status and progress tracking
    paper = await db.get(ExamPaper, paper_id)
    if paper:
        paper.current_stage = stage.value
        if status == StageStatus.FAILED:
            paper.status = PaperStatus.FAILED
            paper.failed_stage = stage.value
        elif status == StageStatus.RUNNING:
            step, paper_status = stage_order.get(stage, (0, PaperStatus.VALIDATING))
            paper.status = paper_status
            paper.stage_progress = step
        elif stage == ProcessingStage.RENDER and status == StageStatus.COMPLETED:
            paper.status = PaperStatus.COMPLETED
            paper.stage_progress = 6
            paper.current_stage = "completed"

    await db.commit()
    return log



async def process_paper(db: AsyncSession, paper_id: str, rewrite_feedback: Optional[str] = None) -> PipelineResult:
    """Run the full processing pipeline for a given paper.

    Args:
        rewrite_feedback: Optional user correction request (from an accuracy
            report). When provided, the AI rewrite is instructed to address it
            and the new derivatives are stored as the next version instead of
            overwriting v1.
    
    For Phase 0, this runs synchronously in the background task.
    In Phase 1, this will be broken up into Celery tasks.
    """
    overall_start = time.time()
    result = PipelineResult(paper_id=paper_id, status="running")
    
    # ── 1. Fetch paper ──────────────────────────────────────────────────────────
    paper = await db.get(ExamPaper, paper_id)
    if not paper:
        result.status = "failed"
        result.error = f"Paper {paper_id} not found"
        return result

    file_path = storage.get_original_path(paper.original_file_path)
    if not file_path.exists():
        result.status = "failed"
        result.error = f"Original file missing: {file_path}"
        await _log_stage(db, paper_id, ProcessingStage.PREPROCESS, StageStatus.FAILED, error_details=result.error)
        return result

    # Use a temporary directory for all intermediate files
    with tempfile.TemporaryDirectory() as tmpdir:
        work_dir = Path(tmpdir)
        
        # ── 2. Preprocess ───────────────────────────────────────────────────────
        stage_start = _utcnow()
        await _log_stage(db, paper_id, ProcessingStage.PREPROCESS, StageStatus.RUNNING, stage_start)
        try:
            prep_res = preprocess(file_path, work_dir)
            result.preprocess = prep_res
            if prep_res.errors and not prep_res.pages:
                raise ValueError("Preprocessing failed to extract any pages")
                
            paper.page_count = prep_res.page_count
            await _log_stage(
                db, paper_id, ProcessingStage.PREPROCESS, StageStatus.COMPLETED, stage_start,
                metrics={"page_count": prep_res.page_count, "time_s": prep_res.processing_time_seconds}
            )
        except Exception as e:
            logger.exception("Preprocessing failed")
            await _log_stage(db, paper_id, ProcessingStage.PREPROCESS, StageStatus.FAILED, stage_start, str(e))
            result.status = "failed"
            result.error = str(e)
            return result

        # ── 3. Extract Text ─────────────────────────────────────────────────────
        stage_start = _utcnow()
        await _log_stage(db, paper_id, ProcessingStage.EXTRACT, StageStatus.RUNNING, stage_start)
        try:
            ext_res = extract_text(prep_res)
            result.extraction = ext_res
            
            paper.extraction_confidence = ext_res.overall_confidence
            paper.has_embedded_text = int("embedded" in ext_res.methods_used)
            # Keep the extracted text attached to the paper so catalog search can
            # find a phrase inside a PDF, not only its manually entered metadata.
            paper.extracted_text = ext_res.full_text
            
            await _log_stage(
                db, paper_id, ProcessingStage.EXTRACT, StageStatus.COMPLETED, stage_start,
                metrics={"words": ext_res.total_word_count, "confidence": ext_res.overall_confidence}
            )
        except Exception as e:
            logger.exception("Extraction failed")
            await _log_stage(db, paper_id, ProcessingStage.EXTRACT, StageStatus.FAILED, stage_start, str(e))
            result.status = "failed"
            result.error = str(e)
            return result

        # ── 4. Analyze (AI Structure & Metadata) ────────────────────────────────
        stage_start = _utcnow()
        await _log_stage(db, paper_id, ProcessingStage.ANALYZE, StageStatus.RUNNING, stage_start)
        try:
            try:
                metadata_envelope = json.loads(paper.metadata_json or "{}")
            except json.JSONDecodeError:
                metadata_envelope = {"provided": {}}

            # Resolve cached aliases immediately and use the external lookup
            # only here, inside the queued worker. The raw user context stays
            # attached to the resolved JSON sent to the AI analyzer.
            metadata_context = await resolve_metadata_context(
                db,
                metadata_envelope,
                allow_web_lookup=True,
            )
            paper.metadata_json = json.dumps(metadata_context, ensure_ascii=False)
            resolved = metadata_context.get("resolved", {})
            paper.university = resolved.get("university") or paper.university
            paper.university_type = resolved.get("university_type") or paper.university_type
            paper.study_year = resolved.get("study_year") or paper.study_year
            paper.department = resolved.get("department") or paper.department
            paper.course_code = resolved.get("course_code") or paper.course_code
            paper.course_name = resolved.get("course_name") or paper.course_name

            # Ground the AI analyzer with the matched university's knowledge
            # base entry (canonical names, colleges, course-code prefixes).
            university_resolution = metadata_context.get("resolutions", {}).get(
                "university"
            ) or {"canonical_value": resolved.get("university")}
            kb_context = knowledge_base.university_context(university_resolution)

            ana_res = analyze(ext_res, prep_res, provided_metadata=metadata_context, knowledge_context=kb_context)
            result.analysis = ana_res
            
            # Update paper metadata
            m = ana_res.metadata
            paper.document_type = ana_res.document_type
            paper.title = paper.title or m.title or paper.original_filename
            paper.description = paper.description or m.description
            # Canonical name wins: the resolver/knowledge-base form beats the
            # AI's raw wording (which may be an abbreviation from the source).
            ai_university = m.university
            if ai_university and not resolved.get("university"):
                kb_match = knowledge_base.match_university(ai_university)
                if kb_match:
                    ai_university = kb_match.get("canonical_value") or ai_university
            paper.university = resolved.get("university") or ai_university or paper.university
            paper.university_type = m.university_type or resolved.get("university_type") or paper.university_type
            paper.study_year = m.study_year or resolved.get("study_year") or paper.study_year
            paper.department = m.department or resolved.get("department") or paper.department
            paper.course_code = m.course_code or resolved.get("course_code") or paper.course_code
            paper.course_name = m.course_name or resolved.get("course_name") or paper.course_name
            paper.year = paper.year or m.year
            paper.semester = paper.semester or m.semester
            paper.exam_type = paper.exam_type or m.exam_type
            paper.language = m.language
            paper.instructor = m.instructor
            paper.quality_score = ana_res.confidence

            normalized_metadata = {
                key: value
                for key, value in {
                    "title": paper.title,
                    "description": paper.description,
                    "university": paper.university,
                    "university_type": paper.university_type,
                    "study_year": paper.study_year,
                    "department": paper.department,
                    "course_code": paper.course_code,
                    "course_name": paper.course_name,
                    "year": paper.year,
                    "semester": paper.semester,
                    "exam_type": paper.exam_type,
                    "uploaded_at": metadata_context.get("uploaded_at") or (paper.created_at.isoformat() if paper.created_at else None),
                }.items()
                if value not in (None, "")
            }
            metadata_context["ai_normalized"] = {
                key: value
                for key, value in {
                    "university": m.university,
                    "university_type": m.university_type,
                    "study_year": m.study_year,
                    "department": m.department,
                    "course_code": m.course_code,
                    "course_name": m.course_name,
                }.items()
                if value not in (None, "")
            }
            metadata_context["normalized"] = normalized_metadata
            paper.metadata_json = json.dumps(metadata_context, ensure_ascii=False)
            await cache_ai_resolutions(
                db,
                metadata_context.get("provided", {}),
                metadata_context["ai_normalized"],
            )
            
            # Save parsed questions to DB
            def _save_questions(qs, parent_id=None):
                for q in qs:
                    db_q = Question(
                        exam_paper_id=paper_id,
                        parent_question_id=parent_id,
                        display_number=q.display_number,
                        normalized_order=q.normalized_order,
                        text=q.text,
                        marks=q.marks,
                        page_start=q.page_start,
                        page_end=q.page_end,
                        topics=q.topics,
                    )
                    db.add(db_q)
                    # We need the ID for children, but SQLAlchemy async flush handles this 
                    # well if we don't strictly need it immediately, or we can flush.
                    # For Phase 0, we'll just let the cascade handle it if we build the tree.
            
            _save_questions(ana_res.questions)
            
            await _log_stage(
                db, paper_id, ProcessingStage.ANALYZE, StageStatus.COMPLETED, stage_start,
                metrics={"questions": ana_res.total_questions, "type": ana_res.document_type}
            )
        except Exception as e:
            logger.exception("Analysis failed")
            await _log_stage(db, paper_id, ProcessingStage.ANALYZE, StageStatus.FAILED, stage_start, str(e))
            result.status = "failed"
            result.error = str(e)
            return result

        # ── 5. Rewrite (AI Typesetting) ─────────────────────────────────────────
        stage_start = _utcnow()
        await _log_stage(db, paper_id, ProcessingStage.REWRITE, StageStatus.RUNNING, stage_start)
        rewrite_used_fallback = False
        # Version bump: a regeneration must never overwrite the previous
        # PDF — compute the next version from existing derivatives up front so
        # both the success and fallback paths store under the same version.
        version_result = await db.execute(
            select(sa_func.max(PaperDerivative.version)).where(
                PaperDerivative.exam_paper_id == paper_id
            )
        )
        next_version = (version_result.scalar() or 0) + 1
        try:
            rew_res = rewrite(ext_res, ana_res, work_dir, feedback=rewrite_feedback)
            result.rewrite = rew_res

            if not rew_res.source_file_path or not Path(rew_res.source_file_path).is_file():
                raise FileNotFoundError("AI rewrite did not produce a source file")
            
            # Store the source code derivative
            source_type = DerivativeType.REWRITTEN_LATEX if rew_res.format_chosen == "latex" else DerivativeType.REWRITTEN_HTML
            ext = ".tex" if rew_res.format_chosen == "latex" else ".html"
            
            source_key = storage.store_derivative(
                rew_res.source_file_path,
                paper_id,
                version=next_version,
                derivative_type=source_type.value,
                extension=ext
            )
            
            db.add(PaperDerivative(
                exam_paper_id=paper_id,
                derivative_type=source_type,
                file_path=source_key,
                version=next_version,
                pipeline_version="0.1.0",
                model_version=rew_res.model_used,
            ))
            
            await _log_stage(
                db, paper_id, ProcessingStage.REWRITE, StageStatus.COMPLETED, stage_start,
                metrics={"format": rew_res.format_chosen}
            )
        except Exception as e:
            logger.exception("Rewrite failed")
            # A missing AI service or typesetting engine must not destroy a
            # valid upload. Keep a cleaned, readable PDF available and mark it
            # for review so the library can still receive it.
            await _log_stage(
                db,
                paper_id,
                ProcessingStage.REWRITE,
                StageStatus.COMPLETED,
                stage_start,
                metrics={
                    "fallback": "cleaned_preprocess_fallback",
                    "warning": "AI refinement was unavailable; showing a cleaned preview. This document will be retried when the refinement worker is available.",
                    "technical_error": str(e),
                },
            )
            rewrite_used_fallback = True
            result.error = f"AI refinement unavailable; cleaned preprocessed PDF created: {e}"

        # ── 6. Render (Source -> PDF) ───────────────────────────────────────────
        stage_start = _utcnow()
        await _log_stage(db, paper_id, ProcessingStage.RENDER, StageStatus.RUNNING, stage_start)
        try:
            if rewrite_used_fallback:
                fallback_path = _make_original_pdf(file_path, work_dir, prep_res.pages)
                result.render = RenderResult(
                    pdf_path=str(fallback_path),
                    pdf_size_bytes=fallback_path.stat().st_size,
                    render_engine="cleaned_preprocess_fallback",
                    processing_time_seconds=0,
                    page_count=paper.page_count or 0,
                    warnings=["AI refinement was unavailable; a cleaned preprocessed PDF was created."],
                )
                rendered_pdf_path = fallback_path
                render_metrics = {"engine": "cleaned_preprocess_fallback", "size": fallback_path.stat().st_size}
            else:
                ren_res = render(rew_res, work_dir)
                result.render = ren_res

                if not ren_res.pdf_path:
                    raise ValueError("Renderer did not produce a PDF")
                rendered_pdf_path = Path(ren_res.pdf_path)
                render_metrics = {"engine": ren_res.render_engine, "size": ren_res.pdf_size_bytes}

            # Store final PDF
            pdf_key = storage.store_derivative(
                rendered_pdf_path,
                paper_id,
                version=next_version,
                derivative_type=DerivativeType.FINAL_PDF.value,
                extension=".pdf"
            )
            
            db.add(PaperDerivative(
                exam_paper_id=paper_id,
                derivative_type=DerivativeType.FINAL_PDF,
                file_path=pdf_key,
                version=next_version,
                pipeline_version="0.1.0",
            ))
            
            await _log_stage(
                db, paper_id, ProcessingStage.RENDER, StageStatus.COMPLETED, stage_start,
                metrics=render_metrics
            )
        except Exception as e:
            logger.exception("Rendering failed")
            await _log_stage(db, paper_id, ProcessingStage.RENDER, StageStatus.FAILED, stage_start, str(e))
            result.status = "failed"
            result.error = str(e)
            return result

    # ── Finalize ────────────────────────────────────────────────────────────────
    if rewrite_used_fallback:
        result.status = "needs_review"
        paper.status = PaperStatus.NEEDS_REVIEW
        paper.failed_stage = ProcessingStage.REWRITE.value
        await db.commit()
    else:
        result.status = "completed"
        paper.failed_stage = None
        await db.commit()

    # Resolve accuracy reports that requested this regeneration
    if rewrite_feedback:
        regen_result = await db.execute(
            select(PaperReport).where(
                PaperReport.exam_paper_id == paper_id,
                PaperReport.status == "regenerating",
            )
        )
        for report in regen_result.scalars().all():
            report.status = "resolved"
            report.review_note = (
                f"Document regenerated as version {next_version} addressing this report."
            )
        await db.commit()

    result.total_processing_time_seconds = round(time.time() - overall_start, 3)
    result.completed_at = _utcnow()

    # Trigger optional email notification if configured
    if paper.email:
        try:
            from services.email_notifier import send_paper_ready_email
            await send_paper_ready_email(
                to_email=paper.email,
                paper_id=paper_id,
                title=paper.title or paper.original_filename,
            )
        except Exception as e:
            logger.warning(f"Failed to trigger email notification: {e}")

    logger.info(f"Successfully processed paper {paper_id} in {result.total_processing_time_seconds}s")
    return result


async def run_pipeline_for_paper(paper_id: str, rewrite_feedback: Optional[str] = None) -> PipelineResult:
    """Entry point for Celery tasks or background workers to run the pipeline.

    Uses a dedicated engine with NullPool instead of the app-wide one: each
    Celery task runs under a fresh asyncio.run() event loop, and pooled
    asyncpg connections are bound to the loop that created them. Sharing the
    global engine across loops raises "attached to a different loop" errors.
    """
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    from app.config import get_settings

    engine = create_async_engine(
        get_settings().resolved_database_url,
        poolclass=NullPool,
        future=True,
    )
    session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    try:
        async with session_factory() as session:
            return await process_paper(session, paper_id, rewrite_feedback=rewrite_feedback)
    finally:
        await engine.dispose()
