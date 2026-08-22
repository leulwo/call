"""Resolve detailed upload metadata without slowing down the upload request.

The browser sends the user's complete metadata context as JSON. This service
keeps that raw context, resolves common aliases immediately, checks values
already present in the PaperFlow library, and only then performs a best-effort
web lookup for an uncached value.
"""

from __future__ import annotations

import html
import json
import logging
import re
from copy import deepcopy
from typing import Any, Optional

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ExamPaper, MetadataResolution

logger = logging.getLogger(__name__)

RESOLVABLE_FIELDS = ("university", "department", "course_code", "course_name")
WEB_FIELDS = {"university", "department", "course_code", "course_name"}


def normalize_key(value: Any) -> str:
    """Create a stable key for aliases, cache entries, and comparisons."""
    text = str(value or "").strip().casefold()
    text = text.replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def clean_value(value: Any) -> Optional[str]:
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


def _strip_html(value: str) -> str:
    return re.sub(r"<[^>]+>", " ", html.unescape(value or ""))


async def _cached_or_library_value(
    db: AsyncSession,
    field: str,
    query_key: str,
) -> Optional[dict[str, Any]]:
    cached = await db.execute(
        select(MetadataResolution)
        .where(
            MetadataResolution.field == field,
            MetadataResolution.query_key == query_key,
        )
        .limit(1)
    )
    cached_row = cached.scalars().first()
    if cached_row:
        return {
            "canonical_value": cached_row.canonical_value,
            "university_type": cached_row.university_type,
            "source": cached_row.source,
            "confidence": cached_row.confidence,
            "verified": cached_row.source != "user",
        }

    column = getattr(ExamPaper, field, None)
    if column is None:
        return None

    result = await db.execute(
        select(column)
        .where(column.is_not(None))
        .distinct()
        .limit(250)
    )
    for (value,) in result.all():
        if normalize_key(value) == query_key:
            return {
                "canonical_value": value,
                "university_type": None,
                "source": "library",
                "confidence": 0.95,
                "verified": True,
            }
    return None


async def _web_match(
    field: str,
    raw_value: str,
    context_query: str,
    university: Optional[str],
) -> Optional[dict[str, Any]]:
    """Use Wikipedia's public search endpoint as a conservative lookup.

    This is a fallback for genuinely new values only. A strict title/snippet
    check prevents an unrelated search result from silently replacing input.
    """
    if field not in WEB_FIELDS:
        return None

    suffix = " university college institute" if field == "university" else ""
    context = f" {university}" if university and field != "university" else ""
    query = f"{raw_value}{suffix}{context} {context_query}".strip()

    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(5.0),
            headers={"User-Agent": "PaperFlow metadata resolver/1.0"},
            follow_redirects=True,
        ) as client:
            response = await client.get(
                "https://en.wikipedia.org/w/api.php",
                params={
                    "action": "query",
                    "list": "search",
                    "srsearch": query,
                    "format": "json",
                    "utf8": "1",
                    "srlimit": "5",
                },
            )
            response.raise_for_status()
            items = response.json().get("query", {}).get("search", [])
    except Exception as exc:
        logger.info("Metadata web lookup unavailable for %s=%r: %s", field, raw_value, exc)
        return None

    raw_key = normalize_key(raw_value)
    raw_tokens = [token for token in raw_key.split() if len(token) > 2]
    candidates: list[tuple[int, dict[str, Any]]] = []

    for item in items:
        title = str(item.get("title") or "").strip()
        snippet = _strip_html(str(item.get("snippet") or ""))
        title_key = normalize_key(title)
        haystack = normalize_key(f"{title} {snippet}")

        if field == "university" and not re.search(
            r"university|college|institute|school", title, re.IGNORECASE
        ):
            continue

        token_hits = sum(token in haystack for token in raw_tokens)
        exact_phrase = raw_key and raw_key in title_key
        if field != "university" and not exact_phrase and token_hits < max(1, len(raw_tokens)):
            continue
        if field == "university" and not exact_phrase and token_hits < max(1, len(raw_tokens) // 2):
            continue

        score = token_hits * 10 + (30 if exact_phrase else 0)
        university_type = None
        if field == "university":
            if re.search(r"public|state[- ]owned|government", haystack, re.IGNORECASE):
                university_type = "public"
            elif re.search(r"private", haystack, re.IGNORECASE):
                university_type = "private"
        candidates.append(
            (
                score,
                {
                    "canonical_value": title,
                    "university_type": university_type,
                    "source": "wikipedia",
                    "confidence": min(0.95, 0.65 + score / 200),
                    "verified": True,
                    "source_url": f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}",
                    "snippet": snippet[:500],
                },
            )
        )

    return max(candidates, key=lambda item: item[0])[1] if candidates else None


