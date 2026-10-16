"""ExamPaper Refine - TikZ Figure Generator.

When an exam question references a figure (e.g. "Figure 1: A parabola
y=x^2"), this module:
  1. Uses Gemini to write a self-contained TikZ/pgfplots block that
     reproduces the figure.
  2. Sanitizes the block so it compiles inside the server-controlled
     LaTeX template.

Figures are pure LaTeX vector graphics — no subprocess execution, no PNG
files, one unified graphics system end to end.
"""

from __future__ import annotations

import logging
import re
import time
from typing import Optional

from google import genai
from google.genai import types as genai_types

from app.config import get_settings

logger = logging.getLogger(__name__)


# ── Prompt ─────────────────────────────────────────────────────────────────────

FIGURE_TIKZ_SYSTEM = """\
You are an expert LaTeX developer who recreates mathematical figures using
TikZ and pgfplots.

Your task is to write ONE self-contained tikzpicture that reproduces the
described figure.

Rules:
1. Output ONLY a single \\begin{tikzpicture}...\\end{tikzpicture} block.
   No preamble, no \\documentclass, no \\usepackage, no figure environment,
   no explanation, no markdown fencing.
2. For function graphs and data plots use a pgfplots axis environment with a
   clean style: labeled axes, grid=major, sensible domain/samples, and a
   legend only when the original has one.
3. For geometric diagrams use plain TikZ coordinates with labeled points,
   angle marks, right-angle squares, and dimension annotations as needed.
4. Scale the picture to fit comfortably within \\textwidth (e.g. width=8cm).
5. The block must compile standalone inside a document that already loads
   tikz and pgfplots (compat=1.18): never rely on external files, custom
   macros, or \\usetikzlibrary beyond arrows.meta/calc/patterns/angles/quotes.
6. Keep the block under 80 lines and faithful to the description.
"""

FIGURE_TIKZ_USER = """\
Write a TikZ (pgfplots allowed) figure for the following description from a
university exam paper.

Figure description:
{description}

Context (surrounding question text):
{context}

Return ONLY the \\begin{{tikzpicture}}...\\end{{tikzpicture}} block.
"""


# ── Figure description detection ───────────────────────────────────────────────

FIGURE_REFERENCE_PATTERNS = [
    r"(?i)(figure\s+\d+\s*[:–—-][^\n.]{5,120})",      # Figure 1: description
    r"(?i)(fig\.\s*\d+\s*[:–—-][^\n.]{5,120})",        # Fig. 1: description
    r"(?i)(the\s+(?:graph|plot|diagram|curve)\s+(?:below|above|shown)\s+[^\n.]{0,80})",
    r"(?i)(sketch\s+(?:the\s+)?(?:graph|curve|function)\s+[^\n.]{5,100})",
    r"(?i)(plot\s+(?:the\s+)?(?:graph|curve|function)\s+[^\n.]{5,100})",
    r"(?i)(draw\s+(?:the\s+)?(?:graph|curve|function)\s+[^\n.]{5,100})",
]


def extract_figure_descriptions(text: str) -> list[dict]:
    """Scan text for figure references and return a list of found figures.

    Returns a list of dicts with 'description' and 'context' keys.
    """
    figures = []
    for pattern in FIGURE_REFERENCE_PATTERNS:
        for match in re.finditer(pattern, text):
            description = match.group(1).strip()
            # Get surrounding context (100 chars on each side)
            start = max(0, match.start() - 100)
            end = min(len(text), match.end() + 100)
            context = text[start:end]
            figures.append({
                "description": description,
                "context": context,
                "span": match.span(),
            })

    # Deduplicate by description
    seen = set()
    unique_figures = []
    for fig in figures:
        key = fig["description"][:60].lower()
        if key not in seen:
            seen.add(key)
            unique_figures.append(fig)

    return unique_figures


# ── TikZ code generation ───────────────────────────────────────────────────────

_BEGIN_PICTURE = "\\begin{tikzpicture}"
_END_PICTURE = "\\end{tikzpicture}"

