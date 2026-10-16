"""Fast regression coverage for image and multipage refinement paths."""

from types import SimpleNamespace

import fitz
import pytest
from PIL import Image, ImageDraw

import pipeline.extractor as extractor_module
import pipeline.rewriter as rewriter_module
from pipeline.extractor import extract_text
from pipeline.preprocessor import preprocess
from pipeline.renderer import render
from pipeline.rewriter import rewrite
from pipeline.schemas import AnalysisResult, ExtractedMetadata


class _FakeGeminiModels:
    def generate_content(self, **_kwargs):
        return SimpleNamespace(
            text=(
                "<!DOCTYPE html><html><head><style>body{font-family:Arial;" 
                "margin:36px} h1{color:#234}</style></head><body>"
                "<h1>Refined study paper</h1><ol><li>Question one</li>"
                "<li>Question two</li></ol></body></html>"
            )
        )


class _FakeGeminiClient:
    def __init__(self, **_kwargs):
        self.models = _FakeGeminiModels()


@pytest.mark.parametrize("source_kind", ["image", "multipage_pdf"])
def test_single_image_and_multipage_pdf_reach_generated_pdf(tmp_path, monkeypatch, source_kind):
    """A successful AI response must produce a generated PDF, not fallback output."""
    source_dir = tmp_path / "source"
    source_dir.mkdir()

    if source_kind == "image":
        source_path = source_dir / "single-page.png"
        image = Image.new("RGB", (900, 1200), "white")
        ImageDraw.Draw(image).text((80, 90), "Question 1: Explain the method.", fill="black")
        image.save(source_path)
        # Image uploads normally use Gemini vision extraction.
        monkeypatch.setattr(
            extractor_module,
            "_extract_with_gemini",
            lambda _path: ("Question 1: Explain the method.", 0.92),
        )
        expected_pages = 1
    else:
        source_path = source_dir / "two-page.pdf"
        pdf = fitz.open()
        for page_number in (1, 2):
            page = pdf.new_page()
            page.insert_text((72, 90), f"Question {page_number}: Explain the method.")
        pdf.save(source_path)
        pdf.close()
        expected_pages = 2

    monkeypatch.setattr(rewriter_module.genai, "Client", _FakeGeminiClient)

    prepared = preprocess(source_path, tmp_path / "prepared")
    assert prepared.page_count == expected_pages
    assert len(prepared.pages) == expected_pages

    extraction = extract_text(prepared)
    assert extraction.total_word_count > 0

    analysis = AnalysisResult(
        document_type="text_only",
        metadata=ExtractedMetadata(title="Refined study paper"),
        questions=[],
        confidence=0.95,
    )
    rewritten = rewrite(extraction, analysis, tmp_path / "rewrite")
    assert rewritten.source_file_path
    assert rewritten.source_file_path.endswith("rewritten.html")

    rendered = render(rewritten, tmp_path / "render")
    assert rendered.pdf_path
    assert rendered.pdf_size_bytes > 0
    assert rendered.render_engine == "xhtml2pdf"
    with fitz.open(rendered.pdf_path) as rendered_pdf:
        assert rendered_pdf.page_count >= 1