async def _resolve_value(
    db: AsyncSession,
    field: str,
    raw_value: str,
    *,
    context_query: str,
    university: Optional[str],
    allow_web_lookup: bool,
) -> dict[str, Any]:
    query_key = normalize_key(raw_value)
    if not query_key:
        return {"canonical_value": raw_value, "source": "empty", "verified": False}

    result = await _cached_or_library_value(db, field, query_key)
    if result is None and allow_web_lookup:
        result = await _web_match(field, raw_value, context_query, university)

    if result is None:
        return {
            "canonical_value": raw_value,
            "source": "user",
            "confidence": None,
            "verified": False,
        }

    result["raw_value"] = raw_value
    result["query_key"] = query_key
    if result.get("source") in {"alias", "library", "wikipedia"}:
        existing = await db.execute(
            select(MetadataResolution)
            .where(
                MetadataResolution.field == field,
                MetadataResolution.query_key == query_key,
            )
            .limit(1)
        )
        if existing.scalars().first() is None:
            db.add(
                MetadataResolution(
                    field=field,
                    query_key=query_key,
                    raw_value=raw_value,
                    canonical_value=result["canonical_value"],
                    university_type=result.get("university_type"),
                    source=result["source"],
                    confidence=result.get("confidence"),
                    payload=json.dumps(result, ensure_ascii=False),
                )
            )
    return result


async def cache_ai_resolutions(
    db: AsyncSession,
    provided: dict[str, Any],
    normalized: dict[str, Any],
) -> None:
    """Cache AI-confirmed canonical values for future uploads.

    This is deliberately data-driven: the first successful refinement teaches
    PaperFlow how to map the exact user spelling next time. No university or
    course directory is embedded in the application.
    """
    for field in RESOLVABLE_FIELDS:
        raw_value = clean_value(provided.get(field))
        canonical_value = clean_value(normalized.get(field))
        if not raw_value or not canonical_value:
            continue
        query_key = normalize_key(raw_value)
        existing = await db.execute(
            select(MetadataResolution)
            .where(
                MetadataResolution.field == field,
                MetadataResolution.query_key == query_key,
            )
            .limit(1)
        )
        row = existing.scalars().first()
        if row:
            row.canonical_value = canonical_value
            row.source = "ai"
            row.confidence = max(row.confidence or 0.0, 0.9)
            row.payload = json.dumps(
                {"canonical_value": canonical_value, "source": "ai", "verified": True},
                ensure_ascii=False,
            )
            continue
        db.add(
            MetadataResolution(
                field=field,
                query_key=query_key,
                raw_value=raw_value,
                canonical_value=canonical_value,
                source="ai",
                confidence=0.9,
                payload=json.dumps(
                    {"canonical_value": canonical_value, "source": "ai", "verified": True},
                    ensure_ascii=False,
                ),
            )
        )


async def resolve_metadata_context(
    db: AsyncSession,
    metadata_envelope: dict[str, Any],
    *,
    allow_web_lookup: bool = False,
) -> dict[str, Any]:
    """Resolve a detailed upload context while retaining every raw input."""
    provided = metadata_envelope.get("provided", metadata_envelope)
    if not isinstance(provided, dict):
        provided = {}
    provided = {
        key: clean_value(provided.get(key))
        for key in (
            "title",
            "description",
            "university",
            "university_type",
            "study_year",
            "department",
            "course_code",
            "course_name",
            "year",
        "semester",
        "exam_type",
        )
        if clean_value(provided.get(key)) is not None
    }
    context_query = clean_value(metadata_envelope.get("context_query")) or ""

    resolved = deepcopy(provided)
    resolutions: dict[str, Any] = {}
    for field in RESOLVABLE_FIELDS:
        raw_value = provided.get(field)
        if not raw_value:
            continue
        resolution = await _resolve_value(
            db,
            field,
            raw_value,
            context_query=context_query,
            university=provided.get("university"),
            allow_web_lookup=allow_web_lookup,
        )
        resolutions[field] = resolution
        resolved[field] = resolution.get("canonical_value") or raw_value
        if field == "university" and resolution.get("university_type") and provided.get("university_type") in (None, "", "other"):
            resolved["university_type"] = resolution["university_type"]

    if provided.get("university_type") == "other" and resolved.get("university_type") == "other":
        resolved["university_type"] = "unknown"

    return {
        "schema_version": "paperflow.metadata.v1",
        "context_query": context_query,
        "provided": provided,
        "resolved": resolved,
        "resolutions": resolutions,
        "unresolved": [
            field for field, resolution in resolutions.items()
            if not resolution.get("verified")
        ],
        "external_lookup_used": any(
            resolution.get("source") == "wikipedia"
            for resolution in resolutions.values()
        ),
    }
