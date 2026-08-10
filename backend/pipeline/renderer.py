"""ExamPaper Refine - Renderer stage.

Converts rewritten source files (LaTeX, HTML) into final PDF output.

Engines:
  • HTML → PDF:  WeasyPrint (pure Python, no external deps)
  • LaTeX → PDF: subprocess call to pdflatex or tectonic (must be installed)
"""

from __future__ import annotations

import logging
import os
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Optional

from pipeline.schemas import RenderResult, RewriteResult

logger = logging.getLogger(__name__)


def _render_html_to_pdf(html_content: str, output_path: Path) -> dict:
    """Render HTML to PDF using xhtml2pdf.

    Returns metadata dict with page_count and engine info.
    """
    from xhtml2pdf import pisa

    with open(output_path, "wb") as result_file:
        pisa_status = pisa.CreatePDF(
            src=html_content,
            dest=result_file
        )

    # Note: xhtml2pdf doesn't easily return page counts, so we return 0 for now.
    return {
        "engine": "xhtml2pdf",
        "page_count": 0,
    }


def _find_latex_engine() -> Optional[str]:
    """Find an available LaTeX engine on the system.
    
    Checks PATH first, then falls back to known Windows installation directories
    for MiKTeX and TeX Live.
    """
    import platform

    # Candidate engine names (tried in order)
    engine_names = ["tectonic", "pdflatex", "xelatex", "lualatex"]

    # Known Windows install paths to probe when not on PATH
    windows_search_dirs = []
    if platform.system() == "Windows":
        import os
        local_appdata = os.environ.get("LOCALAPPDATA", "")
        windows_search_dirs = [
            # MiKTeX per-user install (winget default)
            rf"{local_appdata}\Programs\MiKTeX\miktex\bin\x64",
            rf"{local_appdata}\Programs\MiKTeX\miktex\bin",
            # MiKTeX system-wide install
            r"C:\Program Files\MiKTeX\miktex\bin\x64",
            r"C:\Program Files\MiKTeX\miktex\bin",
            # TeX Live
            r"C:\texlive\2024\bin\windows",
            r"C:\texlive\2023\bin\windows",
        ]

    def _try_engine(cmd: str) -> bool:
        """Return True if the command exists and runs successfully."""
        try:
            result = subprocess.run(
                [cmd, "--version"],
                capture_output=True,
                timeout=10,
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            return False

    # 1. Check PATH first
    for name in engine_names:
        if _try_engine(name):
            logger.info(f"Found LaTeX engine on PATH: {name}")
            return name

    # 2. Check known install directories
    for search_dir in windows_search_dirs:
        from pathlib import Path as _Path
        for name in engine_names:
            full_path = str(_Path(search_dir) / (name + ".exe"))
            if _try_engine(full_path):
                logger.info(f"Found LaTeX engine at: {full_path}")
                return full_path

    return None


def _render_latex_to_pdf(
    latex_content: str,
    output_path: Path,
    engine: Optional[str] = None,
) -> dict:
    """Render LaTeX to PDF using an available engine.

    Falls back to HTML rendering if no LaTeX engine is installed.
    """
    engine = engine or _find_latex_engine()

    if not engine:
        logger.warning(
            "No LaTeX engine found (tectonic/pdflatex). "
            "Falling back to HTML wrapper rendering."
        )
        return _render_latex_as_html_fallback(latex_content, output_path)

    # Write LaTeX to a temp directory and compile
    with tempfile.TemporaryDirectory() as tmpdir:
        tex_path = Path(tmpdir) / "document.tex"
        tex_path.write_text(latex_content, encoding="utf-8")

        # Build command based on engine
        if engine == "tectonic":
            cmd = [engine, str(tex_path)]
        else:
            # pdflatex / xelatex / lualatex
            cmd = [
                engine,
                "-interaction=nonstopmode",
                "-output-directory", tmpdir,
                str(tex_path),
            ]

        logger.info(f"Compiling LaTeX with {engine}...")

        try:
            # Run twice for references/TOC (standard practice)
            for pass_num in range(2):
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=120,
                    cwd=tmpdir,
                )
                if result.returncode != 0 and pass_num == 1:
                    logger.error(f"LaTeX compilation failed:\n{result.stderr[:2000]}")
                    logger.debug(f"LaTeX stdout:\n{result.stdout[:2000]}")
                    # Try fallback
                    return _render_latex_as_html_fallback(latex_content, output_path)

            # Find the output PDF
            pdf_file = Path(tmpdir) / "document.pdf"
            if not pdf_file.exists():
                logger.error("LaTeX compiled but no PDF was produced")
                return _render_latex_as_html_fallback(latex_content, output_path)

            # Copy to final location
            import shutil
            shutil.copy2(str(pdf_file), str(output_path))

            # Count pages (rough: check with PyMuPDF)
            page_count = 0
            try:
                import pymupdf as fitz
                doc = fitz.open(str(output_path))
                page_count = len(doc)
                doc.close()
            except Exception:
                pass

            return {
                "engine": engine,
                "page_count": page_count,
            }

        except subprocess.TimeoutExpired:
            logger.error("LaTeX compilation timed out")
            return _render_latex_as_html_fallback(latex_content, output_path)


