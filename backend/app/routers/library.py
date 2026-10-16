"""Per-user library router: cloud-persisted saves, likes, view history,
collections, and one-shot import of guest (localStorage) data.

All endpoints require a signed-in user. Guest visitors keep using the
localStorage sandbox on the frontend.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.auth import AuthUser, get_current_user
from app.models import (
    ExamPaper,
    PaperLike,
    PaperSave,
    PaperStatus,
    PaperSummary,
    PaperView,
    UserCollection,
    UserCollectionItem,
)

logger = logging.getLogger(__name__)
router = APIRouter()


async def _paper_or_404(db: AsyncSession, paper_id: str) -> ExamPaper:
    paper = await db.get(ExamPaper, paper_id)
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
    return paper


async def _papers_by_join_time(
    db: AsyncSession, user_id: str, model, order_column, limit: int = 200
) -> list[ExamPaper]:
    result = await db.execute(
        select(ExamPaper)
        .join(model, model.paper_id == ExamPaper.id)
        .where(model.user_id == user_id, ExamPaper.status != PaperStatus.FAILED)
        .order_by(order_column.desc())
        .limit(limit)
    )
    return list(result.scalars().unique().all())


# ── Saved ───────────────────────────────────────────────────────────────────


@router.get("/library/saved", response_model=list[PaperSummary])
async def list_saved(
    user: AuthUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    return await _papers_by_join_time(db, user.id, PaperSave, PaperSave.created_at)


@router.post("/library/saves/{paper_id}/toggle")
async def toggle_save(
    paper_id: str,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _paper_or_404(db, paper_id)
    existing = await db.get(PaperSave, (user.id, paper_id))
    if existing:
        await db.delete(existing)
        saved = False
    else:
        db.add(PaperSave(user_id=user.id, paper_id=paper_id))
        saved = True
    paper = await db.get(ExamPaper, paper_id)
    if paper:
        paper.save_count = max(0, (paper.save_count or 0) + (1 if saved else -1))
    await db.commit()
    return {"saved": saved}


# ── Liked ───────────────────────────────────────────────────────────────────


@router.get("/library/liked", response_model=list[PaperSummary])
async def list_liked(
    user: AuthUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    return await _papers_by_join_time(db, user.id, PaperLike, PaperLike.created_at)


@router.post("/library/likes/{paper_id}/toggle")
async def toggle_like(
    paper_id: str,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _paper_or_404(db, paper_id)
    existing = await db.get(PaperLike, (user.id, paper_id))
    if existing:
        await db.delete(existing)
        liked = False
    else:
        db.add(PaperLike(user_id=user.id, paper_id=paper_id))
        liked = True
    paper = await db.get(ExamPaper, paper_id)
    if paper:
        paper.like_count = max(0, (paper.like_count or 0) + (1 if liked else -1))
    await db.commit()
    return {"liked": liked}


# ── View history ────────────────────────────────────────────────────────────


@router.get("/library/recent", response_model=list[PaperSummary])
async def list_recent(
    user: AuthUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    return await _papers_by_join_time(db, user.id, PaperView, PaperView.last_viewed_at, limit=50)


@router.post("/library/views/{paper_id}")
async def record_view(
    paper_id: str,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _paper_or_404(db, paper_id)
    view = await db.get(PaperView, (user.id, paper_id))
    if view:
        view.view_count = (view.view_count or 0) + 1
        view.last_viewed_at = datetime.now(timezone.utc)
    else:
        db.add(PaperView(user_id=user.id, paper_id=paper_id))
    await db.commit()
    return {"ok": True}


# ── Collections ─────────────────────────────────────────────────────────────


class CollectionCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)


@router.get("/library/collections")
async def list_collections(
    user: AuthUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(UserCollection)
        .where(UserCollection.user_id == user.id)
        .order_by(UserCollection.created_at.asc())
    )
    collections = result.scalars().all()
    payload = []
    for collection in collections:
        items = await db.execute(
            select(ExamPaper)
            .join(UserCollectionItem, UserCollectionItem.paper_id == ExamPaper.id)
            .where(UserCollectionItem.collection_id == collection.id)
            .order_by(UserCollectionItem.created_at.asc())
        )
        papers = list(items.scalars().unique().all())
        payload.append(
            {
                "id": collection.id,
                "name": collection.name,
                "paper_ids": [paper.id for paper in papers],
                "papers": papers,
            }
        )
    return payload


@router.post("/library/collections", status_code=201)
async def create_collection(
    request: CollectionCreateRequest,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    name = request.name.strip()
    existing = await db.execute(
        select(UserCollection).where(
            UserCollection.user_id == user.id, UserCollection.name == name
        )
    )
    collection = existing.scalars().first()
    if collection:
        return {"id": collection.id, "name": collection.name, "paper_ids": []}
    collection = UserCollection(user_id=user.id, name=name)
    db.add(collection)
    await db.commit()
    await db.refresh(collection)
    return {"id": collection.id, "name": collection.name, "paper_ids": []}


@router.delete("/library/collections/{collection_id}")
async def delete_collection(
    collection_id: str,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    collection = await db.get(UserCollection, collection_id)
    if not collection or collection.user_id != user.id:
        raise HTTPException(status_code=404, detail="Collection not found")
    await db.delete(collection)
    await db.commit()
    return {"ok": True}


@router.post("/library/collections/{collection_id}/items/{paper_id}")
async def add_to_collection(
    collection_id: str,
    paper_id: str,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    collection = await db.get(UserCollection, collection_id)
    if not collection or collection.user_id != user.id:
        raise HTTPException(status_code=404, detail="Collection not found")
    await _paper_or_404(db, paper_id)
    existing = await db.get(UserCollectionItem, (collection_id, paper_id))
    if not existing:
        db.add(UserCollectionItem(collection_id=collection_id, paper_id=paper_id))
        await db.commit()
    return {"ok": True}


@router.delete("/library/collections/{collection_id}/items/{paper_id}")
async def remove_from_collection(
    collection_id: str,
    paper_id: str,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    collection = await db.get(UserCollection, collection_id)
    if not collection or collection.user_id != user.id:
        raise HTTPException(status_code=404, detail="Collection not found")
    existing = await db.get(UserCollectionItem, (collection_id, paper_id))
    if existing:
        await db.delete(existing)
        await db.commit()
    return {"ok": True}


# ── Guest data import ───────────────────────────────────────────────────────


class GuestSnapshot(BaseModel):
    saved_ids: list[str] = Field(default_factory=list)
    liked_ids: list[str] = Field(default_factory=list)
    recent: list[dict] = Field(default_factory=list)  # [{id, viewed_at?}]
    collections: list[dict] = Field(default_factory=list)  # [{name, paper_ids}]


@router.post("/library/import")
async def import_guest_data(
    request: GuestSnapshot,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Merge localStorage guest data into the account. Idempotent: existing
    rows are kept as-is, only missing rows are added."""

    async def _existing_ids(paper_ids: list[str]) -> set[str]:
        if not paper_ids:
            return set()
        result = await db.execute(
            select(ExamPaper.id).where(ExamPaper.id.in_(paper_ids))
        )
        return {row[0] for row in result}

    imported = {"saved": 0, "liked": 0, "views": 0, "collections": 0, "skipped": 0}

    valid_saved = await _existing_ids(request.saved_ids)
    for paper_id in request.saved_ids:
        if paper_id not in valid_saved:
            imported["skipped"] += 1
            continue
        if not await db.get(PaperSave, (user.id, paper_id)):
            db.add(PaperSave(user_id=user.id, paper_id=paper_id))
            imported["saved"] += 1

    valid_liked = await _existing_ids(request.liked_ids)
    for paper_id in request.liked_ids:
        if paper_id not in valid_liked:
            imported["skipped"] += 1
            continue
        if not await db.get(PaperLike, (user.id, paper_id)):
            db.add(PaperLike(user_id=user.id, paper_id=paper_id))
            imported["liked"] += 1

    for entry in request.recent[:50]:
        paper_id = str(entry.get("id") or "")
        if not paper_id or paper_id not in await _existing_ids([paper_id]):
            imported["skipped"] += 1
            continue
        view = await db.get(PaperView, (user.id, paper_id))
        if view:
            view.view_count = (view.view_count or 0) + 1
            view.last_viewed_at = datetime.now(timezone.utc)
        else:
            db.add(PaperView(user_id=user.id, paper_id=paper_id))
            imported["views"] += 1

    for collection_data in request.collections[:20]:
        name = str(collection_data.get("name") or "").strip()[:80]
        if not name:
            continue
        existing = await db.execute(
            select(UserCollection).where(
                UserCollection.user_id == user.id, UserCollection.name == name
            )
        )
        collection = existing.scalars().first()
        if not collection:
            collection = UserCollection(user_id=user.id, name=name)
            db.add(collection)
            await db.flush()
            imported["collections"] += 1
        paper_ids = [str(pid) for pid in (collection_data.get("paper_ids") or [])][:100]
        valid_ids = await _existing_ids(paper_ids)
        for paper_id in paper_ids:
            if paper_id not in valid_ids:
                continue
            if not await db.get(UserCollectionItem, (collection.id, paper_id)):
                db.add(UserCollectionItem(collection_id=collection.id, paper_id=paper_id))

    await db.commit()
    return {"imported": imported}
