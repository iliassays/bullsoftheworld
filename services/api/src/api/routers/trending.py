"""Trending cashtags (SQL) + an AI 'Today's Watch' note.

Trending is a pure aggregation. Today's Watch ranks the day's movers/chatter in code, then the LLM
writes a grounded blurb naming them — cached daily (one model call for the whole platform/locale).
"""

from __future__ import annotations

import datetime as dt

import redis.asyncio as aioredis
from fastapi import APIRouter, Query
from pydantic import BaseModel
from sqlalchemy import case, func, select

from api.deps import CurrentTenant, DbSession
from api.i18n import language_for
from bulls.ai.tasks.watch import Breadth, WatchItem, todays_watch
from bulls.core.config import get_settings
from bulls.core.models import Cashtag, Post, QuoteSnapshot

router = APIRouter(tags=["trending"])

WATCH_TTL = 21600  # 6h — Today's Watch is a slow-changing daily view


class WatchResponse(BaseModel):
    summary: str
    items: list[WatchItem]
    breadth: Breadth | None = None


async def _breadth(session, market: str) -> Breadth:
    """Market-wide advancers/decliners from the latest quote snapshots."""
    adv = func.count(case((QuoteSnapshot.change_pct > 0, 1)))
    dec = func.count(case((QuoteSnapshot.change_pct < 0, 1)))
    unch = func.count(case((QuoteSnapshot.change_pct == 0, 1)))
    row = (
        await session.execute(
            select(adv, dec, unch, func.count()).where(QuoteSnapshot.market == market)
        )
    ).one()
    return Breadth(advancers=row[0], decliners=row[1], unchanged=row[2], total=row[3])


async def _trending(session, market: str, *, days: int, limit: int) -> list[WatchItem]:
    """Top cashtags by post count over the window, with sentiment tally + latest price move."""
    since = dt.datetime.now(dt.UTC) - dt.timedelta(days=days)
    bull = func.count(case((Post.sentiment == "bull", 1)))
    bear = func.count(case((Post.sentiment == "bear", 1)))
    stmt = (
        select(Cashtag.code, func.count(Post.id), bull, bear)
        .join(Post, Cashtag.post_id == Post.id)
        .where(Cashtag.market == market, Post.created_at >= since)
        .group_by(Cashtag.code)
        .order_by(func.count(Post.id).desc())
        .limit(limit)
    )
    rows = (await session.execute(stmt)).all()
    items = {
        code: WatchItem(code=code, change_pct=0.0, posts=n, bull=b, bear=br)
        for code, n, b, br in rows
    }
    # attach latest price move for those codes
    if items:
        quotes = await session.scalars(
            select(QuoteSnapshot).where(
                QuoteSnapshot.market == market, QuoteSnapshot.code.in_(list(items))
            )
        )
        for q in quotes:
            items[q.code].change_pct = q.change_pct
    return list(items.values())


@router.get("/trending")
async def trending(
    tenant: CurrentTenant,
    session: DbSession,
    days: int = Query(2, ge=1, le=30),
    limit: int = Query(10, ge=1, le=50),
) -> list[WatchItem]:
    return await _trending(session, tenant.market, days=days, limit=limit)


async def _watch_items(session, market: str) -> list[WatchItem]:
    """Merge trending chatter with the biggest price movers."""
    items = {it.code: it for it in await _trending(session, market, days=2, limit=6)}
    movers = await session.scalars(
        select(QuoteSnapshot)
        .where(QuoteSnapshot.market == market)
        .order_by(func.abs(QuoteSnapshot.change_pct).desc())
        .limit(5)
    )
    for q in movers:
        if q.code in items:
            items[q.code].change_pct = q.change_pct
        else:
            items[q.code] = WatchItem(code=q.code, change_pct=q.change_pct, posts=0, bull=0, bear=0)
    return list(items.values())[:8]


@router.get("/todays-watch")
async def todays_watch_endpoint(tenant: CurrentTenant, session: DbSession) -> WatchResponse:
    today = dt.datetime.now(dt.UTC).date()
    cache_key = f"watch:{tenant.market}:{tenant.locale}:{today}"
    redis = aioredis.from_url(get_settings().redis_url)
    try:
        cached = await redis.get(cache_key)
        if cached:
            return WatchResponse.model_validate_json(cached)
        items = await _watch_items(session, tenant.market)
        breadth = await _breadth(session, tenant.market)
        summary = await todays_watch(items, breadth=breadth, language=language_for(tenant.locale))
        resp = WatchResponse(summary=summary, items=items, breadth=breadth)
        await redis.set(cache_key, resp.model_dump_json(), ex=WATCH_TTL)
        return resp
    finally:
        await redis.aclose()
