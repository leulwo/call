"""ExamPaper Refine - Papers Router."""

import mimetypes
import logging
import math
import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
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
    db: AsyncSession = Depends(get_db),
):
    """List and filter exam papers."""
    stmt = select(ExamPaper).order_by(ExamPaper.created_at.desc())

    if search_query and search_query.strip():
        # Questions are loaded as a fallback for older papers uploaded before
        # extracted_text was persisted by the pipeline.
        stmt = stmt.options(selectinload(ExamPaper.questions))

    # Failed processing attempts are still available by direct URL for review,
    # but they should not appear as usable library documents or broken previews.
    if not status:
        stmt = stmt.where(ExamPaper.status != PaperStatus.FAILED)
    
    if university:
        stmt = stmt.where(ExamPaper.university.ilike(f"%{university}%"))
    if course_code:
        stmt = stmt.where(ExamPaper.course_code.ilike(f"%{course_code}%"))
    if year:
        stmt = stmt.where(ExamPaper.year == year)
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
async def report_paper(
    paper_id: str,
    payload: PaperReportRequest,
    db: AsyncSession = Depends(get_db),
):
    """Create a moderation report without exposing direct destructive deletion."""
    paper = await db.get(ExamPaper, paper_id)
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
    report = PaperReport(
        exam_paper_id=paper.id,
        reason=payload.reason.strip(),
        details=payload.details.strip() if payload.details else None,
    )
    db.add(report)
    await db.commit()
    return {"id": report.id, "status": report.status, "message": "Report received for review."}


@router.get("/papers/{paper_id}", response_model=PaperDetail)
async def get_paper(paper_id: str, db: AsyncSession = Depends(get_db)):
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
        
    # Top-level questions only (children are fetched via sub_questions relationship)
    paper.questions = [q for q in paper.questions if not q.parent_question_id]

    # Sort questions and logs
    paper.questions.sort(key=lambda q: q.normalized_order or 0)
    paper.processing_logs.sort(key=lambda log: log.started_at or log.id)
        
    return paper


@router.get("/papers/{paper_id}/download/original")
async def download_original(paper_id: str, db: AsyncSession = Depends(get_db)):
    """Download the original uploaded file."""
    paper = await db.get(ExamPaper, paper_id)
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
        
    file_path = storage.get_original_path(paper.original_file_path)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Original file missing on disk")
        
    return FileResponse(
        path=file_path,
        filename=paper.original_filename,
        media_type="application/octet-stream"
    )


@router.get("/papers/{paper_id}/view/original")
async def view_original(paper_id: str, db: AsyncSession = Depends(get_db)):
    """Serve the original upload inline for the document reader."""
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
    """Return a browser-friendly first-page preview for a library card.

    A final PDF is preferred when processing produced one. Otherwise the original
    upload is used. PDFs are rasterized to PNG so the library can show the actual
    document page instead of a decorative CSS cover.
    """
    stmt = (
        select(ExamPaper)
        .where(ExamPaper.id == paper_id)
        .options(selectinload(ExamPaper.derivatives))
    )
    result = await db.execute(stmt)
    paper = result.scalars().first()

    if not paper:
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
        except Exception:
            # A malformed or partially uploaded PDF can still be opened from the
            # document page; keep the preview endpoint graceful in that case.
            pass

    media_type = mimetypes.guess_type(preview_path.name)[0] or "application/octet-stream"
    return FileResponse(
        path=preview_path,
        media_type=media_type,
        headers={"Cache-Control": "public, max-age=300"},
    )


@router.get("/papers/{paper_id}/download/refined")
async def download_refined(paper_id: str, db: AsyncSession = Depends(get_db)):
    """Download the final refined PDF (if available)."""
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
        filename=f"refined_{paper_id}.pdf",
        media_type="application/pdf"
    )


@router.get("/papers/{paper_id}/view/refined")
async def view_refined(paper_id: str, db: AsyncSession = Depends(get_db)):
    """Serve the refined PDF inline; downloading remains an explicit action."""
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
        filename=f"refined_{paper_id}.pdf",
        media_type="application/pdf",
        content_disposition_type="inline",
    )
