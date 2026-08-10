"""ExamPaper Refine - Pipeline Orchestrator.

Coordinates the full document processing pipeline:
Upload -> Preprocess -> Extract -> Analyze -> Rewrite -> Render -> Store.
"""

from __future__ import annotations

import logging
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
    PaperStatus,
    ProcessingLog,
    ProcessingStage,
    Question,
    StageStatus,
)
from pipeline.analyzer import analyze
from pipeline.extractor import extract_text
from pipeline.preprocessor import preprocess
from pipeline.renderer import render
from pipeline.rewriter import rewrite
from pipeline.schemas import PipelineResult
from storage.local import storage

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


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
    
    # Also update the main paper status
    paper = await db.get(ExamPaper, paper_id)
    if paper:
        if status == StageStatus.FAILED:
            paper.status = PaperStatus.FAILED
        elif stage == ProcessingStage.PREPROCESS and status == StageStatus.RUNNING:
            paper.status = PaperStatus.PREPROCESSING
        elif stage == ProcessingStage.EXTRACT and status == StageStatus.RUNNING:
            paper.status = PaperStatus.EXTRACTING
        elif stage == ProcessingStage.ANALYZE and status == StageStatus.RUNNING:
            paper.status = PaperStatus.ANALYZING
        elif stage == ProcessingStage.REWRITE and status == StageStatus.RUNNING:
            paper.status = PaperStatus.REWRITING
        elif stage == ProcessingStage.RENDER and status == StageStatus.RUNNING:
            paper.status = PaperStatus.RENDERING
        elif stage == ProcessingStage.RENDER and status == StageStatus.COMPLETED:
            paper.status = PaperStatus.NEEDS_REVIEW

    await db.commit()
    return log


async def process_paper(db: AsyncSession, paper_id: str) -> PipelineResult:
    """Run the full processing pipeline for a given paper.
    
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
            ana_res = analyze(ext_res, prep_res)
            result.analysis = ana_res
            
            # Update paper metadata
            m = ana_res.metadata
            paper.document_type = ana_res.document_type
            paper.university = m.university or paper.university
            paper.department = m.department
            paper.course_code = m.course_code or paper.course_code
            paper.course_name = m.course_name
            paper.year = m.year or paper.year
            paper.semester = m.semester
            paper.exam_type = m.exam_type
            paper.language = m.language
            paper.instructor = m.instructor
            paper.quality_score = ana_res.confidence
            
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
        try:
            rew_res = rewrite(ext_res, ana_res, work_dir)
            result.rewrite = rew_res
            
            # Store the source code derivative
            source_type = DerivativeType.REWRITTEN_LATEX if rew_res.format_chosen == "latex" else DerivativeType.REWRITTEN_HTML
            ext = ".tex" if rew_res.format_chosen == "latex" else ".html"
            
            source_key = storage.store_derivative(
                rew_res.source_file_path,
                paper_id,
                version=1,
                derivative_type=source_type.value,
                extension=ext
            )
            
            db.add(PaperDerivative(
                exam_paper_id=paper_id,
                derivative_type=source_type,
                file_path=source_key,
                pipeline_version="0.1.0",
                model_version=rew_res.model_used,
            ))
            
            await _log_stage(
                db, paper_id, ProcessingStage.REWRITE, StageStatus.COMPLETED, stage_start,
                metrics={"format": rew_res.format_chosen}
            )
        except Exception as e:
            logger.exception("Rewrite failed")
            await _log_stage(db, paper_id, ProcessingStage.REWRITE, StageStatus.FAILED, stage_start, str(e))
            result.status = "failed"
            result.error = str(e)
            return result

        # ── 6. Render (Source -> PDF) ───────────────────────────────────────────
        stage_start = _utcnow()
        await _log_stage(db, paper_id, ProcessingStage.RENDER, StageStatus.RUNNING, stage_start)
        try:
            ren_res = render(rew_res, work_dir)
            result.render = ren_res
            
            if not ren_res.pdf_path:
                raise ValueError("Renderer did not produce a PDF")
                
            # Store final PDF
            pdf_key = storage.store_derivative(
                ren_res.pdf_path,
                paper_id,
                version=1,
                derivative_type=DerivativeType.FINAL_PDF.value,
                extension=".pdf"
            )
            
            db.add(PaperDerivative(
                exam_paper_id=paper_id,
                derivative_type=DerivativeType.FINAL_PDF,
                file_path=pdf_key,
                pipeline_version="0.1.0",
            ))
            
            await _log_stage(
                db, paper_id, ProcessingStage.RENDER, StageStatus.COMPLETED, stage_start,
                metrics={"engine": ren_res.render_engine, "size": ren_res.pdf_size_bytes}
            )
        except Exception as e:
            logger.exception("Rendering failed")
            await _log_stage(db, paper_id, ProcessingStage.RENDER, StageStatus.FAILED, stage_start, str(e))
            result.status = "failed"
            result.error = str(e)
            return result

    # ── Finalize ────────────────────────────────────────────────────────────────
    result.status = "completed"
    result.total_processing_time_seconds = round(time.time() - overall_start, 3)
    result.completed_at = _utcnow()
    
    logger.info(f"Successfully processed paper {paper_id} in {result.total_processing_time_seconds}s")
    return result
