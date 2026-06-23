"""AI symbol digest — "what's happening with $X".

Computes the facts (price stats + sentiment tally) in code, lets the LLM only write the prose,
and caches the result in Redis (digests are expensive; identical views shouldn't re-run the model).
"""

from __future__ import annotations

import datetime as dt

import redis.asyncio as aioredis
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from api.deps import CurrentTenant, DbSession
from api.i18n import language_for
from bulls.ai.tasks.digest import SymbolFacts, crowd_mood, summarize_symbol
from bulls.core.config import get_settings
from bulls.core.models import Cashtag, DailyBar, Post, QuoteSnapshot, Symbol

router = APIRouter(tags=["digest"])

CACHE_TTL = 600  # seconds — one digest per symbol per 10 min


class DigestResponse(BaseModel):
    code: str
    summary: str
    mood: str
    posts: int
    change_pct_1d: float


async def _gather_facts(session, market: str, code: str) -> SymbolFacts | None:
    symbol = await session.get(Symbol, (market, code))
    if symbol is None:
        return None

    bars = list(
        await session.scalars(
            select(DailyBar)
            .where(DailyBar.market == market, DailyBar.code == code)
            .order_by(DailyBar.date.desc())
            .limit(6)
        )
    )
    quote = await session.get(QuoteSnapshot, (market, code))

    last_price = quote.ltp if quote else (bars[0].close if bars else 0.0)
    change_1d = quote.change_pct if quote else 0.0
    last_vol = quote.volume if quote else (bars[0].volume if bars else 0)
    is_delayed = quote.is_delayed if quote else True

    change_5d = None
    avg_vol_5d = None
    if len(bars) >= 6 and bars[5].close:
        change_5d = round((bars[0].close - bars[5].close) / bars[5].close * 100, 2)
    if len(bars) >= 2:
        recent = bars[1:6]  # prior sessions
        avg_vol_5d = int(sum(b.volume for b in recent) / len(recent))

    # crowd sentiment over the last 7 days
    since = dt.datetime.now(dt.UTC) - dt.timedelta(days=7)
    tagged = select(Cashtag.post_id).where(Cashtag.market == market, Cashtag.code == code)
    posts = list(
        await session.scalars(
            select(Post)
            .where(Post.id.in_(tagged), Post.created_at >= since)
            .order_by(Post.created_at.desc())
            .limit(40)
        )
    )
    bull = sum(p.sentiment == "bull" for p in posts)
    bear = sum(p.sentiment == "bear" for p in posts)
    neutral = len(posts) - bull - bear

    return SymbolFacts(
        code=code,
        name=symbol.name_en,
        last_price=last_price,
        change_pct_1d=change_1d,
        change_pct_5d=change_5d,
        last_volume=last_vol,
        avg_volume_5d=avg_vol_5d,
        bull_posts=bull,
        bear_posts=bear,
        neutral_posts=neutral,
        sample_posts=[p.body[:160] for p in posts[:3]],
        is_delayed=is_delayed,
    )


@router.get("/symbols/{code}/digest")
async def get_digest(code: str, tenant: CurrentTenant, session: DbSession) -> DigestResponse:
    code = code.upper()
    cache_key = f"digest:{tenant.market}:{code}:{tenant.locale}"
    redis = aioredis.from_url(get_settings().redis_url)
    try:
        cached = await redis.get(cache_key)
        if cached:
            return DigestResponse.model_validate_json(cached)

        facts = await _gather_facts(session, tenant.market, code)
        if facts is None:
            raise HTTPException(status_code=404, detail=f"Unknown symbol {code!r}")

        summary = await summarize_symbol(facts, language=language_for(tenant.locale))
        resp = DigestResponse(
            code=code,
            summary=summary,
            mood=crowd_mood(facts.bull_posts, facts.bear_posts, facts.neutral_posts),
            posts=facts.bull_posts + facts.bear_posts + facts.neutral_posts,
            change_pct_1d=facts.change_pct_1d,
        )
        await redis.set(cache_key, resp.model_dump_json(), ex=CACHE_TTL)
        return resp
    finally:
        await redis.aclose()
