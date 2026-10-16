"""ExamPaper Refine - Papers Router."""

import mimetypes
import logging
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.database import get_db
from app.dependencies.auth import AuthUser, get_current_user, get_optional_user
from app.middleware.rate_limit import limiter
from app.models import (
    DerivativeType,
    ExamPaper,
    PaperDetail,
    PaperInteractionRequest,
    PaperReport,
    PaperReportRequest,
    PaperStatus,
    PaperSummary,
    Question,
)
from storage.local import storage

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/papers", response_model=list[PaperSummary])
async def list_papers(
    university: Optional[str] = None,
    course_code: Optional[str] = None,
    year: Optional[int] = None,
    status: Optional[str] = None,
    search_query: Optional[str] = Query(None, alias="search", max_length=300),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    user: Optional[AuthUser] = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
):
    """List and filter exam papers. Rejected papers are hidden from non-admin users."""
    stmt = select(ExamPaper).order_by(ExamPaper.created_at.desc())

    if search_query and search_query.strip():
        stmt = stmt.options(selectinload(ExamPaper.questions))

    is_admin = user and user.is_admin

    # Always hide REJECTED and FAILED papers from non-admins
    if not is_admin:
        stmt = stmt.where(ExamPaper.status != PaperStatus.REJECTED)
        if not status:
            stmt = stmt.where(ExamPaper.status != PaperStatus.FAILED)
        elif status.lower() == PaperStatus.REJECTED.value.lower():
            raise HTTPException(status_code=403, detail="Permission denied")
        else:
            stmt = stmt.where(ExamPaper.status == status)
    else:
        if status:
            stmt = stmt.where(ExamPaper.status == status)
        
    if search_query and search_query.strip():
        # Fetch a bounded candidate set, then rank in Python. This keeps the
        # implementation portable across SQLite and PostgreSQL while allowing
        # title, metadata, full extracted text, and saved popularity to work
        # together in one relevance score.
        stmt = stmt.limit(5000)
        result = await db.execute(stmt)
        candidates = list(result.scalars().unique().all())
        matched = [paper for paper in candidates if _search_has_match(paper, search_query)]
        logger.info("paper search %r matched %s from %s candidates", search_query, [paper.id for paper in matched], len(candidates))
        ranked = sorted(matched, key=lambda paper: _search_score(paper, search_query), reverse=True)
        return ranked[skip : skip + limit]

    stmt = stmt.offset(skip).limit(limit)
    result = await db.execute(stmt)
    return result.scalars().all()


def _search_score(paper: ExamPaper, raw_query: str) -> float:
    """Rank a paper using phrase/term relevance plus library engagement."""
    query = " ".join(raw_query.lower().split())
    tokens = [token for token in re.findall(r"[\w-]+", query) if len(token) > 1]
    title = (paper.title or "").lower()
    metadata = " ".join(
        str(value or "")
        for value in (
            paper.original_filename,
            paper.course_code,
            paper.course_name,
            paper.university,
            paper.department,
            paper.study_year,
            paper.semester,
            paper.exam_type,
            paper.description,
        )
    ).lower()
    body = (paper.extracted_text or "").lower()
    questions = " ".join((question.text or "") for question in (paper.questions or [])).lower()
    searchable_body = f"{body} {questions}"
    score = 0.0

    if query in title:
        score += 120
    if query in metadata:
        score += 55
    if query in searchable_body:
        score += 45

    for token in tokens:
        if token in title:
            score += 34
        if token in metadata:
            score += 18
        if token in searchable_body:
            score += 10

    # Save count is an explicit signal that people found the document useful;
    # log scaling prevents one popular paper from drowning out relevance.
    score += math.log1p(max(0, paper.save_count or 0)) * 7
    score += math.log1p(max(0, paper.like_count or 0)) * 2
    score += max(0.0, min(1.0, float(paper.quality_score or 0))) * 8
    return score


