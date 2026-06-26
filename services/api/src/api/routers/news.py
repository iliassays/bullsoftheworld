"""A symbol's classified news/announcements for the News tab — descriptive, ranked by recency."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select

from api.deps import CurrentTenant, DbSession
from bulls.core.models import Announcement, Symbol

router = APIRouter(tags=["news"])


class NewsOut(BaseModel):
    published_at: str
    category: str
    strength: int
    headline: str


@router.get("/symbols/{code}/news")
async def symbol_news(
    code: str, tenant: CurrentTenant, session: DbSession, limit: int = Query(40, le=100)
) -> list[NewsOut]:
    code = code.upper()
    if await session.get(Symbol, (tenant.market, code)) is None:
        raise HTTPException(status_code=404, detail=f"Unknown symbol {code!r}")
    rows = await session.scalars(
        select(Announcement)
        .where(Announcement.market == tenant.market, Announcement.code == code)
        .order_by(Announcement.published_at.desc(), Announcement.strength.desc())
        .limit(limit)
    )
    return [
        NewsOut(
            published_at=str(a.published_at),
            category=a.category,
            strength=a.strength,
            headline=a.headline,
        )
        for a in rows
    ]
