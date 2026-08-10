"""ExamPaper Refine - Matplotlib Figure Generator.

When a math question references a figure (e.g. "Figure 1: A parabola y=x^2"),
this module:
  1. Uses Gemini to write a matplotlib script that reproduces the figure.
  2. Runs the script in a subprocess sandbox.
  3. Returns the path to the saved PNG image.

The generated image can then be embedded into a LaTeX document via \\includegraphics{}.
"""

from __future__ import annotations

import logging
import re
import subprocess
import sys
import textwrap
import time
from pathlib import Path
from typing import Optional

from google import genai
from google.genai import types as genai_types

from app.config import get_settings

logger = logging.getLogger(__name__)


# ── Prompt ─────────────────────────────────────────────────────────────────────

FIGURE_CODEGEN_SYSTEM = """\
You are an expert Python programmer who specializes in recreating mathematical
figures and graphs using matplotlib.

Your task is to write a SINGLE, SELF-CONTAINED Python script that generates
a figure and saves it to disk.

Rules:
1. Use ONLY standard Python libraries plus matplotlib and numpy. No other imports.
2. The script MUST save the figure to the path given by the variable OUTPUT_PATH
   which will be injected at the top of the script.
3. Do NOT call plt.show(). Only call plt.savefig(OUTPUT_PATH, dpi=150, bbox_inches='tight').
4. Use a clean, minimal style: white background, labeled axes, grid lines.
5. Make the figure accurate and faithful to the description.
6. Keep the script under 60 lines.
7. Return ONLY the Python code. No explanation, no markdown fencing.
"""

FIGURE_CODEGEN_USER = """\
Write a matplotlib script to generate the following figure from a university exam paper.

Figure description:
{description}

Context (surrounding question text):
{context}

The script will have the following line injected at the very top before your code:
  OUTPUT_PATH = "/path/to/output.png"

Your script must end with:
  plt.savefig(OUTPUT_PATH, dpi=150, bbox_inches='tight')
  plt.close()
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


# ── Code generation ────────────────────────────────────────────────────────────

def _generate_matplotlib_code(description: str, context: str) -> Optional[str]:
    """Call Gemini to generate a matplotlib script for a figure description."""
    settings = get_settings()
    client = genai.Client(api_key=settings.gemini_api_key)

    prompt = FIGURE_CODEGEN_USER.format(
        description=description,
        context=context,
    )

    try:
        response = client.models.generate_content(
            model=settings.gemini_model,
            contents=prompt,
            config=genai_types.GenerateContentConfig(
                system_instruction=FIGURE_CODEGEN_SYSTEM,
                temperature=0.2,
                max_output_tokens=2048,
            ),
        )

        code = response.text or ""
        code = code.strip()

        # Strip markdown fencing
        if code.startswith("```"):
            code = code[code.index("\n") + 1:]
        if code.endswith("```"):
            code = code[:-3].strip()

        return code if code else None

    except Exception as e:
        logger.error(f"Gemini figure codegen failed: {e}")
        return None


# ── Execution ──────────────────────────────────────────────────────────────────

def _run_matplotlib_script(
    code: str,
    output_path: Path,
    timeout: int = 15,
) -> bool:
    """Execute a generated matplotlib script in a subprocess.

    Injects the OUTPUT_PATH variable and runs the script.
    Returns True on success.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Inject the output path at the top
    full_code = f'OUTPUT_PATH = r"{str(output_path)}"\n\n' + textwrap.dedent(code)

    try:
        result = subprocess.run(
            [sys.executable, "-c", full_code],
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        if result.returncode != 0:
            logger.warning(
                f"Matplotlib script failed (exit {result.returncode}): "
                f"{result.stderr[:300]}"
            )
            return False

        if not output_path.exists():
            logger.warning("Matplotlib script ran but produced no output file")
            return False

        logger.info(f"Generated figure: {output_path}")
        return True

    except subprocess.TimeoutExpired:
        logger.warning(f"Matplotlib script timed out after {timeout}s")
        return False
    except Exception as e:
        logger.error(f"Failed to run matplotlib script: {e}")
        return False


# ── Public API ─────────────────────────────────────────────────────────────────

def generate_figure(
    description: str,
    context: str,
    output_path: Path,
) -> Optional[Path]:
    """Generate a matplotlib figure for a given description.

    Args:
        description: The figure description extracted from the exam text.
        context: Surrounding question text for better understanding.
        output_path: Where to save the generated PNG.

    Returns:
        The output_path if successful, None if generation failed.
    """
    logger.info(f"Generating figure for: {description[:60]}...")
    start = time.time()

    code = _generate_matplotlib_code(description, context)
    if not code:
        return None

    success = _run_matplotlib_script(code, output_path)
    elapsed = time.time() - start

    if success:
        logger.info(f"Figure generated in {elapsed:.1f}s -> {output_path}")
        return output_path
    else:
        logger.warning(f"Figure generation failed for: {description[:60]}")
        return None


def generate_figures_for_document(
    full_text: str,
    figures_dir: Path,
) -> list[dict]:
    """Scan a document and generate all detectable figures.

    Args:
        full_text: The full extracted text of the exam paper.
        figures_dir: Directory to save generated PNG images.

    Returns:
        List of dicts with 'description', 'image_path', and 'latex_key' for each
        successfully generated figure.
    """
    detected = extract_figure_descriptions(full_text)

    if not detected:
        logger.info("No figure references detected in document")
        return []

    logger.info(f"Detected {len(detected)} potential figures in document")
    results = []

    for i, fig in enumerate(detected):
        image_path = figures_dir / f"figure_{i + 1:02d}.png"
        generated = generate_figure(
            description=fig["description"],
            context=fig["context"],
            output_path=image_path,
        )

        if generated:
            results.append({
                "description": fig["description"],
                "image_path": str(generated),
                "latex_key": f"figure_{i + 1:02d}",
                "latex_include": (
                    f"\\begin{{figure}}[h!]\n"
                    f"  \\centering\n"
                    f"  \\includegraphics[width=0.7\\textwidth]{{{generated}}}\n"
                    f"  \\caption{{{fig['description']}}}\n"
                    f"\\end{{figure}}"
                ),
            })

    logger.info(f"Successfully generated {len(results)}/{len(detected)} figures")
    return results