def _search_has_match(paper: ExamPaper, raw_query: str) -> bool:
    """Exclude unrelated documents before popularity can influence ranking."""
    query = " ".join(raw_query.lower().split())
    tokens = [token for token in re.findall(r"[\w-]+", query) if len(token) > 1]
    searchable = " ".join(
        str(value or "")
        for value in (
            paper.title,
            paper.original_filename,
            paper.course_code,
            paper.course_name,
            paper.university,
            paper.department,
            paper.study_year,
            paper.semester,
            paper.exam_type,
            paper.description,
            paper.extracted_text,
            " ".join((question.text or "") for question in (paper.questions or [])),
        )
    ).lower()
    return bool(query and query in searchable) or any(token in searchable for token in tokens)


@router.post("/papers/{paper_id}/interactions")
async def record_interaction(
    paper_id: str,
    payload: PaperInteractionRequest,
    db: AsyncSession = Depends(get_db),
):
    """Record anonymous library engagement used by ranking and discovery."""
    paper = await db.get(ExamPaper, paper_id)
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")

    if payload.kind == "save":
        paper.save_count = (paper.save_count or 0) + 1
    elif payload.kind == "unsave":
        paper.save_count = max(0, (paper.save_count or 0) - 1)
    elif payload.kind == "like":
        paper.like_count = (paper.like_count or 0) + 1
    else:
        paper.like_count = max(0, (paper.like_count or 0) - 1)

    await db.commit()
    return {"paper_id": paper.id, "save_count": paper.save_count, "like_count": paper.like_count}


