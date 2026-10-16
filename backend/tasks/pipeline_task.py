"""ExamPaper Refine - Celery Pipeline Task.

Defines the asynchronous Celery task that executes the paper refinement pipeline
with exponential backoff retries (30s -> 60s -> 120s).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from celery import Task
from worker import celery_app
from pipeline.orchestrator import run_pipeline_for_paper

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class PipelineTask(Task):
    """Custom Celery Task with automatic retry tracking."""

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        paper_id = args[0] if args else "unknown"
        logger.error(
            f"Celery task {task_id} failed for paper {paper_id}: {exc}",
            exc_info=einfo,
        )

    def on_retry(self, exc, task_id, args, kwargs, einfo):
        paper_id = args[0] if args else "unknown"
        logger.warning(
            f"Celery task {task_id} retrying for paper {paper_id} "
            f"(attempt {self.request.retries + 1}/3): {exc}"
        )


@celery_app.task(
    bind=True,
    base=PipelineTask,
    name="tasks.process_paper_task",
    max_retries=3,
    default_retry_delay=30,      # 30s base delay
    retry_backoff=True,          # 30s -> 60s -> 120s exponential backoff
    retry_backoff_max=120,
    retry_jitter=True,
    acks_late=True,
)
def process_paper_task(self, paper_id: str, rewrite_feedback: str | None = None):
    """Celery task entry point to process an exam paper asynchronously.

    ``rewrite_feedback`` carries user correction requests (from accuracy
    reports) into the AI rewrite prompt; the run then stores a new version.
    """
    logger.info(
        f"Starting Celery pipeline task for paper {paper_id} "
        f"(retry #{self.request.retries}, feedback={'yes' if rewrite_feedback else 'no'})"
    )

    try:
        # Run the async pipeline in an event loop
        result = asyncio.run(run_pipeline_for_paper(paper_id, rewrite_feedback=rewrite_feedback))

        if result.status == "failed":
            # If the pipeline failed due to a potentially retryable error, raise to trigger Celery retry
            error_msg = result.error or "Unknown pipeline failure"
            # Non-retryable errors
            if "not found" in error_msg.lower() or "missing" in error_msg.lower():
                logger.error(f"Non-retryable failure for paper {paper_id}: {error_msg}")
                return {"paper_id": paper_id, "status": "failed", "error": error_msg}

            # Retry with exponential backoff if within retry limit
            raise RuntimeError(f"Pipeline error: {error_msg}")

        logger.info(f"Completed Celery pipeline task for paper {paper_id}")
        return {
            "paper_id": paper_id,
            "status": "completed",
            "time_s": result.total_processing_time_seconds,
        }

    except Exception as exc:
        logger.exception(f"Exception during processing of paper {paper_id}")
        # Retry with exponential backoff if retries remaining
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc)
        
        # Max retries exhausted
        logger.error(f"Max retries exhausted (3/3) for paper {paper_id}")
        return {"paper_id": paper_id, "status": "failed", "error": str(exc)}
