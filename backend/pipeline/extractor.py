"""ExamPaper Refine - Text extraction stage.

Extracts text from preprocessed page images using embedded text (PyMuPDF)
where available, falling back to Tesseract OCR for scanned / image pages.
"""

from __future__ import annotations

import logging
import time
from typing import Optional

import pytesseract
from PIL import Image

from pipeline.schemas import ExtractionResult, PageText, PreprocessResult

logger = logging.getLogger(__name__)

# Tesseract configuration for exam papers
# OEM 3 = default (best available), PSM 6 = uniform block of text
TESSERACT_CONFIG = "--oem 3 --psm 6"


def _estimate_text_quality(text: str) -> float:
    """Rough heuristic for text quality (0.0–1.0).

    Checks for reasonable word lengths, alphabet ratio, etc.
    """
    if not text or len(text.strip()) < 10:
        return 0.0

    words = text.split()
    if not words:
        return 0.0

    # Ratio of alphabetic characters
    alpha_chars = sum(1 for c in text if c.isalpha())
    total_chars = len(text.replace(" ", "").replace("\n", ""))
    alpha_ratio = alpha_chars / max(total_chars, 1)

    # Average word length (very short or very long = suspicious)
    avg_word_len = sum(len(w) for w in words) / len(words)
    word_len_score = 1.0 if 2 < avg_word_len < 15 else 0.5

    # Combine heuristics
    score = (alpha_ratio * 0.6 + word_len_score * 0.4)
    return round(min(max(score, 0.0), 1.0), 3)


def _ocr_page(image_path: str, lang: str = "eng") -> tuple[str, Optional[float]]:
    """Run Tesseract OCR on a page image.

    Returns (text, confidence).
    """
    try:
        img = Image.open(image_path)
        # Get detailed data for confidence
        data = pytesseract.image_to_data(
            img, lang=lang, config=TESSERACT_CONFIG, output_type=pytesseract.Output.DICT
        )

        # Calculate average confidence from word-level confidences
        confidences = [
            int(c) for c in data["conf"] if int(c) > 0
        ]
        avg_conf = sum(confidences) / len(confidences) / 100.0 if confidences else 0.0

        # Get the full text
        text = pytesseract.image_to_string(img, lang=lang, config=TESSERACT_CONFIG)

        return text.strip(), round(avg_conf, 3)

    except Exception as e:
        logger.error(f"OCR failed for {image_path}: {e}")
        return "", 0.0


def extract_text(
    preprocess_result: PreprocessResult,
    lang: str = "eng",
) -> ExtractionResult:
    """Run text extraction on all preprocessed pages.

    Strategy per page:
    1. If high-quality embedded text exists → use it directly.
    2. Otherwise → run Tesseract OCR.

    Args:
        preprocess_result: Output from the preprocessor stage.
        lang: Tesseract language code.

    Returns:
        ExtractionResult with per-page text and confidence scores.
    """
    start = time.time()
    page_texts: list[PageText] = []
    methods_used: set[str] = set()

    for page in preprocess_result.pages:
        page_start = time.time()

        if page.has_embedded_text and page.embedded_text:
            # Use embedded text from digital PDF
            text = page.embedded_text
            confidence = _estimate_text_quality(text)
            method = "embedded"

            # If embedded text quality is very low, try OCR as well
            if confidence < 0.3:
                logger.info(
                    f"Page {page.page_number}: embedded text quality low "
                    f"({confidence:.2f}), trying OCR"
                )
                ocr_text, ocr_conf = _ocr_page(page.image_path, lang)
                if ocr_conf and ocr_conf > confidence:
                    text = ocr_text
                    confidence = ocr_conf
                    method = "tesseract"
        else:
            # No embedded text — use OCR
            text, confidence = _ocr_page(page.image_path, lang)
            method = "tesseract"
            confidence = confidence or 0.0

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