def _render_latex_as_html_fallback(latex_content: str, output_path: Path) -> dict:
    """Fallback: wrap LaTeX source in a styled HTML page and render to PDF.

    This is a last resort when no LaTeX engine is available. It produces
    a readable PDF but without proper math typesetting.
    """
    logger.info("Using HTML fallback for LaTeX rendering")

    html = f"""\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<style>
    @page {{
        size: A4;
        margin: 2.5cm;
    }}
    body {{
        font-family: "Times New Roman", "DejaVu Serif", Georgia, serif;
        font-size: 11pt;
        line-height: 1.6;
        color: #1a1a1a;
    }}
    pre {{
        font-family: "Courier New", monospace;
        font-size: 9pt;
        white-space: pre-wrap;
        word-wrap: break-word;
        background: #f8f8f8;
        padding: 1em;
        border: 1px solid #ddd;
        border-radius: 4px;
    }}
    .notice {{
        background: #fff3cd;
        border: 1px solid #ffc107;
        padding: 0.8em;
        margin-bottom: 1.5em;
        border-radius: 4px;
        font-size: 9pt;
        color: #856404;
    }}
</style>
</head>
<body>
<div class="notice">
    ⚠ This document was generated without a LaTeX engine. Math formatting
    may not render correctly. Install <code>tectonic</code> or
    <code>pdflatex</code> for proper typesetting.
</div>
<pre>{_escape_html(latex_content)}</pre>
</body>
</html>"""

    return _render_html_to_pdf(html, output_path)


def _escape_html(text: str) -> str:
    """Escape HTML special characters."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def render(
    rewrite_result: RewriteResult,
    output_dir: Path,
) -> RenderResult:
    """Render the rewritten source into a final PDF.

    Args:
        rewrite_result: Output from the rewriter stage.
        output_dir: Directory to save the final PDF.

    Returns:
        RenderResult with the PDF path and metadata.
    """
    start = time.time()
    warnings: list[str] = []

    if not rewrite_result.source_content:
        return RenderResult(
            pdf_path="",
            render_engine="none",
            processing_time_seconds=time.time() - start,
            warnings=["No source content to render"],
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = output_dir / "final.pdf"

    fmt = rewrite_result.format_chosen

    try:
        if fmt == "latex":
            meta = _render_latex_to_pdf(rewrite_result.source_content, pdf_path)
        elif fmt in ("html", "markdown"):
            meta = _render_html_to_pdf(rewrite_result.source_content, pdf_path)
        else:
            warnings.append(f"Unknown format '{fmt}', using HTML renderer")
            meta = _render_html_to_pdf(rewrite_result.source_content, pdf_path)
    except Exception as e:
        logger.error(f"Rendering failed: {e}")
        return RenderResult(
            pdf_path="",
            render_engine="failed",
            processing_time_seconds=time.time() - start,
            warnings=[f"Render failed: {e}"],
        )

    pdf_size = pdf_path.stat().st_size if pdf_path.exists() else 0

    elapsed = time.time() - start
    logger.info(
        f"Rendered PDF: {pdf_size / 1024:.1f}KB, "
        f"engine={meta['engine']}, "
        f"pages={meta.get('page_count', '?')}, "
        f"{elapsed:.1f}s"
    )

    return RenderResult(
        pdf_path=str(pdf_path),
        pdf_size_bytes=pdf_size,
        render_engine=meta["engine"],
        processing_time_seconds=round(elapsed, 3),
        page_count=meta.get("page_count", 0),
        warnings=warnings,
    )
