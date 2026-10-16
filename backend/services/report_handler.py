"""Core report-handling logic shared by the Celery task and the
FastAPI BackgroundTasks fallback.

Two automatic behaviors:
  • "inaccurate metadata or content" → regenerate the document with the
    report's reason+details injected into the AI rewrite prompt (new version).
  • "abuse or request for removal" → AI adjudicates; clear violations set the
    paper to REJECTED (hidden from the catalog), everything else is flagged
    for human review.
"""

from __future__ import annotations

import logging

from sqlalchemy import select

from app.config import get_settings
from app.models import ExamPaper, PaperReport, PaperStatus
from services.report_adjudicator import adjudicate_removal

logger = logging.getLogger(__name__)

REMOVAL_REASON = "abuse or request for removal"
INACCURATE_REASON = "inaccurate metadata or content"


async def handle_report(report_id: str) -> dict:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    engine = create_async_engine(
        get_settings().resolved_database_url, poolclass=NullPool, future=True
    )
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with session_factory() as db:
            return await _handle_with_session(db, report_id)
    finally:
        await engine.dispose()


async def _handle_with_session(db, report_id: str) -> dict:
    report = await db.get(PaperReport, report_id)
    if not report:
        return {"status": "missing"}
    paper = await db.get(ExamPaper, report.exam_paper_id)
    if not paper:
        report.status = "rejected"
        report.review_note = "Paper no longer exists."
        await db.commit()
        return {"status": "paper_missing"}

    feedback = (
        f"Report reason: {report.reason}\n"
        f"Report details: {report.details or '(none provided)'}"
    )

    if report.reason.strip().lower() == REMOVAL_REASON:
        report.status = "reviewing"
        await db.commit()

        summary = (
            f"Title: {paper.title or paper.original_filename}\n"
            f"Description: {paper.description or '(none)'}\n"
            f"University: {paper.university or '(unknown)'}\n"
            f"Course: {paper.course_code or ''} {paper.course_name or ''}\n"
            f"Type: {paper.exam_type or paper.document_type or 'unknown'}\n"
            f"Content excerpt:\n{(paper.extracted_text or '')[:4000]}"
        )
        verdict = adjudicate_removal(report.reason, report.details, summary)

        if verdict["decision"] == "remove" and verdict["confidence"] >= 0.7:
            paper.status = PaperStatus.REJECTED
            report.status = "resolved"
            report.review_note = f"AI adjudication: REMOVED. {verdict['note']}"
        elif verdict["decision"] == "keep":
            report.status = "resolved"
            report.review_note = f"AI adjudication: KEPT. {verdict['note']}"
        else:
            report.status = "needs_human"
            report.review_note = f"AI adjudication: HUMAN REVIEW. {verdict['note']}"
        await db.commit()
        logger.info(
            f"Report {report_id} adjudicated: {verdict['decision']} "
            f"(confidence={verdict['confidence']:.2f})"
        )
        return {"status": verdict["decision"]}

    # Accuracy (and other) reports → regenerate with the report as feedback.
    # The pipeline resolves the report when the new version succeeds.
    report.status = "regenerating"
    await db.commit()

    from tasks.pipeline_task import process_paper_task

    process_paper_task.delay(paper.id, rewrite_feedback=feedback)
    logger.info(f"Report {report_id} queued regeneration for paper {paper.id}")
    return {"status": "regenerating"}
