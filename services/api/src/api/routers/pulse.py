"""Pulse gauges for the symbol Overview — crowd sentiment, message volume, participation.

Three descriptive dials (each 0-100 + a label) computed from the community's activity, reusing the
buzz computation for volume. Counts only — no prediction, no advice.
"""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select

from api.deps import CurrentTenant, DbSession
from api.routers.buzz import gather_buzz
from bulls.ai.tasks.digest import crowd_mood
from bulls.core.models import Cashtag, Post, Symbol

router = APIRouter(tags=["pulse"])

_WINDOW = dt.timedelta(days=7)


class Gauge(BaseModel):
    score: int  # 0-100 for the dial
    label: str


class PulseResponse(BaseModel):
    code: str
    sentiment: Gauge
    message_volume: Gauge
    participation: Gauge


def sentiment_gauge(bull: int, bear: int, neutral: int) -> Gauge:
    """0 = all bearish, 50 = neutral/none, 100 = all bullish."""
    directional = bull + bear
    score = 50 if directional == 0 else round(50 + 50 * (bull - bear) / directional)
    return Gauge(score=score, label=crowd_mood(bull, bear, neutral))


def volume_gauge(posts_24h: int, chatter_x: float | None) -> Gauge:
    """Relative to the stock's own usual chatter when we have a baseline, else absolute."""
    if posts_24h == 0:
        return Gauge(score=0, label="quiet")
    raw = chatter_x * 33 if chatter_x else posts_24h * 10
    score = max(0, min(100, round(raw)))
    label = "high" if score >= 66 else "low" if score <= 25 else "normal"
    return Gauge(score=score, label=label)


_MIN_FOR_PARTICIPATION = 5  # below this there isn't enough chatter to judge diversity of voices


def participation_gauge(unique_authors: int, total_posts: int) -> Gauge:
    """Diversity of voices = unique authors per message (low = a few accounts dominate).

    Only meaningful with enough chatter: 1-2 posts trivially score 100% ("every message is a
    different person"), which is noise — so below a small floor we report 'quiet', not 'high'.
    """
    if total_posts < _MIN_FOR_PARTICIPATION:
        return Gauge(score=0, label="quiet")
    score = round(unique_authors / total_posts * 100)
    label = "high" if score >= 70 else "low" if score < 35 else "normal"
    return Gauge(score=score, label=label)


@router.get("/symbols/{code}/pulse")
async def get_pulse(code: str, tenant: CurrentTenant, session: DbSession) -> PulseResponse:
    code = code.upper()
    if await session.get(Symbol, (tenant.market, code)) is None:
        raise HTTPException(status_code=404, detail=f"Unknown symbol {code!r}")

    since = dt.datetime.now(dt.UTC) - _WINDOW
    tagged = select(Cashtag.post_id).where(Cashtag.market == tenant.market, Cashtag.code == code)
    row = (
        await session.execute(
            select(
                func.count(func.distinct(Post.id)),
                func.count(func.distinct(Post.author_id)),
                func.count(func.distinct(Post.id)).filter(Post.sentiment == "bull"),
                func.count(func.distinct(Post.id)).filter(Post.sentiment == "bear"),
            ).where(
                Post.id.in_(tagged),
                Post.created_at >= since,
                Post.moderation_status == "published",
            )
        )
    ).one()
    total, authors, bull, bear = (int(x) for x in row)
    neutral = total - bull - bear

    buzz = await gather_buzz(session, tenant.market, code)
    return PulseResponse(
        code=code,
        sentiment=sentiment_gauge(bull, bear, neutral),
        message_volume=volume_gauge(buzz.posts_24h, buzz.chatter_x),
        participation=participation_gauge(authors, total),
    )
