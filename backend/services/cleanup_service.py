"""ExamPaper Refine - Stale process cleanup.

The library is an archive: papers, derivatives and originals are NEVER
deleted here. This service only reaps *processes* that have been stuck in
an active/processing state for longer than the configured window — whether
they started long ago and hung mid-pipeline, or finished but never got
their final status written — by marking them FAILED so the UI stops
polling/spinning forever.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.config import get_settings
from app.database import async_session
from app.models import ExamPaper, PaperStatus, ProcessingStage, StageStatus

logger = logging.getLogger(__name__)

# How often the cleanup sweep runs.
CHECK_INTERVAL_SECONDS = 6 * 60 * 60  # every 6 hours

# Statuses that represent a process still considered "in flight". Anything
# terminal (completed / published / needs_review / rejected / failed) is
# left untouched.
ACTIVE_STATUSES = {
    PaperStatus.QUEUED,
    PaperStatus.UPLOADED,
    PaperStatus.VALIDATING,
    PaperStatus.PREPROCESSING,
    PaperStatus.EXTRACTING,
    PaperStatus.ANALYZING,
    PaperStatus.REWRITING,
    PaperStatus.RENDERING,
    PaperStatus.STORING,
}


async def cleanup_stale_processes() -> dict:
    """Fail every paper whose process has been active past the cutoff.

    Only DB status fields change; no files or rows are removed.

    Returns:
        Stats dict: reaped paper ids and errors.
    """
    settings = get_settings()
    cutoff = datetime.now(timezone.utc) - timedelta(days=settings.stale_process_days)
    stats: dict = {"reaped_papers": [], "errors": []}

    async with async_session() as db:
        stale_papers = (
            await db.execute(
                select(ExamPaper).where(
                    ExamPaper.status.in_(list(ACTIVE_STATUSES)),
                    ExamPaper.updated_at < cutoff,
                )
            )
        ).scalars().all()

        for paper in stale_papers:
            try:
                previous_stage = paper.current_stage
                paper.status = PaperStatus.FAILED
                paper.failed_stage = previous_stage
                if previous_stage:
                    paper.current_stage = None

                # Record why it died so the UI/history can show it.
                try:
                    from pipeline.orchestrator import _log_stage

                    stage_enum = (
                        ProcessingStage(previous_stage) if previous_stage else ProcessingStage.RENDER
                    )
                    await _log_stage(
                        db,
                        paper.id,
                        stage_enum,
                        StageStatus.FAILED,
                        error_details=(
                            f"Stale process automatically marked failed after "
                            f"{settings.stale_process_days} day(s) without progress."
                        ),
                    )
                except ValueError:
                    pass  # unknown stage string; status flip alone is enough

                stats["reaped_papers"].append(paper.id)
            except Exception as e:
                logger.exception(f"Stale-process cleanup failed for paper {paper.id}")
                stats["errors"].append({"paper_id": paper.id, "error": str(e)})

        await db.commit()

    return stats


async def stale_process_cleanup_loop() -> None:
    """Background loop sweeping stale processes on an interval."""
    settings = get_settings()
    if settings.stale_process_days <= 0:
        logger.info("Stale-process cleanup disabled (stale_process_days <= 0)")
        return

    logger.info(
        f"Stale-process cleanup active: failing processes stuck > "
        f"{settings.stale_process_days} day(s), sweep every "
        f"{CHECK_INTERVAL_SECONDS // 3600}h"
    )

    while True:
        try:
            stats = await cleanup_stale_processes()
            if stats["reaped_papers"]:
                logger.info(
                    f"Marked {len(stats['reaped_papers'])} stale process(es) "
                    f"as failed: {stats['reaped_papers']} "
                    f"(errors: {len(stats['errors'])})"
                )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Stale-process sweep failed")

        await asyncio.sleep(CHECK_INTERVAL_SECONDS)
