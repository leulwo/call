"""ExamPaper Refine - AI analysis stage.

Uses Google Gemini to extract structured document data:
  • document type classification
  • questions, sub-questions, marks
  • metadata (university, course, year, etc.)
"""

from __future__ import annotations

import json
import logging
import time
from typing import Optional

from google import genai
from google.genai import types as genai_types

from app.config import get_settings
from pipeline.schemas import (
    AnalysisResult,
    ExtractedMetadata,
    ExtractedQuestion,
    ExtractionResult,
    PreprocessResult,
)
from services.normalizer import (
    normalize_course_code,
    normalize_exam_type,
    normalize_semester,
    normalize_study_year,
)

logger = logging.getLogger(__name__)

# ── System prompt for structure extraction ─────────────────────────────────────

ANALYSIS_SYSTEM_PROMPT = """\
You are a document analysis expert specializing in university exam papers.

Your task is to analyze the provided exam paper text and extract structured
information. Be precise and faithful to the source material.

Rules:
1. Extract ALL questions and sub-questions exactly as they appear.
2. Preserve the exact wording of questions — do not paraphrase or summarize.
3. If marks are shown for a question, include them. If not, set marks to null.
4. Identify the document type based on content:
   - "math_heavy": predominantly equations, formulas, proofs
   - "text_only": mostly prose, essays, short-answer without math
   - "mixed": combination of math and text
   - "diagram_heavy": references diagrams, figures, or images extensively
5. Extract metadata only if clearly stated in the document.
   Do NOT guess or infer metadata that isn't explicitly present.
6. For sub-questions, nest them under their parent question.
7. Number questions in the order they appear (normalized_order).
8. The website-provided metadata context below is user-supplied. Treat its
   resolved fields as authoritative context, preserve them when they are
   present, and use the document only to fill fields that are still missing.
   Never replace a supplied value with a guess.
9. Return normalized metadata, not merely a copy of the user's spelling. Use
   the document and context to correct compact course codes and spacing. For
   example, if the source/context clearly identifies `emete1112` as the
   official course code `EmTe 1112`, return `EmTe 1112`. If the evidence is
   insufficient, keep the safest value and add a warning instead of inventing.
10. A UNIVERSITY KNOWLEDGE BASE CONTEXT section may be provided below. It is a
   curated reference entry (canonical names, aliases, colleges, departments,
   course-code prefixes) for Ethiopian institutions. Use it to normalize
   university names to their canonical form, expand abbreviations (e.g. AAU →
   Addis Ababa University), and map department/course spellings to the
   institution's official naming. The document text always wins over the
   knowledge base when they conflict; add a warning about the conflict instead
   of silently choosing one side.
"""

ANALYSIS_USER_PROMPT_TEMPLATE = """\
Analyze the following exam paper text and extract the structured information.

--- WEBSITE METADATA CONTEXT JSON ---
{metadata_context}
--- END WEBSITE METADATA CONTEXT ---

--- UNIVERSITY KNOWLEDGE BASE CONTEXT ---
{knowledge_context}
--- END UNIVERSITY KNOWLEDGE BASE CONTEXT ---

--- EXAM PAPER TEXT ---
{text}
--- END ---

Respond with a JSON object matching this exact schema:

{{
  "document_type": "math_heavy" | "text_only" | "mixed" | "diagram_heavy",
  "metadata": {{
    "title": "string or null",
    "description": "string or null",
    "university": "string or null",
    "university_type": "string or null",
    "study_year": "string or null",
    "department": "string or null",
    "course_code": "string or null",
    "course_name": "string or null",
    "year": "integer or null",
    "semester": "string or null",
    "exam_type": "string or null (midterm/final/quiz/assignment)",
    "language": "string (default: en)",
    "instructor": "string or null",
    "total_marks": "number or null",
    "duration": "string or null",
    "instructions": "string or null"
  }},
  "questions": [
    {{
      "display_number": "string (e.g. '1', '2a', '3.ii')",
      "normalized_order": "integer",
      "text": "exact question text",
      "marks": "number or null",
      "page_start": "integer or null",
      "page_end": "integer or null",
      "topics": ["list", "of", "topic", "tags"],
      "sub_questions": [
        ... (same schema, nested)
      ]
    }}
  ],
  "confidence": "float 0.0-1.0 — your confidence in the extraction accuracy",
  "warnings": ["list of any issues or uncertainties"]
}}

Important:
- Return ONLY valid JSON, no markdown fencing, no explanation.
- Preserve exact question text from the source.
- If you cannot determine a metadata field, set it to null.
"""


def _build_client() -> genai.Client:
    """Create a Gemini client."""
    settings = get_settings()
    if not settings.gemini_api_key:
        raise ValueError(
            "GEMINI_API_KEY is not set. Add it to your .env file."
        )
    return genai.Client(api_key=settings.gemini_api_key)


def _parse_questions(raw: list[dict]) -> list[ExtractedQuestion]:
    """Recursively parse question dicts into ExtractedQuestion models."""
    questions = []
    for index, q in enumerate(raw):
        sub_qs = _parse_questions(q.get("sub_questions", []))
        # The model sometimes emits fractional ordering (e.g. 5.1 for a
        # sub-question numbered "5.1"). Coerce to a stable integer sequence
        # instead of failing the whole analysis.
        try:
            normalized_order = int(float(q.get("normalized_order", index + 1)))
        except (TypeError, ValueError):
            normalized_order = index + 1
        marks = q.get("marks")
        try:
            marks = float(marks) if marks is not None else None
        except (TypeError, ValueError):
            marks = None

        def _as_int(value):
            try:
                return int(float(value)) if value is not None else None
            except (TypeError, ValueError):
                return None

        questions.append(
            ExtractedQuestion(
                display_number=str(q.get("display_number", "")),
                normalized_order=normalized_order,
                text=q.get("text", ""),
                marks=marks,
                page_start=_as_int(q.get("page_start")),
                page_end=_as_int(q.get("page_end")),
                topics=q.get("topics", []),
                sub_questions=sub_qs,
            )
        )
    return questions


