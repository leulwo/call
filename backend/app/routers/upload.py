"""ExamPaper Refine - Upload Router."""

import asyncio
import hashlib
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.models import ExamPaper, UploadResponse
from pipeline.orchestrator import process_paper
from storage.local import storage

router = APIRouter()


async def _run_pipeline_background(paper_id: str):
    """Run the pipeline in a background task (Phase 0)."""
    # Create a fresh DB session for the background task
    from app.database import async_session
    async with async_session() as db:
        await process_paper(db, paper_id)


@router.post("/upload", response_model=UploadResponse)
async def upload_paper(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    university: Optional[str] = Form(None),
    course_code: Optional[str] = Form(None),
    course_name: Optional[str] = Form(None),
    year: Optional[int] = Form(None),
    semester: Optional[str] = Form(None),
    exam_type: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
):
    """Upload a new exam paper and start processing it."""
    settings = get_settings()
    
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    # Validate extension
    ext = f".{file.filename.split('.')[-1].lower()}" if "." in file.filename else ""
    if ext not in settings.allowed_extensions:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {ext}")

    # Read and hash file
    content = await file.read()
    if len(content) > settings.max_file_size_bytes:
        raise HTTPException(
            status_code=413, 
            detail=f"File too large. Max size is {settings.max_file_size_mb}MB"
        )
        
    sha256 = hashlib.sha256(content).hexdigest()
    await file.seek(0)
    
    # Check for duplicates
    result = await db.execute(select(ExamPaper).where(ExamPaper.source_sha256 == sha256))
    existing = result.scalars().first()
    if existing:
        return UploadResponse(
            id=existing.id,
            status=existing.status.value,
            message="File already exists"
        )

    # Store original file
    file_key = storage.store_original(file.file, file.filename, sha256)
    
    # Create DB record
    paper = ExamPaper(
        original_filename=file.filename,
        source_sha256=sha256,
        original_file_path=file_key,
        university=university,
        course_code=course_code,
        course_name=course_name,
        year=year,
        semester=semester,
        exam_type=exam_type,
    )
    db.add(paper)
    await db.commit()
    await db.refresh(paper)
    
    # Start processing pipeline in background
    background_tasks.add_task(_run_pipeline_background, paper.id)
    
    return UploadResponse(
        id=paper.id,
        status=paper.status.value,
        message="Upload successful, processing started"
    )
