"""ExamPaper Refine - Papers Router."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models import DerivativeType, ExamPaper, PaperDetail, PaperSummary
from storage.local import storage

router = APIRouter()


@router.get("/papers", response_model=list[PaperSummary])
async def list_papers(
    university: Optional[str] = None,
    course_code: Optional[str] = None,
    year: Optional[int] = None,
    status: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """List and filter exam papers."""
    stmt = select(ExamPaper).order_by(ExamPaper.created_at.desc())
    
    if university:
        stmt = stmt.where(ExamPaper.university.ilike(f"%{university}%"))
    if course_code:
        stmt = stmt.where(ExamPaper.course_code.ilike(f"%{course_code}%"))
    if year:
        stmt = stmt.where(ExamPaper.year == year)
    if status:
        stmt = stmt.where(ExamPaper.status == status)
        
    stmt = stmt.offset(skip).limit(limit)
    
    result = await db.execute(stmt)
    papers = result.scalars().all()
    
    return papers


@router.get("/papers/{paper_id}", response_model=PaperDetail)
async def get_paper(paper_id: str, db: AsyncSession = Depends(get_db)):
    """Get full details of a specific paper."""
    stmt = (
        select(ExamPaper)
        .where(ExamPaper.id == paper_id)
        .options(
            selectinload(ExamPaper.questions).selectinload("sub_questions"),
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
