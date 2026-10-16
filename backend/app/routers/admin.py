"""Admin/moderation endpoints for the report workflow.

Not linked in the public UI — the owner reaches it at /admin (frontend) and
/api/reports here. Kept simple until roles exist.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.auth import AuthUser, get_admin_user
from app.models import ExamPaper, PaperReport, PaperStatus

logger = logging.getLogger(__name__)
router = APIRouter()

VALID_STATUSES = {"open", "reviewing", "regenerating", "needs_human", "resolved", "rejected"}


def _serialize(report: PaperReport, paper: Optional[ExamPaper]) -> dict:
    return {
        "id": report.id,
        "paper_id": report.exam_paper_id,
        "paper_title": (paper.title or paper.original_filename) if paper else "(deleted)",
        "paper_status": paper.status.value if paper else None,
        "reason": report.reason,
        "details": report.details,
        "status": report.status,
        "review_note": report.review_note,
        "created_at": report.created_at.isoformat() if report.created_at else None,
    }


@router.get("/reports")
async def list_reports(
    status_filter: Optional[str] = Query(None, alias="status"),
    limit: int = Query(100, ge=1, le=500),
    admin: AuthUser = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """List reports, newest first. Optionally filter by status. Requires admin privileges."""
    stmt = select(PaperReport, ExamPaper).join(
        ExamPaper, ExamPaper.id == PaperReport.exam_paper_id, isouter=True
    ).order_by(PaperReport.created_at.desc()).limit(limit)
    if status_filter:
        if status_filter not in VALID_STATUSES:
            raise HTTPException(status_code=400, detail=f"status must be one of {sorted(VALID_STATUSES)}")
        stmt = stmt.where(PaperReport.status == status_filter)
    result = await db.execute(stmt)
    return [_serialize(report, paper) for report, paper in result.all()]


@router.get("/reports/{report_id}")
async def get_report(
    report_id: str,
    admin: AuthUser = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Fetch report details by ID. Requires admin privileges."""
    report = await db.get(PaperReport, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    paper = await db.get(ExamPaper, report.exam_paper_id)
    return _serialize(report, paper)


class ReportStatusUpdate(BaseModel):
    status: str = Field(min_length=3, max_length=30)
    note: Optional[str] = Field(default=None, max_length=2000)


@router.patch("/reports/{report_id}/status")
async def update_report_status(
    report_id: str,
    payload: ReportStatusUpdate,
    admin: AuthUser = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Manually move a report through the workflow (resolve, reject, reopen...). Requires admin."""
    status_value = payload.status.strip().lower()
    if status_value not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail=f"status must be one of {sorted(VALID_STATUSES)}")
    report = await db.get(PaperReport, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    report.status = status_value
    if payload.note is not None:
        report.review_note = payload.note.strip()[:2000] or None
    await db.commit()
    return {"id": report.id, "status": report.status, "review_note": report.review_note}


@router.post("/reports/{report_id}/adjudicate")
async def adjudicate_report(
    report_id: str,
    background_tasks: BackgroundTasks,
    admin: AuthUser = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Re-run AI handling for a report. Requires admin."""
    report = await db.get(PaperReport, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    from app.routers.papers import _dispatch_report_task

    _dispatch_report_task(report.id, background_tasks)
    return {"id": report.id, "message": "Report re-queued for AI handling."}


@router.post("/reports/{report_id}/remove-paper")
async def remove_reported_paper(
    report_id: str,
    admin: AuthUser = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Manually hide the reported paper from the catalog (status=rejected). Requires admin."""
    report = await db.get(PaperReport, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    paper = await db.get(ExamPaper, report.exam_paper_id)
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
    paper.status = PaperStatus.REJECTED
    report.status = "resolved"
    report.review_note = (
        f"{(report.review_note or '')} [Manual removal at "
        f"{datetime.now(timezone.utc).isoformat()}]".strip()
    )
    await db.commit()
    return {"paper_id": paper.id, "paper_status": paper.status.value}
