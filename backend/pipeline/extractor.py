"""ExamPaper Refine - Text extraction stage.

Uses Gemini's multimodal vision to extract text from page images.
For digital PDFs with embedded text, uses PyMuPDF directly (free, instant).
Falls back to Gemini vision for scanned/image pages.
"""

from __future__ import annotations

import base64
import logging
import time
from pathlib import Path
from typing import Optional

from google import genai
from google.genai import types as genai_types

from app.config import get_settings
from pipeline.schemas import ExtractionResult, PageText, PreprocessResult

logger = logging.getLogger(__name__)

# ── Gemini Vision extraction prompt ─────────────────────────────────────────────

VISION_EXTRACTION_PROMPT = """\
Extract ALL text from this exam paper image. Be extremely thorough and precise.

Rules:
1. Preserve the exact wording, spelling, and punctuation as shown.
2. Reproduce mathematical expressions using standard notation (e.g. x^2, sqrt(x), integral, summation).
3. Maintain the logical reading order (headers first, then body, questions in order).
4. Preserve question numbers exactly (e.g. "1.", "2a)", "iii.").
5. Include ALL text: headers, instructions, questions, marks, footnotes, page numbers.
6. For tables, reproduce them in a readable plain-text format.
7. If text is partially illegible, include your best reading with [unclear] markers.
8. Separate distinct sections with blank lines.
9. Do NOT add any commentary, explanation, or markdown formatting — output ONLY the extracted text.
"""


def _estimate_text_quality(text: str) -> float:
    """Rough heuristic for text quality (0.0–1.0)."""
    if not text or len(text.strip()) < 10:
        return 0.0

    words = text.split()
    if not words:
        return 0.0

    alpha_chars = sum(1 for c in text if c.isalpha())
    total_chars = len(text.replace(" ", "").replace("\n", ""))
    alpha_ratio = alpha_chars / max(total_chars, 1)

    avg_word_len = sum(len(w) for w in words) / len(words)
    word_len_score = 1.0 if 2 < avg_word_len < 15 else 0.5

    score = (alpha_ratio * 0.6 + word_len_score * 0.4)
    return round(min(max(score, 0.0), 1.0), 3)


def _extract_with_gemini(image_path: str) -> tuple[str, float]:
    """Use Gemini's multimodal vision to extract text from an image.

    Returns (text, confidence).
    """
    settings = get_settings()
    client = genai.Client(api_key=settings.gemini_api_key)

    # Read and encode the image
    image_bytes = Path(image_path).read_bytes()
    
    # Determine MIME type from extension
    ext = Path(image_path).suffix.lower()
    mime_map = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}
    mime_type = mime_map.get(ext, "image/png")

    try:
        response = client.models.generate_content(
            model=settings.gemini_model,
            contents=[
                genai_types.Content(
                    parts=[
                        genai_types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                        genai_types.Part.from_text(text=VISION_EXTRACTION_PROMPT),
                    ]
                )
            ],
            config=genai_types.GenerateContentConfig(
                temperature=0.1,
                max_output_tokens=8192,
            ),
        )

        text = response.text or ""
        text = text.strip()

        # Estimate quality based on output
        confidence = _estimate_text_quality(text)
        # Gemini vision is generally high-quality when it returns text
        if text and len(text) > 20:
            confidence = max(confidence, 0.85)

        return text, confidence

    except Exception as e:
        logger.error(f"Gemini vision extraction failed for {image_path}: {e}")
        return "", 0.0


def extract_text(
    preprocess_result: PreprocessResult,
    lang: str = "eng",
) -> ExtractionResult:
    """Run text extraction on all preprocessed pages.

    Strategy per page:
    1. If high-quality embedded text exists (digital PDF) → use it directly.
    2. Otherwise → use Gemini vision to read the image.

    Args:
        preprocess_result: Output from the preprocessor stage.
        lang: Language hint (reserved for future use).

    Returns:
        ExtractionResult with per-page text and confidence scores.
    """
    start = time.time()
    page_texts: list[PageText] = []
    methods_used: set[str] = set()

    for page in preprocess_result.pages:
        page_start = time.time()

        if page.has_embedded_text and page.embedded_text:
            # Use embedded text from digital PDF (free, no API call)
            text = page.embedded_text
            confidence = _estimate_text_quality(text)
            method = "embedded"

            # If embedded text quality is very low, try Gemini vision
            if confidence < 0.3:
                logger.info(
                    f"Page {page.page_number}: embedded text quality low "
                    f"({confidence:.2f}), falling back to Gemini vision"
                )
                vision_text, vision_conf = _extract_with_gemini(page.image_path)
                if vision_conf > confidence:
                    text = vision_text
                    confidence = vision_conf
                    method = "gemini_vision"
        else:
            # No embedded text (scanned page or image upload) → Gemini vision
            text, confidence = _extract_with_gemini(page.image_path)
            method = "gemini_vision"

        page_time = time.time() - page_start
        methods_used.add(method)

        page_texts.append(
            PageText(
                page_number=page.page_number,
                text=text,
                method=method,
                confidence=confidence,
                word_count=len(text.split()) if text else 0,
                processing_time_seconds=round(page_time, 3),
            )
        )

        logger.debug(
            f"Page {page.page_number}: method={method}, "
            f"confidence={confidence:.2f}, words={page_texts[-1].word_count}"
        )

    # Aggregate results
    total_words = sum(p.word_count for p in page_texts)
    confidences = [p.confidence for p in page_texts if p.confidence is not None]
    overall_conf = sum(confidences) / len(confidences) if confidences else 0.0
    full_text = "\n\n--- PAGE BREAK ---\n\n".join(p.text for p in page_texts if p.text)

    elapsed = time.time() - start
    logger.info(
        f"Extracted {total_words} words from {len(page_texts)} pages "
        f"in {elapsed:.1f}s (confidence={overall_conf:.2f})"
    )

    return ExtractionResult(
        pages=page_texts,
        overall_confidence=round(overall_conf, 3),
        total_word_count=total_words,
        methods_used=sorted(methods_used),
        full_text=full_text,
        processing_time_seconds=round(elapsed, 3),
    )
