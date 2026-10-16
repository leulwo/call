"""ExamPaper Refine - AI rewriter stage.

Uses Google Gemini to rewrite the exam paper into a clean, typeset document.
The format is chosen based on document type:
  • math_heavy / mixed → LaTeX
  • text_only → HTML
  • diagram_heavy → HTML (with placeholders for diagrams)

The output is always a source file that can be rendered to PDF.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Optional

from google import genai
from google.genai import types as genai_types

from app.config import get_settings
from pipeline.figure_generator import generate_figures_for_document
from pipeline.latex_template import assemble_latex_document
from pipeline.schemas import AnalysisResult, ExtractionResult, RewriteResult

logger = logging.getLogger(__name__)


# ── Format selection ───────────────────────────────────────────────────────────


def _choose_format(document_type: str) -> str:
    """Select the best output format based on document type."""
    mapping = {
        "math_heavy": "latex",
        "mixed": "latex",
        "text_only": "html",
        "diagram_heavy": "html",
    }
    return mapping.get(document_type, "html")


# ── Prompt templates ───────────────────────────────────────────────────────────


REWRITE_SYSTEM_PROMPT = """\
You are an expert document typesetter. Your job is to take the text content
of a university exam paper and rewrite it as a clean, professionally formatted
document.

CRITICAL RULES:
1. PRESERVE the exact wording of every question, instruction, and mark allocation.
   Do NOT add, remove, paraphrase, or summarize any exam content.
2. Fix OCR artifacts (broken words, garbled characters) ONLY when the correction
   is obvious and unambiguous. If uncertain, keep the original text.
3. Use proper document structure: title, course information header, instructions
   section, numbered questions with sub-questions.
4. For equations and mathematical notation, use the appropriate format notation
   (LaTeX math mode or HTML with proper symbols).
5. Include mark allocations exactly as shown in the original (e.g., [10 marks]).
6. Add page breaks between major sections where appropriate.
7. Do NOT add solutions, answers, hints, or commentary.
8. Do NOT add watermarks, footers, or any text not in the original.
"""

LATEX_PROMPT = """\
Rewrite the following exam paper as the BODY of a LaTeX document.

IMPORTANT — the build system supplies the document preamble automatically
(document class, packages, fonts, spacing). You must NOT include:
- \\documentclass or \\usepackage lines
- \\begin{{document}} or \\end{{document}}
Return ONLY the content that goes between \\begin{{document}} and
\\end{{document}}.

Body structure:
- Document header with university, course, exam type, date, duration, marks
  (e.g., \\begin{{center}}...\\end{{center}} for the title block)
- Instructions section (if present in the original)
- Questions using \\begin{{enumerate}} with proper nesting for sub-questions
- Math equations in $...$ or \\[...\\] as appropriate (never put \\item inside
  display math blocks)
- Mark allocations right-aligned or in brackets
- IMPORTANT: For any figures listed in GENERATED FIGURES below, embed them using
  the exact TikZ \\begin{{figure}} block provided. Place each figure at the
  point in the document where it is referenced. tikz/pgfplots are already
  loaded — never add packages.
{feedback_section}
--- DOCUMENT METADATA ---
{metadata}

--- EXTRACTED QUESTIONS ---
{questions}

--- GENERATED FIGURES ---
{figures}

--- FULL TEXT ---
{text}
--- END ---

Return ONLY the LaTeX body content. No explanation, no markdown fencing,
no preamble.
"""

HTML_PROMPT = """\
Rewrite the following exam paper as a clean, print-ready HTML document.

Use the following structure:
- Complete HTML5 document with embedded CSS
- Professional styling: clean serif font, proper margins, good spacing
- Document header with university, course, exam type, date, duration, marks
- Instructions section (if present in the original)
- Numbered questions using ordered lists with proper nesting
- Mark allocations styled distinctly (e.g., right-aligned, smaller font)
- Use CSS @media print for clean printing
- For math notation, use Unicode symbols or HTML entities where possible
{feedback_section}
--- DOCUMENT METADATA ---
{metadata}

--- EXTRACTED QUESTIONS ---
{questions}

--- FULL TEXT ---
{text}
--- END ---

