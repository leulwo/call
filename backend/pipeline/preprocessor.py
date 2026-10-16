"""ExamPaper Refine - Preprocessor stage.

Takes an uploaded file (PDF or image) and produces normalized page images
ready for OCR, along with any embedded text found in digital PDFs.
"""

from __future__ import annotations

import hashlib
import logging
import time
from pathlib import Path
from typing import Optional

import cv2
import fitz  # PyMuPDF
import numpy as np
from PIL import Image

from pipeline.schemas import PageImage, PreprocessResult

logger = logging.getLogger(__name__)

# Rendering DPI for PDF pages → images
RENDER_DPI = 300
# Hard budget on rendered page size. A page rendered above this is scaled
# down to fit; OCR quality is unaffected for normal documents while a
# pathological (e.g. 72-DPI poster-page) PDF cannot stall the pipeline.
MAX_RENDER_PIXELS = 12_000_000
# Above this pixel count, fastNlMeansDenoising becomes minutes-per-page slow;
# fall back to a fast median filter instead.
DENOISE_PIXEL_LIMIT = 6_000_000


def compute_sha256(file_path: Path) -> str:
    """Compute SHA-256 hash of a file."""
    sha = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha.update(chunk)
    return sha.hexdigest()


def _detect_file_type(file_path: Path) -> str:
    """Detect whether the file is a PDF or an image."""
    suffix = file_path.suffix.lower()
    if suffix == ".pdf":
        return "pdf"
    if suffix in {".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp", ".webp"}:
        return "image"
    raise ValueError(f"Unsupported file type: {suffix}")


def _extract_pdf_pages(
    file_path: Path,
    output_dir: Path,
) -> list[PageImage]:
    """Extract pages from a PDF, saving each as an image.

    For each page we also try to extract embedded text (for digital PDFs).
    """
    pages: list[PageImage] = []
    doc = fitz.open(str(file_path))

    try:
        for page_num in range(len(doc)):
            page = doc[page_num]

            # ── Extract embedded text ──────────────────────────────────────
            embedded_text = page.get_text("text").strip()
            has_embedded = bool(embedded_text) and len(embedded_text) > 20

            # ── Render page to image ───────────────────────────────────────
            scale = RENDER_DPI / 72
            pixel_count = page.rect.width * scale * page.rect.height * scale
            if pixel_count > MAX_RENDER_PIXELS:
                shrink = (MAX_RENDER_PIXELS / pixel_count) ** 0.5
                scale *= shrink
                logger.warning(
                    f"Page {page_num + 1} is oversized "
                    f"({page.rect.width:.0f}x{page.rect.height:.0f}pt); "
                    f"rendering at {scale * 72:.0f} DPI to stay within budget"
                )
            mat = fitz.Matrix(scale, scale)
            pix = page.get_pixmap(matrix=mat, alpha=False)
            img_path = output_dir / f"page_{page_num + 1:04d}.png"
            pix.save(str(img_path))

            pages.append(
                PageImage(
                    page_number=page_num + 1,
                    image_path=str(img_path),
                    width=pix.width,
                    height=pix.height,
                    has_embedded_text=has_embedded,
                    embedded_text=embedded_text if has_embedded else None,
                )
            )
    finally:
        doc.close()

    return pages


def _load_image_as_page(
    file_path: Path,
    output_dir: Path,
) -> list[PageImage]:
    """Load a single image file as one page."""
    img = Image.open(file_path)
    # Normalize orientation from EXIF
    from PIL import ImageOps
    img = ImageOps.exif_transpose(img) or img

    # Convert to RGB if needed
    if img.mode != "RGB":
        img = img.convert("RGB")

    img_path = output_dir / "page_0001.png"
    img.save(str(img_path), "PNG")

    return [
        PageImage(
            page_number=1,
            image_path=str(img_path),
            width=img.width,
            height=img.height,
            has_embedded_text=False,
        )
    ]


def _apply_preprocessing(image_path: str) -> list[str]:
    """Apply image preprocessing (deskew, denoise, contrast) in-place.

    Returns a list of operations applied.
    """
    operations: list[str] = []

    img = cv2.imread(image_path)
    if img is None:
        logger.warning(f"Could not read image: {image_path}")
        return operations

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # ── Deskew ─────────────────────────────────────────────────────────────
    try:
        coords = np.column_stack(np.where(gray < 200))
        if len(coords) > 100:
            angle = cv2.minAreaRect(coords)[-1]
            if angle < -45:
                angle = -(90 + angle)
            else:
                angle = -angle

            if abs(angle) > 0.3 and abs(angle) < 15:
                h, w = gray.shape
                center = (w // 2, h // 2)
                M = cv2.getRotationMatrix2D(center, angle, 1.0)
                img = cv2.warpAffine(
                    img, M, (w, h),
                    flags=cv2.INTER_CUBIC,
                    borderMode=cv2.BORDER_REPLICATE,
                )
                gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
                operations.append(f"deskew({angle:.1f}°)")
    except Exception as e:
        logger.debug(f"Deskew skipped: {e}")

    # ── Denoise ────────────────────────────────────────────────────────────
    if gray.size > DENOISE_PIXEL_LIMIT:
        denoised = cv2.medianBlur(gray, 3)
        operations.append("denoise(median)")
    else:
        denoised = cv2.fastNlMeansDenoising(gray, h=10)
        operations.append("denoise")

    # ── Contrast enhancement (CLAHE) ───────────────────────────────────────
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(denoised)
    operations.append("clahe_contrast")

    # ── Save preprocessed image ────────────────────────────────────────────
    cv2.imwrite(image_path, enhanced)

    return operations


def preprocess(
    file_path: Path,
    work_dir: Path,
) -> PreprocessResult:
    """Run the full preprocessing stage.

    Args:
        file_path: Path to the uploaded original file.
        work_dir: Working directory for intermediate files (page images).

    Returns:
        PreprocessResult with page images and metadata.
    """
    start = time.time()
    errors: list[str] = []

    work_dir.mkdir(parents=True, exist_ok=True)
    pages_dir = work_dir / "pages"
    pages_dir.mkdir(exist_ok=True)

    # Fingerprint original
    sha256 = compute_sha256(file_path)
    file_type = _detect_file_type(file_path)

    # Extract pages
    logger.info(f"Preprocessing {file_path.name} (type={file_type})")
    try:
        if file_type == "pdf":
            pages = _extract_pdf_pages(file_path, pages_dir)
        else:
            pages = _load_image_as_page(file_path, pages_dir)
    except Exception as e:
        logger.error(f"Failed to extract pages: {e}")
        return PreprocessResult(
            source_sha256=sha256,
            original_filename=file_path.name,
            file_type=file_type,
            page_count=0,
            pages=[],
            processing_time_seconds=time.time() - start,
            errors=[f"Page extraction failed: {e}"],
        )

    # Apply image preprocessing to each page
    for page in pages:
        try:
            ops = _apply_preprocessing(page.image_path)
            page.preprocessing_applied = ops
        except Exception as e:
            msg = f"Preprocessing failed for page {page.page_number}: {e}"
            logger.warning(msg)
            errors.append(msg)

    elapsed = time.time() - start
    logger.info(
        f"Preprocessed {len(pages)} pages in {elapsed:.1f}s "
        f"(sha256={sha256[:12]}...)"
    )

    return PreprocessResult(
        source_sha256=sha256,
        original_filename=file_path.name,
        file_type=file_type,
        page_count=len(pages),
        pages=pages,
        processing_time_seconds=elapsed,
        errors=errors,
    )
