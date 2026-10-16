"""ExamPaper Refine - Celery Worker Configuration."""

import asyncio
from celery import Celery
from celery.signals import worker_ready
from sqlalchemy import select
from app.config import get_settings
from app.database import async_session
from app.models import ExamPaper, PaperStatus

settings = get_settings()

celery_app = Celery(
    "exampaper_worker",
    broker=settings.redis_url,
    backend=settings.celery_result_backend,
    include=["tasks.pipeline_task", "tasks.report_task"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    # Multi-page scans can take several minutes before AI extraction even
    # begins. Give PDF jobs enough room to finish instead of killing them at
    # the old five-minute limit.
    task_time_limit=3600,
    task_soft_time_limit=3300,
    worker_prefetch_multiplier=1,
    task_acks_late=True,
)


async def _find_needs_review_papers() -> list[str]:
    async with async_session() as session:
        result = await session.execute(
            select(ExamPaper.id).where(ExamPaper.status == PaperStatus.NEEDS_REVIEW)
        )
        paper_ids = list(result.scalars().all())
        if paper_ids:
            papers = (await session.execute(select(ExamPaper).where(ExamPaper.id.in_(paper_ids)))).scalars().all()
            for paper in papers:
                paper.status = PaperStatus.QUEUED
                paper.current_stage = "queued"
                paper.stage_progress = 0
                paper.failed_stage = None
            await session.commit()
        return paper_ids


@worker_ready.connect
def enqueue_needs_review_recovery(**_kwargs):
    """Give fallback papers one automatic retry when the worker is available."""
    if not settings.auto_reprocess_needs_review:
        return

    from tasks.pipeline_task import process_paper_task

    paper_ids = asyncio.run(_find_needs_review_papers())
    for paper_id in paper_ids:
        process_paper_task.delay(paper_id)
        print(f"Queued automatic needs-review recovery for paper {paper_id}")

if __name__ == "__main__":
    celery_app.start()
