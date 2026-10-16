"""AI adjudication of abuse/removal reports.

When a reader requests removal of a document, Gemini reviews the report
against the document's own content and decides:
  • remove        — clear policy violation / wrong / harmful content
  • keep          — report looks mistaken or abusive
  • human_review  — genuinely ambiguous; surface to the owner
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from google import genai
from google.genai import types as genai_types

from app.config import get_settings

logger = logging.getLogger(__name__)

ADJUDICATION_SYSTEM_PROMPT = """\
You are a content moderation reviewer for PaperFlow, an academic document
library where university students share exam papers and study material.

You will receive a removal report (reason + details) and a summary of the
reported document. Decide what should happen:

- "remove": the document clearly violates policy — it is not a real academic
  document, it infringes copyright in an obvious way, it contains harmful,
  dangerous, hateful, or sexually explicit content, or it exposes private
  personal data.
- "keep": the report appears mistaken, malicious, frivolous, or the described
  problem is minor/subjective (e.g. someone dislikes the course).
- "human_review": the evidence is genuinely ambiguous or the stakes are high.

Be conservative: only order removal when the report clearly justifies it.
Respond with ONLY a JSON object:
{"decision": "remove" | "keep" | "human_review", "confidence": 0.0-1.0,
 "note": "one-paragraph justification citing the report and the document"}
"""


def adjudicate_removal(
    reason: str,
    details: Optional[str],
    document_summary: str,
) -> dict:
    """Ask Gemini to adjudicate a removal report.

    Returns {"decision": str, "confidence": float, "note": str}; on any
    failure the decision defaults to "human_review" so nothing is silently
    removed without a human looking at it.
    """
    settings = get_settings()
    fallback = {
        "decision": "human_review",
        "confidence": 0.0,
        "note": "Automatic adjudication unavailable; a human should review this report.",
    }
    try:
        client = genai.Client(api_key=settings.gemini_api_key)
        prompt = (
            f"REMOVAL REPORT\nReason: {reason}\n"
            f"Details: {details or '(none provided)'}\n\n"
            f"DOCUMENT SUMMARY\n{document_summary[:6000]}\n"
        )
        response = client.models.generate_content(
            model=settings.gemini_model,
            contents=prompt,
            config=genai_types.GenerateContentConfig(
                system_instruction=ADJUDICATION_SYSTEM_PROMPT,
                temperature=0.1,
                response_mime_type="application/json",
                max_output_tokens=2048,
            ),
        )
        raw = (response.text or "").strip()
        if raw.startswith("```"):
            raw = raw[raw.index("\n") + 1:]
        if raw.endswith("```"):
            raw = raw[:-3].strip()
        data = json.loads(raw)
        decision = str(data.get("decision", "")).lower()
        if decision not in {"remove", "keep", "human_review"}:
            return fallback
        return {
            "decision": decision,
            "confidence": float(data.get("confidence", 0.5)),
            "note": str(data.get("note", ""))[:2000],
        }
    except Exception as exc:
        logger.error(f"Removal adjudication failed: {exc}")
        return fallback