Return ONLY the complete HTML source. No explanation, no markdown fencing.
Start with <!DOCTYPE html> and end with </html>.
"""

FEEDBACK_SECTION_TEMPLATE = """
--- USER CORRECTION REQUEST ---
A reader reported problems with a previous version of this document. Address
EVERY point below while still preserving the original exam content faithfully
(never invent or drop questions/marks):
{feedback}
--- END USER CORRECTION REQUEST ---
"""


def _format_metadata(analysis: AnalysisResult) -> str:
    """Format metadata for the prompt."""
    m = analysis.metadata
    parts = []
    if m.university:
        parts.append(f"University: {m.university}")
    if m.department:
        parts.append(f"Department: {m.department}")
    if m.course_code:
        parts.append(f"Course Code: {m.course_code}")
    if m.course_name:
        parts.append(f"Course Name: {m.course_name}")
    if m.year:
        parts.append(f"Year: {m.year}")
    if m.semester:
        parts.append(f"Semester: {m.semester}")
    if m.exam_type:
        parts.append(f"Exam Type: {m.exam_type}")
    if m.instructor:
        parts.append(f"Instructor: {m.instructor}")
    if m.total_marks:
        parts.append(f"Total Marks: {m.total_marks}")
    if m.duration:
        parts.append(f"Duration: {m.duration}")
    if m.instructions:
        parts.append(f"Instructions: {m.instructions}")
    return "\n".join(parts) if parts else "No metadata available"


def _format_questions(analysis: AnalysisResult) -> str:
    """Format questions for the prompt."""
    lines = []

    def _fmt(q, indent=0):
        prefix = "  " * indent
        mark_str = f" [{q.marks} marks]" if q.marks else ""
        lines.append(f"{prefix}{q.display_number}. {q.text}{mark_str}")
        for sub in q.sub_questions:
            _fmt(sub, indent + 1)

    for q in analysis.questions:
        _fmt(q)

    return "\n".join(lines) if lines else "Questions could not be parsed individually."


def rewrite(
    extraction_result: ExtractionResult,
    analysis_result: AnalysisResult,
    output_dir: Path,
    feedback: Optional[str] = None,
) -> RewriteResult:
    """Rewrite the exam paper into a clean typeset document.

    Args:
        extraction_result: The raw extracted text.
        analysis_result: Structured analysis with questions and metadata.
        output_dir: Directory to save the generated source file.
        feedback: Optional user correction request (e.g. from an accuracy
            report). Injected into the prompt so the regeneration addresses it.

    Returns:
        RewriteResult with the generated source content and file path.
    """
    start = time.time()
    settings = get_settings()
    model_name = settings.gemini_model

    # Choose format based on document type
    fmt = _choose_format(analysis_result.document_type)
    logger.info(
        f"Rewriting document as {fmt} "
        f"(document_type={analysis_result.document_type})"
    )

    # Build prompt
    metadata_str = _format_metadata(analysis_result)
    questions_str = _format_questions(analysis_result)
    text = extraction_result.full_text[:30000]

    # ── Generate TikZ figures (LaTeX only) ─────────────────────────────────
    figures_str = "None"
    if fmt == "latex":
        generated_figures = generate_figures_for_document(
            full_text=extraction_result.full_text,
        )
        if generated_figures:
            figure_blocks = []
            for fig in generated_figures:
                figure_blocks.append(
                    f"Description: {fig['description']}\n"
                    f"LaTeX block:\n{fig['latex_include']}"
                )
            figures_str = "\n\n".join(figure_blocks)
            logger.info(f"Injecting {len(generated_figures)} generated figures into LaTeX")

    if fmt == "latex":
        user_prompt = LATEX_PROMPT.format(
            metadata=metadata_str, questions=questions_str,
            figures=figures_str, text=text,
            feedback_section=(
                FEEDBACK_SECTION_TEMPLATE.format(feedback=feedback.strip()[:4000])
                if feedback and feedback.strip() else ""
            ),
        )
    else:
        user_prompt = HTML_PROMPT.format(
            metadata=metadata_str, questions=questions_str, text=text,
            feedback_section=(
                FEEDBACK_SECTION_TEMPLATE.format(feedback=feedback.strip()[:4000])
                if feedback and feedback.strip() else ""
            ),
        )

    # Call Gemini
    warnings: list[str] = []
    try:
        client = genai.Client(api_key=settings.gemini_api_key)
        response = client.models.generate_content(
            model=model_name,
            contents=user_prompt,
            config=genai_types.GenerateContentConfig(
                system_instruction=REWRITE_SYSTEM_PROMPT,
                temperature=0.2,
                max_output_tokens=16384,
            ),
        )

        source_content = response.text
        if not source_content:
            raise ValueError("Empty response from Gemini")

        # Clean up response — remove markdown fencing if present
        source_content = source_content.strip()
        if source_content.startswith("```"):
            first_nl = source_content.index("\n")
            source_content = source_content[first_nl + 1:]
        if source_content.endswith("```"):
            source_content = source_content[:-3].strip()

        # Server-controlled preamble: wrap the model's body in the fixed
        # template (also strips any \documentclass wrapper the model added
        # anyway, so typography never depends on prompt compliance).
        if fmt == "latex":
            source_content = assemble_latex_document(source_content)

    except Exception as e:
        logger.error(f"Rewriting failed: {e}")
        return RewriteResult(
            format_chosen=fmt,
            source_content="",
            model_used=model_name,
            processing_time_seconds=time.time() - start,
            warnings=[f"Rewrite failed: {e}"],
        )

    # Save source file
    output_dir.mkdir(parents=True, exist_ok=True)
    ext = ".tex" if fmt == "latex" else ".html"
    source_path = output_dir / f"rewritten{ext}"
    source_path.write_text(source_content, encoding="utf-8")

    elapsed = time.time() - start
    logger.info(
        f"Rewrite complete: {fmt}, {len(source_content)} chars, {elapsed:.1f}s"
    )

    return RewriteResult(
        format_chosen=fmt,
        source_content=source_content,
        source_file_path=str(source_path),
        model_used=model_name,
        processing_time_seconds=round(elapsed, 3),
        warnings=warnings,
    )
