"""ExamPaper Refine - Process Router."""

import logging
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.database import get_db
from app.middleware.rate_limit import limiter
from app.models import ExamPaper, PaperStatus, ProcessingStatusResponse, StageProgressInfo
from pipeline.orchestrator import run_pipeline_for_paper

logger = logging.getLogger(__name__)
router = APIRouter()

STANDARD_STAGES = [
    "preprocess",
    "extract",
    "analyze",
    "rewrite",
    "render",
    "store",
]


@router.get("/papers/{paper_id}/status", response_model=ProcessingStatusResponse)
async def get_processing_status(paper_id: str, db: AsyncSession = Depends(get_db)):
    """Get the granular per-stage processing progress for a paper."""
    stmt = (
        select(ExamPaper)
        .where(ExamPaper.id == paper_id)
        .options(selectinload(ExamPaper.processing_logs), selectinload(ExamPaper.derivatives))
    )
    result = await db.execute(stmt)
    paper = result.scalars().first()

    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")

    # Map logs by stage name
    logs_by_stage: dict[str, list] = {}
    for log in paper.processing_logs:
        stage_name = log.stage.value if hasattr(log.stage, "value") else str(log.stage)
        logs_by_stage.setdefault(stage_name, []).append(log)

    # Build standard 6-stage progress list
    stages_info: list[StageProgressInfo] = []
    latest_error: Optional[str] = None

    for stage_name in STANDARD_STAGES:
        stage_logs = logs_by_stage.get(stage_name, [])
        if not stage_logs:
            # Stage has not started yet
            stages_info.append(
                StageProgressInfo(
                    name=stage_name,
                    status="completed" if paper.status in (PaperStatus.COMPLETED, PaperStatus.NEEDS_REVIEW, PaperStatus.PUBLISHED) else "pending",
                )
            )
            continue

        # Get latest log for this stage
        latest_log = sorted(stage_logs, key=lambda l: l.started_at or l.id)[-1]
        log_status = latest_log.status.value if hasattr(latest_log.status, "value") else str(latest_log.status)

        duration = None
        if latest_log.started_at and latest_log.completed_at:
            duration = round((latest_log.completed_at - latest_log.started_at).total_seconds(), 2)

        if latest_log.error_details:
            latest_error = latest_log.error_details
        elif latest_log.metrics and latest_log.metrics.get("warning"):
            latest_error = str(latest_log.metrics["warning"])

        stages_info.append(
            StageProgressInfo(
                name=stage_name,
                status=log_status,
                duration_s=duration,
                started_at=latest_log.started_at,
                completed_at=latest_log.completed_at,
                error=latest_log.error_details,
            )
        )

    if paper.status == PaperStatus.NEEDS_REVIEW and not latest_error:
        latest_error = "AI refinement needs another pass; a cleaned preview is available."

    # Determine download URL if completed
    download_url = None
    has_pdf = any(d.derivative_type.value == "final_pdf" for d in paper.derivatives)
    if paper.status in (PaperStatus.COMPLETED, PaperStatus.NEEDS_REVIEW, PaperStatus.PUBLISHED) or has_pdf:
        download_url = f"/api/papers/{paper.id}/download/refined"

    return ProcessingStatusResponse(
        id=paper.id,
        status=paper.status.value if hasattr(paper.status, "value") else str(paper.status),
        current_stage=paper.current_stage,
        current_stage_index=paper.stage_progress or 0,
        total_stages=len(STANDARD_STAGES),
        stages=stages_info,
        download_url=download_url,
        failed_stage=paper.failed_stage if paper.status in (PaperStatus.NEEDS_REVIEW, PaperStatus.FAILED) else None,
        error=latest_error,
    )


@router.post("/papers/{paper_id}/reprocess")
@limiter.limit(get_settings().rate_limit_reprocess)
async def reprocess_paper(
    request: Request,
    paper_id: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """Manually trigger reprocessing of an existing paper."""
    paper = await db.get(ExamPaper, paper_id)

    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")

    active_statuses = (
        PaperStatus.VALIDATING,
        PaperStatus.PREPROCESSING,
        PaperStatus.EXTRACTING,
        PaperStatus.ANALYZING,
        PaperStatus.REWRITING,
        PaperStatus.RENDERING,
        PaperStatus.STORING,
    )
    if paper.status in active_statuses:
        raise HTTPException(status_code=400, detail="Paper is already processing")

    # Reset paper state
    paper.status = PaperStatus.QUEUED
    paper.current_stage = "queued"
    paper.stage_progress = 0
    paper.failed_stage = None
    await db.commit()

    # Dispatch Celery or BackgroundTasks
    try:
        from tasks.pipeline_task import process_paper_task
        process_paper_task.delay(paper.id)
        logger.info(f"Dispatched Celery reprocess task for paper {paper_id}")
    except Exception as e:
        logger.warning(f"Celery dispatch failed ({e}); using BackgroundTasks.")
        background_tasks.add_task(run_pipeline_for_paper, paper.id)

    return {
        "message": "Reprocessing started",
        "paper_id": paper_id,
        "polling_url": f"/api/papers/{paper_id}/status",
    }