def _clean_json_response(text: str) -> str:
    """Strip markdown fencing and whitespace from a JSON response."""
    text = text.strip()
    if text.startswith("```"):
        # Remove opening fence (e.g. ```json)
        first_newline = text.index("\n")
        text = text[first_newline + 1:]
    if text.endswith("```"):
        text = text[:-3]
    return text.strip()


def analyze(
    extraction_result: ExtractionResult,
    preprocess_result: Optional[PreprocessResult] = None,
    provided_metadata: Optional[dict] = None,
    knowledge_context: str = "",
) -> AnalysisResult:
    """Run AI analysis on extracted text to produce structured data.

    Args:
        extraction_result: Output from the extractor stage.
        preprocess_result: Optional preprocessor output (for page images on
            low-confidence pages — future enhancement).
        provided_metadata: Resolved website/user metadata context JSON.
        knowledge_context: Matched university reference text from the local
            Ethiopian-universities knowledge base (empty when unmatched).

    Returns:
        AnalysisResult with document type, metadata, and questions.
    """
    start = time.time()
    settings = get_settings()
    model_name = settings.gemini_model

    if not extraction_result.full_text.strip():
        return AnalysisResult(
            document_type="text_only",
            metadata=ExtractedMetadata(),
            questions=[],
            confidence=0.0,
            model_used=model_name,
            processing_time_seconds=time.time() - start,
            warnings=["No text available for analysis"],
        )

    # ── Call Gemini ────────────────────────────────────────────────────────
    logger.info(f"Analyzing document with {model_name}...")
    client = _build_client()

    user_prompt = ANALYSIS_USER_PROMPT_TEMPLATE.format(
        metadata_context=json.dumps(provided_metadata or {}, ensure_ascii=False)[:10000],
        knowledge_context=(knowledge_context or "").strip()[:8000],
        text=extraction_result.full_text[:30000],  # Limit input size
    )

    try:
        response = client.models.generate_content(
            model=model_name,
            contents=user_prompt,
            config=genai_types.GenerateContentConfig(
                system_instruction=ANALYSIS_SYSTEM_PROMPT,
                temperature=0.1,  # Low temperature for factual extraction
                response_mime_type="application/json",
                max_output_tokens=16384,
            ),
        )

        raw_text = response.text
        if not raw_text:
            raise ValueError("Empty response from Gemini")

        # Parse JSON response
        cleaned = _clean_json_response(raw_text)
        data = json.loads(cleaned)

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse Gemini response as JSON: {e}")
        logger.debug(f"Raw response: {raw_text[:500]}")
        return AnalysisResult(
            document_type="text_only",
            metadata=ExtractedMetadata(),
            questions=[],
            confidence=0.0,
            model_used=model_name,
            processing_time_seconds=time.time() - start,
            warnings=[f"JSON parse error: {e}"],
        )
    except Exception as e:
        logger.error(f"Gemini API call failed: {e}")
        return AnalysisResult(
            document_type="text_only",
            metadata=ExtractedMetadata(),
            questions=[],
            confidence=0.0,
            model_used=model_name,
            processing_time_seconds=time.time() - start,
            warnings=[f"API error: {e}"],
        )

    # ── Parse structured output ────────────────────────────────────────────
    metadata_raw = data.get("metadata", {})
    metadata = ExtractedMetadata(
        title=metadata_raw.get("title"),
        description=metadata_raw.get("description"),
        university=metadata_raw.get("university"),
        university_type=metadata_raw.get("university_type"),
        study_year=normalize_study_year(metadata_raw.get("study_year")),
        department=metadata_raw.get("department"),
        course_code=normalize_course_code(metadata_raw.get("course_code")),
        course_name=metadata_raw.get("course_name"),
        year=metadata_raw.get("year"),
        semester=normalize_semester(metadata_raw.get("semester")),
        exam_type=normalize_exam_type(metadata_raw.get("exam_type")),
        language=metadata_raw.get("language", "en"),
        instructor=metadata_raw.get("instructor"),
        total_marks=metadata_raw.get("total_marks"),
        duration=metadata_raw.get("duration"),
        instructions=metadata_raw.get("instructions"),
    )

    questions = _parse_questions(data.get("questions", []))

    # Count total marks found
    def _sum_marks(qs: list[ExtractedQuestion]) -> float:
        total = 0.0
        for q in qs:
            if q.marks:
                total += q.marks
            total += _sum_marks(q.sub_questions)
        return total

    total_marks = _sum_marks(questions) or metadata.total_marks

    elapsed = time.time() - start
    warnings = data.get("warnings", [])
    confidence = data.get("confidence", 0.5)

    logger.info(
        f"Analysis complete: {len(questions)} questions, "
        f"type={data.get('document_type', 'unknown')}, "
        f"confidence={confidence:.2f}, {elapsed:.1f}s"
    )

    return AnalysisResult(
        document_type=data.get("document_type", "text_only"),
        metadata=metadata,
        questions=questions,
        total_questions=len(questions),
        total_marks_found=total_marks,
        confidence=confidence,
        model_used=model_name,
        processing_time_seconds=round(elapsed, 3),
        warnings=warnings,
    )
