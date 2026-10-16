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
from app.dependencies.auth import AuthUser, get_current_user
from app.middleware.rate_limit import limit as rate_limit
from app.models import ExamPaper, PaperStatus, UploadResponse
from pipeline.orchestrator import run_pipeline_for_paper
from services.metadata_resolver import resolve_metadata_context
from services.normalizer import (
    normalize_course_code,
    normalize_exam_type,
    normalize_semester,
    normalize_study_year,
)
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
@rate_limit(get_settings().rate_limit_upload)
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
    needs_refinement: bool = Form(True),
    metadata_json: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
    user: AuthUser = Depends(get_current_user),
):
    """Upload a new exam paper and queue it for asynchronous processing.

    Requires a signed-in user (Supabase Auth). Returns immediately with HTTP
    202 Accepted and a polling URL for status updates.

    When ``needs_refinement`` is false the document is accepted as-is: it skips
    the AI pipeline entirely and is published immediately. Refinement uploads
    are limited to 30 pages per document and 90 refined pages per day per IP.
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

    # ── Validate Magic Bytes ──────────────────────────────────────────────
    def _validate_magic_bytes(fname: str, blob: bytes) -> None:
        ext = f".{fname.split('.')[-1].lower()}" if "." in fname else ""
        if ext == ".pdf":
            if not blob.startswith(b"%PDF-"):
                raise HTTPException(status_code=400, detail=f"File '{fname}' is not a valid PDF document.")
        elif ext == ".png":
            if not blob.startswith(b"\x89PNG\r\n\x1a\n"):
                raise HTTPException(status_code=400, detail=f"File '{fname}' is not a valid PNG image.")
        elif ext in (".jpg", ".jpeg"):
            if not blob.startswith(b"\xff\xd8\xff"):
                raise HTTPException(status_code=400, detail=f"File '{fname}' is not a valid JPEG image.")
        elif ext == ".webp":
            if not (blob.startswith(b"RIFF") and len(blob) >= 12 and blob[8:12] == b"WEBP"):
                raise HTTPException(status_code=400, detail=f"File '{fname}' is not a valid WebP image.")
        elif ext in (".tiff", ".tif"):
            if not (blob.startswith(b"II*\x00") or blob.startswith(b"MM\x00*")):
                raise HTTPException(status_code=400, detail=f"File '{fname}' is not a valid TIFF image.")
        elif ext == ".bmp":
            if not blob.startswith(b"BM"):
                raise HTTPException(status_code=400, detail=f"File '{fname}' is not a valid BMP image.")

    for upload, blob in zip(uploads, raw_pages):
        _validate_magic_bytes(upload.filename or "upload", blob)

    # ── Page limits ───────────────────────────────────────────────────────
    MAX_ABSOLUTE_PAGES = 100
    MAX_PAGES_PER_UPLOAD = 30
    MAX_REFINED_PAGES_PER_DAY = 90

    def _count_pdf_pages(blob: bytes) -> int:
        try:
            import fitz

            with fitz.open(stream=blob, filetype="pdf") as doc:
                return len(doc)
        except Exception:
            return 1

    total_doc_pages = len(uploads) if len(uploads) > 1 else _count_pdf_pages(raw_pages[0])
    if total_doc_pages > MAX_ABSOLUTE_PAGES:
        raise HTTPException(
            status_code=400,
            detail=f"Document exceeds the maximum limit of {MAX_ABSOLUTE_PAGES} pages.",
        )

    if needs_refinement:
        page_count = total_doc_pages
        if page_count > MAX_PAGES_PER_UPLOAD:
            raise HTTPException(
                status_code=400,
                detail=f"Refinement is limited to {MAX_PAGES_PER_UPLOAD} pages per document. This file has {page_count} pages. Uncheck 'needs refinement' to publish it as-is.",
            )

        # Daily quota per IP, tracked in Redis (best effort — never block
        # uploads if Redis is unavailable).
        client_ip = request.client.host if request.client else "unknown"
        try:
            import redis as redis_lib

            redis_client = redis_lib.Redis.from_url(
                settings.redis_url, decode_responses=True, socket_connect_timeout=2
            )
            today = datetime.now(timezone.utc).strftime("%Y%m%d")
            quota_key = f"paperflow:refined_pages:{client_ip}:{today}"
            used = int(redis_client.get(quota_key) or 0)
            if used + page_count > MAX_REFINED_PAGES_PER_DAY:
                raise HTTPException(
                    status_code=429,
                    detail=f"Daily refinement limit reached ({MAX_REFINED_PAGES_PER_DAY} pages/day). You have used {used} pages today. Uncheck 'needs refinement' to publish documents as-is.",
                )
            redis_client.incrby(quota_key, page_count)
            redis_client.expire(quota_key, 172800)  # 48h TTL
        except HTTPException:
            raise
        except Exception as exc:
            logger.warning(f"Refinement quota check skipped (Redis unavailable): {exc}")

    filename = uploads[0].filename or "paper.pdf"
    if len(uploads) > 1:
        try:
            from PIL import Image, ImageOps

            # Protect against decompression bombs
            Image.MAX_IMAGE_PIXELS = 50_000_000

            MAX_PAGE_LONG_EDGE = 2400  # ~4MP; keeps OCR quality while bounding pipeline cost
            images = []
            for page in raw_pages:
                img = Image.open(io.BytesIO(page))
                img = ImageOps.exif_transpose(img) or img
                img = img.convert("RGB")
                long_edge = max(img.size)
                if long_edge > MAX_PAGE_LONG_EDGE:
                    scale = MAX_PAGE_LONG_EDGE / long_edge
                    img = img.resize(
                        (round(img.width * scale), round(img.height * scale)),
                        Image.LANCZOS,
                    )
                images.append(img)
            pdf_buffer = io.BytesIO()
            # resolution matches the downscaled images so pages keep a sane
            # physical size instead of becoming giant 72-DPI poster pages
            images[0].save(
                pdf_buffer,
                format="PDF",
                save_all=True,
                append_images=images[1:],
                resolution=150.0,
            )
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
            "study_year": normalize_study_year(study_year),
            "department": department,
            "course_code": normalize_course_code(course_code),
            "course_name": course_name,
            "year": year,
            "semester": normalize_semester(semester),
            "exam_type": normalize_exam_type(exam_type),
        }.items()
        if value is not None and str(value).strip()
    })
    metadata_envelope["provided"] = provided
    uploaded_at = datetime.now(timezone.utc).isoformat()
    metadata_envelope["uploaded_at"] = uploaded_at
    metadata_envelope["needs_refinement"] = bool(needs_refinement)
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
        uploader_id=user.id,
        uploader_name=user.display_name[:120],
    )
    db.add(paper)
    await db.commit()
    await db.refresh(paper)

    if not needs_refinement:
        # Document is already fine — publish as-is without running the
        # AI refinement pipeline. The original file remains downloadable.
        paper.status = PaperStatus.COMPLETED
        paper.current_stage = "completed"
        paper.stage_progress = 100
        paper.page_count = len(uploads) if len(uploads) > 1 else _count_pdf_pages(content)
        await db.commit()
        return UploadResponse(
            id=paper.id,
            status=paper.status.value,
            message="Upload accepted. Published as-is without refinement.",
            polling_url=f"/api/papers/{paper.id}/status",
        )

    # Dispatch task asynchronously
    _dispatch_processing_task(paper.id, background_tasks)

    return UploadResponse(
        id=paper.id,
        status=paper.status.value,
        message="Upload accepted. Processing has been queued.",
        polling_url=f"/api/papers/{paper.id}/status",
    )
