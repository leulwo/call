"""Local Ethiopian-universities knowledge base access.

Replaces per-upload web lookups with curated, offline reference data stored in
backend/knowledge/ethiopian_universities/. The INDEX.md alias table is parsed
once and cached; fuzzy matching resolves messy OCR/user spellings to canonical
university names. Matched university files are injected into the AI analyzer
prompt as grounding context.
"""

from __future__ import annotations

import logging
import re
from difflib import SequenceMatcher
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

KB_ROOT = Path(__file__).resolve().parent.parent / "knowledge" / "ethiopian_universities"

FUZZY_THRESHOLD = 0.82


def normalize_key(value: Any) -> str:
    """Stable key form — mirrors services.metadata_resolver.normalize_key."""
    text = str(value or "").strip().casefold()
    text = text.replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


@lru_cache(maxsize=1)
def _load_alias_index() -> tuple[tuple[str, str, str], ...]:
    """Parse INDEX.md rows into (alias_key, canonical_name, file_name) tuples."""
    index_path = KB_ROOT / "INDEX.md"
    if not index_path.is_file():
        logger.warning("Knowledge base index missing: %s", index_path)
        return ()
    entries = []
    pattern = re.compile(
        r"^\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*universities/([\w-]+\.md)\s*\|"
    )
    for line in index_path.read_text(encoding="utf-8").splitlines():
        match = pattern.match(line)
        if not match:
            continue
        alias_key = normalize_key(match.group(1))
        if alias_key:
            entries.append((alias_key, match.group(2), match.group(3)))
    logger.info("Knowledge base loaded %d aliases", len(entries))
    return tuple(entries)


@lru_cache(maxsize=None)
def _read_kb_file(file_name: str) -> Optional[str]:
    path = KB_ROOT / "universities" / file_name
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8")


def _type_from_file(file_name: str) -> Optional[str]:
    """Extract public/private from the university file's Type table row."""
    text = _read_kb_file(file_name) or ""
    match = re.search(r"\|\s*Type\s*\|\s*([^|]+)\|", text)
    if not match:
        return None
    raw = match.group(1).strip().lower()
    if "private" in raw:
        return "private"
    if "public" in raw:
        return "public"
    return None


def _similarity(a: str, b: str) -> float:
    """Blend edit similarity with token containment for OCR-style noise."""
    base = SequenceMatcher(None, a, b).ratio()
    tokens_a = set(a.split())
    tokens_b = set(b.split())
    score = base
    if tokens_a and tokens_a <= tokens_b:
        # Every input token appears in the alias ("addis ababa universty" case).
        score = max(score, 0.86)
    elif tokens_a & tokens_b:
        overlap = len(tokens_a & tokens_b) / len(tokens_a | tokens_b)
        score = max(score, overlap * 0.9)
    return score


def match_university(raw_value: Any) -> Optional[dict[str, Any]]:
    """Resolve a raw university string to a canonical KB entry.

    Returns a resolution dict compatible with metadata_resolver results, or
    None when nothing matches confidently.
    """
    query = normalize_key(raw_value)
    if not query:
        return None

    aliases = _load_alias_index()
    if not aliases:
        return None

    best_key, best_canonical, best_file, best_score = "", "", "", 0.0
    for alias_key, canonical, file_name in aliases:
        score = _similarity(query, alias_key)
        if score > best_score:
            best_key, best_canonical, best_file, best_score = (
                alias_key,
                canonical,
                file_name,
                score,
            )

    if best_score < FUZZY_THRESHOLD:
        return None

    confidence = min(0.98, 0.7 + best_score * 0.28)
    exact = best_score >= 0.999
    return {
        "canonical_value": best_canonical,
        "university_type": _type_from_file(best_file),
        "source": "knowledge_base",
        "confidence": 0.98 if exact else round(confidence, 2),
        "verified": True,
        "matched_alias": best_key,
        "match_score": round(best_score, 3),
        "knowledge_file": best_file,
    }


def university_context(resolution: Any) -> str:
    """Return the matched university's knowledge file content for prompt grounding.

    Accepts a resolution dict (with ``knowledge_file``) or a raw string that is
    matched on the fly. Falls back to the canonical-name lookup.
    """
    file_name: Optional[str] = None
    if isinstance(resolution, dict):
        file_name = resolution.get("knowledge_file")
        if not file_name:
            match = match_university(resolution.get("canonical_value"))
            file_name = match.get("knowledge_file") if match else None
    elif isinstance(resolution, str):
        match = match_university(resolution)
        file_name = match.get("knowledge_file") if match else None

    if not file_name:
        return ""

    text = (_read_kb_file(file_name) or "").strip()
    if not text:
        return ""
    return f"Matched via knowledge base ({file_name}).\n\n{text}"


def reload() -> None:
    """Drop caches so new/edited knowledge files are picked up."""
    _load_alias_index.cache_clear()
    _read_kb_file.cache_clear()
