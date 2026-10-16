"""Celery task that acts on a freshly submitted report.

Thin wrapper around services.report_handler.handle_report so the same logic
also runs via FastAPI BackgroundTasks when Redis is unavailable.
"""

from __future__ import annotations

import asyncio
import logging

from celery import Task

from worker import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    name="tasks.handle_report_task",
    max_retries=2,
    default_retry_delay=30,
    retry_backoff=True,
)
def handle_report_task(self, report_id: str):
    """Entry point: act on a newly submitted report."""
    logger.info(f"Handling report {report_id}")
    try:
        from services.report_handler import handle_report

        return asyncio.run(handle_report(report_id))
    except Exception as exc:
        logger.exception(f"Report handling failed for {report_id}")
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc)
        return {"status": "failed", "error": str(exc)}
