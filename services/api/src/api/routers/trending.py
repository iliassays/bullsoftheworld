"""Trending cashtags (SQL) + an AI 'Today's Watch' note.

Trending is a pure aggregation. Today's Watch ranks the day's movers/chatter in code, then the LLM
writes a grounded blurb naming them — cached daily (one model call for the whole platform/locale).
"""

from __future__ import annotations

import datetime as dt
import logging
from zoneinfo import ZoneInfo

import redis.asyncio as aioredis
from fastapi import APIRouter, Query
from pydantic import BaseModel
from sqlalchemy import case, func, select

from api.deps import CurrentTenant, DbSession
from api.i18n import language_for
from api.routers.screener import build_screen, sectors
from bulls.ai.tasks.watch import Breadth, WatchItem, todays_watch
from bulls.core.config import get_settings
from bulls.core.models import Cashtag, MarketSummary, Post, QuoteSnapshot
from bulls.market_data.calendar import Session, session_phase

router = APIRouter(tags=["trending"])
log = logging.getLogger(__name__)

WATCH_TTL = 21600  # 6h — Today's Watch is a slow-changing daily view


class WatchContent(BaseModel):
    """The daily-cached part of the brief (one model call per day per market/locale)."""

    summary: str
    items: list[WatchItem]
    breadth: Breadth | None = None


class WatchResponse(WatchContent):
    # session is time-of-day (tenant timezone), attached fresh on every request, not cached
    session: Session


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


async def _watch_extras(tenant: CurrentTenant, session: DbSession) -> list[str]:
    """Extra grounded facts for the watch note — turnover vs average, sector leaders, factor
    standouts. Best-effort: any part that fails is simply omitted (never breaks the note)."""
    market = tenant.market
    lines: list[str] = []

    # Is the move on real volume? Today's turnover vs its 20-day average.
    try:
        vals = list(
            await session.scalars(
                select(MarketSummary.total_value_mn)
                .where(MarketSummary.market == market, MarketSummary.total_value_mn.isnot(None))
                .order_by(MarketSummary.date.desc())
                .limit(20)
            )
        )
        if vals and vals[0]:
            avg = sum(vals) / len(vals)
            if avg:
                lines.append(
                    f"Turnover: Tk {vals[0] / 10:.0f} cr, {vals[0] / avg:.1f}x the 20-day average."
                )
    except Exception:
        log.warning("watch extras: turnover failed", exc_info=True)

    # Which sectors led / lagged.
    try:
        secs = await sectors(tenant, session)
        if len(secs) >= 2:
            top, bot = secs[0], secs[-1]
            lines.append(
                f"Sector leaders: {top.sector} {top.avg_change:+.1f}% avg; "
                f"laggard: {bot.sector} {bot.avg_change:+.1f}% avg."
            )
    except Exception:
        log.warning("watch extras: sectors failed", exc_info=True)

    # Factor standouts — the smart-money story beyond raw % moves.
    specs = [
        ("institutional_buying", lambda it: f"Institutions accumulating: {it.code} (+{it.value:g} pp)"),
        ("quiet_accumulation", lambda it: f"Quiet accumulation (money in, price flat): {it.code}"),
        ("momentum_12_1", lambda it: f"Strongest 12-month trend: {it.code} ({it.value:+.0f}%)"),
    ]
    facts: list[str] = []
    for key, fmt in specs:
        try:
            scr = await build_screen(session, market, key, 1)
            if scr and scr.items:
                facts.append(fmt(scr.items[0]))
        except Exception:
            log.warning("watch extras: %s failed", key, exc_info=True)
    if facts:
        lines.append("Standouts:")
        lines.extend(f"- {f}" for f in facts)
    return lines


@router.get("/todays-watch")
async def todays_watch_endpoint(tenant: CurrentTenant, session: DbSession) -> WatchResponse:
    now = dt.datetime.now(dt.UTC)
    phase = session_phase(now, ZoneInfo(tenant.timezone))
    cache_key = f"watch:v2:{tenant.market}:{tenant.locale}:{now.date()}"
    redis = aioredis.from_url(get_settings().redis_url)
    try:
        cached = await redis.get(cache_key)
        if cached:
            content = WatchContent.model_validate_json(cached)
        else:
            items = await _watch_items(session, tenant.market)
            breadth = await _breadth(session, tenant.market)
            extras = await _watch_extras(tenant, session)
            summary = await todays_watch(
                items, breadth=breadth, extras=extras, language=language_for(tenant.locale)
            )
            content = WatchContent(summary=summary, items=items, breadth=breadth)
            await redis.set(cache_key, content.model_dump_json(), ex=WATCH_TTL)
        return WatchResponse(**content.model_dump(), session=phase)
    finally:
        await redis.aclose()