_FORBIDDEN_SNIPPETS = (
    "\\documentclass",
    "\\usepackage",
    "\\begin{document}",
    "\\end{document}",
)


def _clean_tikz(model_output: str) -> Optional[str]:
    """Normalize model output to exactly one compilable tikzpicture block."""
    code = model_output.strip()

    # Strip markdown fencing if present
    if code.startswith("```"):
        first_nl = code.find("\n")
        if first_nl == -1:
            return None
        code = code[first_nl + 1:]
    if code.endswith("```"):
        code = code[:-3].strip()

    begin_idx = code.find(_BEGIN_PICTURE)
    if begin_idx == -1:
        logger.warning("TikZ generation returned no tikzpicture environment")
        return None

    end_idx = code.rfind(_END_PICTURE)
    if end_idx == -1:
        logger.warning("TikZ generation returned an unterminated tikzpicture")
        return None

    code = code[begin_idx:end_idx + len(_END_PICTURE)]

    for snippet in _FORBIDDEN_SNIPPETS:
        if snippet in code:
            logger.warning(f"TikZ block contained forbidden snippet {snippet!r}; rejected")
            return None

    return code


def _generate_tikz(description: str, context: str) -> Optional[str]:
    """Call Gemini to generate a TikZ block for a figure description."""
    settings = get_settings()
    client = genai.Client(api_key=settings.gemini_api_key)

    prompt = FIGURE_TIKZ_USER.format(
        description=description,
        context=context,
    )

    try:
        response = client.models.generate_content(
            model=settings.gemini_model,
            contents=prompt,
            config=genai_types.GenerateContentConfig(
                system_instruction=FIGURE_TIKZ_SYSTEM,
                temperature=0.2,
                max_output_tokens=4096,
            ),
        )
        return _clean_tikz(response.text or "")

    except Exception as e:
        logger.error(f"Gemini TikZ generation failed: {e}")
        return None


def _figure_environment(tikz: str, caption: str, key: str) -> str:
    """Wrap a tikzpicture in a floatable figure environment."""
    return (
        "\\begin{figure}[h!]\n"
        "  \\centering\n"
        f"{tikz}\n"
        f"  \\caption{{{caption}}}\n"
        f"  \\label{{fig:{key}}}\n"
        "\\end{figure}"
    )


# ── Public API ─────────────────────────────────────────────────────────────────

def generate_figure(
    description: str,
    context: str,
) -> Optional[str]:
    """Generate a TikZ figure block for a given description.

    Args:
        description: The figure description extracted from the exam text.
        context: Surrounding question text for better understanding.

    Returns:
        A compilable ``\\begin{tikzpicture}`` block, or None on failure.
    """
    logger.info(f"Generating TikZ figure for: {description[:60]}...")
    start = time.time()

    tikz = _generate_tikz(description, context)
    elapsed = time.time() - start

    if tikz:
        logger.info(f"TikZ figure generated in {elapsed:.1f}s ({len(tikz)} chars)")
        return tikz

    logger.warning(f"TikZ figure generation failed for: {description[:60]}")
    return None


def generate_figures_for_document(full_text: str) -> list[dict]:
    """Scan a document and generate TikZ blocks for all detectable figures.

    Args:
        full_text: The full extracted text of the exam paper.

    Returns:
        List of dicts with 'description', 'latex_key', and 'latex_include'
        for each successfully generated figure. 'latex_include' is ready to
        paste into the document body.
    """
    detected = extract_figure_descriptions(full_text)

    if not detected:
        logger.info("No figure references detected in document")
        return []

    logger.info(f"Detected {len(detected)} potential figures in document")
    results = []

    for i, fig in enumerate(detected):
        latex_key = f"figure_{i + 1:02d}"
        tikz = generate_figure(description=fig["description"], context=fig["context"])
        if tikz:
            results.append({
                "description": fig["description"],
                "latex_key": latex_key,
                "latex_include": _figure_environment(
                    tikz, fig["description"], latex_key
                ),
            })

    logger.info(f"Successfully generated {len(results)}/{len(detected)} figures")
    return results
