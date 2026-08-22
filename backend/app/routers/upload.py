"""ExamPaper Refine - Upload Router."""

import hashlib
import io
import json
import logging
import re
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Request, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.middleware.rate_limit import limiter
from app.models import ExamPaper, PaperStatus, UploadResponse
from pipeline.orchestrator import run_pipeline_for_paper
from services.metadata_resolver import resolve_metadata_context
from storage.local import storage

logger = logging.getLogger(__name__)
router = APIRouter()


def _dispatch_processing_task(paper_id: str, background_tasks: BackgroundTasks) -> str:
    """Dispatch the processing job to Celery, falling back to BackgroundTasks if Redis is unavailable."""
    try:
        from tasks.pipeline_task import process_paper_task
        task = process_paper_task.delay(paper_id)
        logger.info(f"Dispatched Celery task {task.id} for paper {paper_id}")
        return f"celery:{task.id}"
    except Exception as e:
        logger.warning(
            f"Celery dispatch failed ({e}); falling back to local BackgroundTasks."
        )
        background_tasks.add_task(run_pipeline_for_paper, paper_id)
        return "local:background_tasks"


@router.post(
    "/upload",
    response_model=UploadResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
@limiter.limit(get_settings().rate_limit_upload)
async def upload_paper(
    request: Request,
    background_tasks: BackgroundTasks,
    file: Optional[UploadFile] = File(None),
    files: list[UploadFile] = File(default=[]),
    title: str = Form(...),
    description: str = Form(...),
    email: Optional[str] = Form(None),
    university: Optional[str] = Form(None),
    university_type: Optional[str] = Form(None),
    study_year: Optional[str] = Form(None),
    department: Optional[str] = Form(None),
    course_code: Optional[str] = Form(None),
    course_name: Optional[str] = Form(None),
    year: Optional[str] = Form(None),
    semester: Optional[str] = Form(None),
    exam_type: Optional[str] = Form(None),
    metadata_json: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
):
    """Upload a new exam paper and queue it for asynchronous processing.

    Returns immediately with HTTP 202 Accepted and a polling URL for status updates.
    """
    settings = get_settings()

    uploads = [upload for upload in (list(files or []) + ([file] if file else [])) if upload.filename]
    if not uploads:
        raise HTTPException(status_code=400, detail="No filename provided")

    title = title.strip()
    description = description.strip()
    if not title:
        raise HTTPException(status_code=400, detail="A document name is required")
    if not description:
        raise HTTPException(status_code=400, detail="A document description is required")

    extensions = [f".{upload.filename.split('.')[-1].lower()}" if "." in upload.filename else "" for upload in uploads]
    if any(ext not in settings.allowed_extensions for ext in extensions):
        raise HTTPException(status_code=400, detail="Unsupported file type. Use PDF, PNG, JPG, TIFF, WEBP, or BMP.")
    if len(uploads) > 1 and any(ext == ".pdf" for ext in extensions):
        raise HTTPException(status_code=400, detail="Upload one PDF or multiple image pages, not a mixture of both.")

    raw_pages = [await upload.read() for upload in uploads]
    if sum(len(page) for page in raw_pages) > settings.max_file_size_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Max size is {settings.max_file_size_mb}MB",
        )

    filename = uploads[0].filename or "paper.pdf"
    if len(uploads) > 1:
        try:
            from PIL import Image
            images = [Image.open(io.BytesIO(page)).convert("RGB") for page in raw_pages]
            pdf_buffer = io.BytesIO()
            images[0].save(pdf_buffer, format="PDF", save_all=True, append_images=images[1:])
            content = pdf_buffer.getvalue()
            filename = f"{filename.rsplit('.', 1)[0]}-pages.pdf"
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Could not combine image pages: {exc}") from exc
    else:
        content = raw_pages[0]

    sha256 = hashlib.sha256(content).hexdigest()

    # Check for duplicates
    result = await db.execute(select(ExamPaper).where(ExamPaper.source_sha256 == sha256))
    existing = result.scalars().first()
    if existing:
        return UploadResponse(
            id=existing.id,
            status=existing.status.value,
            message="File already exists in repository",
            polling_url=f"/api/papers/{existing.id}/status",
        )

    # Preserve the detailed form context exactly as entered. Local aliases and
    # library matches are resolved synchronously; external lookup is deferred
    # to the queued pipeline so upload latency stays predictable.
    try:
        metadata_envelope = json.loads(metadata_json) if metadata_json else {}
        if not isinstance(metadata_envelope, dict):
            raise ValueError("metadata_json must be an object")
    except (json.JSONDecodeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"Invalid metadata JSON: {exc}") from exc

    provided = metadata_envelope.get("provided")
    if not isinstance(provided, dict):
        provided = {}
    provided.update({
        key: value
        for key, value in {
            "title": title,
            "description": description,
            "university": university,
            "university_type": university_type,
            "study_year": study_year,
            "department": department,
            "course_code": course_code,
            "course_name": course_name,
            "year": year,
            "semester": semester,
            "exam_type": exam_type,
        }.items()
        if value is not None and str(value).strip()
    })
    metadata_envelope["provided"] = provided
    uploaded_at = datetime.now(timezone.utc).isoformat()
    metadata_envelope["uploaded_at"] = uploaded_at
    metadata_context = await resolve_metadata_context(db, metadata_envelope, allow_web_lookup=False)
    metadata_context["uploaded_at"] = uploaded_at
    resolved = metadata_context.get("resolved", {})
    year_text = year.strip() if year else None
    year_number = int(year_text) if year_text and re.fullmatch(r"\d{4}", year_text) else None

    # Store original file
    file_key = storage.store_original(io.BytesIO(content), filename, sha256)

    # Create DB record with QUEUED status
    paper = ExamPaper(
        title=title,
        description=description,
        original_filename=filename,
        source_sha256=sha256,
        original_file_path=file_key,
        email=email.strip() if email else None,
        university=resolved.get("university") or (university.strip() if university else None),
        university_type=resolved.get("university_type") or (university_type.strip() if university_type else None),
        study_year=resolved.get("study_year") or (study_year.strip() if study_year else None),
        department=resolved.get("department") or (department.strip() if department else None),
        course_code=resolved.get("course_code") or (course_code.strip() if course_code else None),
        course_name=resolved.get("course_name") or (course_name.strip() if course_name else None),
        year=year_number,
        semester=semester,
        exam_type=exam_type,
        metadata_json=json.dumps(metadata_context, ensure_ascii=False),
        status=PaperStatus.QUEUED,
        current_stage="queued",
        stage_progress=0,
    )
    db.add(paper)
    await db.commit()
    await db.refresh(paper)

    # Dispatch task asynchronously
    _dispatch_processing_task(paper.id, background_tasks)

    return UploadResponse(
        id=paper.id,
        status=paper.status.value,
        message="Upload accepted. Processing has been queued.",
        polling_url=f"/api/papers/{paper.id}/status",
    )
