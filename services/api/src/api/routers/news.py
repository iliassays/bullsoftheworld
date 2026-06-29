"""A symbol's classified news/announcements for the News tab — descriptive, ranked by recency.

We serve the decoded `details` (EPS now/prior, dividend rate, record date, …) alongside the headline
so the frontend can render a trader-friendly card per locale. Low-importance "other" items (exchange
greetings, awareness notices, admin re-posts) are kept in the DB but hidden from this feed.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select

from api.deps import CurrentTenant, DbSession
from bulls.core.models import Announcement, Symbol

router = APIRouter(tags=["news"])

# Categories surfaced to users — material to a trader. "other" stays in the DB but is hidden here.
_SHOWN_CATEGORIES = (
    "dividend",
    "earnings",
    "board_meeting",
    "rating",
    "halt",
    "corporate_action",
    "insider",
    "psi",
)


class NewsOut(BaseModel):
    published_at: str
    category: str
    strength: int
    headline: str
    details: dict[str, Any] | None = None


@router.get("/symbols/{code}/news")
async def symbol_news(
    code: str, tenant: CurrentTenant, session: DbSession, limit: int = Query(40, le=100)
) -> list[NewsOut]:
    code = code.upper()
    if await session.get(Symbol, (tenant.market, code)) is None:
        raise HTTPException(status_code=404, detail=f"Unknown symbol {code!r}")
    rows = await session.scalars(
        select(Announcement)
        .where(
            Announcement.market == tenant.market,
            Announcement.code == code,
            Announcement.category.in_(_SHOWN_CATEGORIES),
        )
        .order_by(Announcement.published_at.desc(), Announcement.strength.desc())
        .limit(limit)
    )
    return [
        NewsOut(
            published_at=str(a.published_at),
            category=a.category,
            strength=a.strength,
            headline=a.headline,
            details=a.details,
        )
        for a in rows
    ]