@router.post("/papers/{paper_id}/reports", status_code=201)
@limiter.limit("5/minute")
async def report_paper(
    request: Request,
    paper_id: str,
    payload: PaperReportRequest,
    background_tasks: BackgroundTasks,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a moderation report. Requires sign-in with per-user daily quota."""
    paper = await db.get(ExamPaper, paper_id)
    if not paper or paper.status == PaperStatus.REJECTED:
        raise HTTPException(status_code=404, detail="Paper not found")

    # Enforce daily quota per user (max 5 reports/day) to prevent AI credit exhaustion
    MAX_REPORTS_PER_USER_DAY = 5
    settings = get_settings()
    try:
        import redis as redis_lib

        redis_client = redis_lib.Redis.from_url(
            settings.redis_url, decode_responses=True, socket_connect_timeout=2
        )
        today = datetime.now(timezone.utc).strftime("%Y%m%d")
        quota_key = f"paperflow:report_quota:{user.id}:{today}"
        count = int(redis_client.get(quota_key) or 0)
        if count >= MAX_REPORTS_PER_USER_DAY and not user.is_admin:
            raise HTTPException(
                status_code=429,
                detail=f"Daily report limit reached ({MAX_REPORTS_PER_USER_DAY} reports/day). Please try again tomorrow.",
            )
        redis_client.incr(quota_key)
        redis_client.expire(quota_key, 172800)  # 48h TTL
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning(f"Redis report quota check failed: {exc}")

    report = PaperReport(
        exam_paper_id=paper.id,
        reason=payload.reason.strip(),
        details=payload.details.strip() if payload.details else None,
    )
    db.add(report)
    await db.commit()

    _dispatch_report_task(report.id, background_tasks)
    return {
        "id": report.id,
        "status": report.status,
        "message": (
            "Report received. The document will be regenerated with your feedback."
            if payload.reason.strip().lower() == "inaccurate metadata or content"
            else "Report received for moderation review."
        ),
    }


def _dispatch_report_task(report_id: str, background_tasks: BackgroundTasks) -> None:
    """Send the report to the Celery worker, falling back to background tasks."""
    try:
        from tasks.report_task import handle_report_task

        handle_report_task.delay(report_id)
    except Exception as exc:
        logger.warning(f"Celery dispatch failed for report {report_id} ({exc}); using BackgroundTasks.")
        background_tasks.add_task(_run_report_inline, report_id)


def _run_report_inline(report_id: str) -> None:
    import asyncio

    from services.report_handler import handle_report

    asyncio.run(handle_report(report_id))


@router.get("/papers/mine", response_model=list[PaperSummary])
async def list_my_papers(
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Papers uploaded by the signed-in user, newest first."""
    result = await db.execute(
        select(ExamPaper)
        .where(ExamPaper.uploader_id == user.id)
        .order_by(ExamPaper.created_at.desc())
        .limit(500)
    )
    return result.scalars().all()


@router.get("/papers/{paper_id}", response_model=PaperDetail)
async def get_paper(
    paper_id: str,
    user: Optional[AuthUser] = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
):
    """Get full details of a specific paper."""
    stmt = (
        select(ExamPaper)
        .where(ExamPaper.id == paper_id)
        .options(
            selectinload(ExamPaper.questions).selectinload(Question.sub_questions),
            selectinload(ExamPaper.derivatives),
            selectinload(ExamPaper.processing_logs)
        )
    )
    
    result = await db.execute(stmt)
    paper = result.scalars().first()
    
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")

    if paper.status == PaperStatus.REJECTED and (not user or not user.is_admin):
        raise HTTPException(status_code=404, detail="Paper not found")
        
    # Top-level questions only (children are fetched via sub_questions relationship)
    paper.questions = [q for q in paper.questions if not q.parent_question_id]

    # Sort questions and logs
    paper.questions.sort(key=lambda q: q.normalized_order or 0)
    paper.processing_logs.sort(key=lambda log: log.started_at or log.id)
        
    return paper


def _download_filename(
    paper: ExamPaper, indicator: str, extension: str, fallback: Optional[str] = None
) -> str:
    """Build a human-readable download name from the paper title.

    Produces ``<Title>_<indicator>.<ext>`` (e.g. ``Data_Structures_Final_Exam_refined.pdf``)
    with characters that are unsafe in filenames stripped out.
    """
    source = (paper.title or "").strip() or (fallback or "").strip() or f"paper_{paper.id[:8]}"
    base = re.sub(r"[^\w\s-]", "", source).strip()
    base = re.sub(r"\s+", "_", base)[:120].strip("._-") or f"paper_{paper.id[:8]}"
    return f"{base}_{indicator}{extension}"


@router.get("/papers/{paper_id}/download/original")
async def download_original(
    paper_id: str,
    db: AsyncSession = Depends(get_db),
    user: AuthUser = Depends(get_current_user),
):
    """Download the original uploaded file. Requires sign-in."""
    paper = await db.get(ExamPaper, paper_id)
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")

    file_path = storage.get_original_path(paper.original_file_path)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Original file missing on disk")

    extension = Path(file_path.name).suffix or ".bin"
    return FileResponse(
        path=file_path,
        filename=_download_filename(paper, "original", extension, fallback=paper.original_filename),
        media_type="application/octet-stream"
    )


@router.get("/papers/{paper_id}/view/original")
async def view_original(
    paper_id: str,
    db: AsyncSession = Depends(get_db),
    user: AuthUser = Depends(get_current_user),
):
    """Serve the original upload inline for the document reader. Requires sign-in."""
    paper = await db.get(ExamPaper, paper_id)
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
    file_path = storage.get_original_path(paper.original_file_path)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Original file missing on disk")
    return FileResponse(
        path=file_path,
        media_type=mimetypes.guess_type(file_path.name)[0] or "application/octet-stream",
        headers={"Content-Disposition": f'inline; filename="{paper.original_filename}"'},
    )


@router.get("/papers/{paper_id}/preview")
async def preview_paper(paper_id: str, db: AsyncSession = Depends(get_db)):
    """Return a rasterized first-page PNG thumbnail for a library card.

    A final PDF is preferred when processing produced one. Otherwise the original
    upload is used. PDFs and images are rasterized/returned as PNG images only.
    Raw unauthenticated files are never streamed.
    """
    stmt = (
        select(ExamPaper)
        .where(ExamPaper.id == paper_id)
        .options(selectinload(ExamPaper.derivatives))
    )
    result = await db.execute(stmt)
    paper = result.scalars().first()

    if not paper or paper.status == PaperStatus.REJECTED:
        raise HTTPException(status_code=404, detail="Paper not found")

    preview_path = None
    pdfs = [d for d in paper.derivatives if d.derivative_type == DerivativeType.FINAL_PDF]
    if pdfs:
        candidate = storage.get_derivative_path(max(pdfs, key=lambda d: d.version).file_path)
        if candidate.exists():
            preview_path = candidate

    if preview_path is None:
        original_path = storage.get_original_path(paper.original_file_path)
        if not original_path.exists():
            raise HTTPException(status_code=404, detail="Preview source missing on disk")
        preview_path = original_path

    if preview_path.suffix.lower() == ".pdf":
        try:
            try:
                import fitz
            except ImportError:
                import pymupdf as fitz

            with fitz.open(str(preview_path)) as document:
                if document.page_count:
                    page = document.load_page(0)
                    pixmap = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False)
                    return Response(
                        content=pixmap.tobytes("png"),
                        media_type="image/png",
                        headers={"Cache-Control": "public, max-age=300"},
                    )
        except Exception as exc:
            logger.warning(f"Failed to rasterize PDF preview for {paper_id}: {exc}")

    # For image uploads, return image safely
    if preview_path.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff", ".tif"):
        try:
            from PIL import Image
            import io

            with Image.open(preview_path) as img:
                img.thumbnail((800, 1000))
                buf = io.BytesIO()
                img.save(buf, format="PNG")
                return Response(
                    content=buf.getvalue(),
                    media_type="image/png",
                    headers={"Cache-Control": "public, max-age=300"},
                )
        except Exception as exc:
            logger.warning(f"Failed to generate image preview for {paper_id}: {exc}")

    raise HTTPException(status_code=404, detail="Preview thumbnail not available")


