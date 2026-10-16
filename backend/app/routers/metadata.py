"""Dynamic metadata suggestions for the upload form."""

from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import ExamPaper, MetadataResolution
from services.metadata_resolver import normalize_key

router = APIRouter()

MetadataField = Literal[
    "university",
    "department",
    "course_code",
    "course_name",
]


@router.get("/metadata/suggestions")
async def metadata_suggestions(
    field: MetadataField,
    query: str = Query("", max_length=200),
    db: AsyncSession = Depends(get_db),
):
    """Return suggestions learned from uploaded metadata and resolved matches.

    The website does not need a hardcoded university directory for upload.
    Suggestions grow from actual library metadata and verified resolutions.
    """
    query_key = normalize_key(query)
    column = getattr(ExamPaper, field)
    values: set[str] = set()

    result = await db.execute(
        select(column)
        .where(column.is_not(None))
        .distinct()
        .limit(500)
    )
    values.update(str(value).strip() for (value,) in result.all() if str(value).strip())

    cached = await db.execute(
        select(MetadataResolution.canonical_value)
        .where(MetadataResolution.field == field)
        .distinct()
        .limit(500)
    )
    values.update(str(value).strip() for (value,) in cached.all() if str(value).strip())

    suggestions = sorted(
        (value for value in values if not query_key or query_key in normalize_key(value)),
        key=lambda value: (normalize_key(value) != query_key, normalize_key(value)),
    )
    return {"field": field, "query": query, "suggestions": suggestions[:20]}