@router.get("/papers/{paper_id}/download/refined")
async def download_refined(
    paper_id: str,
    db: AsyncSession = Depends(get_db),
    user: AuthUser = Depends(get_current_user),
):
    """Download the final refined PDF (if available). Requires sign-in."""
    stmt = (
        select(ExamPaper)
        .where(ExamPaper.id == paper_id)
        .options(selectinload(ExamPaper.derivatives))
    )
    result = await db.execute(stmt)
    paper = result.scalars().first()
    
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
        
    # Find the latest final PDF derivative
    pdfs = [d for d in paper.derivatives if d.derivative_type == DerivativeType.FINAL_PDF]
    if not pdfs:
        raise HTTPException(status_code=404, detail="Refined PDF not ready yet")
        
    latest_pdf = sorted(pdfs, key=lambda d: d.version, reverse=True)[0]
    file_path = storage.get_derivative_path(latest_pdf.file_path)
    
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="PDF file missing on disk")

    return FileResponse(
        path=file_path,
        filename=_download_filename(paper, "refined", ".pdf"),
        media_type="application/pdf"
    )


@router.get("/papers/{paper_id}/view/refined")
async def view_refined(
    paper_id: str,
    db: AsyncSession = Depends(get_db),
    user: AuthUser = Depends(get_current_user),
):
    """Serve the refined PDF inline; downloading remains an explicit action. Requires sign-in."""
    stmt = (
        select(ExamPaper)
        .where(ExamPaper.id == paper_id)
        .options(selectinload(ExamPaper.derivatives))
    )
    result = await db.execute(stmt)
    paper = result.scalars().first()
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
    pdfs = [d for d in paper.derivatives if d.derivative_type == DerivativeType.FINAL_PDF]
    if not pdfs:
        raise HTTPException(status_code=404, detail="Refined PDF not ready yet")
    latest_pdf = sorted(pdfs, key=lambda d: d.version, reverse=True)[0]
    file_path = storage.get_derivative_path(latest_pdf.file_path)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="PDF file missing on disk")
    return FileResponse(
        path=file_path,
        filename=_download_filename(paper, "refined", ".pdf"),
        media_type="application/pdf",
        content_disposition_type="inline",
    )
