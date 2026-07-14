"""Crowd-attention buzz for a symbol — current counts + baseline-relative trend.

Current values (watchers, last-24h posts/reactions/replies) are computed live so they're always
fresh. Trend values (chatter vs baseline, weekly watcher delta) come from the ticker_buzz_daily
snapshots and stay null until enough history has accrued — we never fabricate a baseline. Trends
are thresholded with absolute floors so a thin, easily-skewed signal reads as nothing rather than
"rising" (DSE's community is small). Descriptive attention, never a call to act.
"""

from __future__ import annotations

import datetime as dt
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select

from api.deps import CurrentTenant, DbSession
from bulls.core.models import (
    Cashtag,
    Post,
    PostReaction,
    Symbol,
    TickerBuzzDaily,
    User,
    WatchlistItem,
)
from bulls.market_data.calendar import to_market_tz

router = APIRouter(tags=["buzz"])

_WINDOW = dt.timedelta(hours=24)
_BASELINE_DAYS = 14  # look back this far for the chatter baseline
_MIN_BASELINE_DAYS = 3  # need at least this many snapshot days before a baseline is meaningful
_CHATTER_RISING = 2.0  # posts_24h / baseline at/above this reads as elevated
_POSTS_FLOOR = 5  # ...but only if there's a real number of posts behind it
_WATCHER_DELTA_FLOOR = 5  # show a watcher delta only if it moved by at least this many
_WATCHER_MIN = 20  # ...and there are enough watchers for the move to mean anything

Attention = Literal["rising", "normal", "quiet"]


class BuzzResponse(BaseModel):
    code: str
    watchers: int
    watchers_delta_7d: int | None = None
    posts_24h: int
    posts_baseline: float | None = None
    chatter_x: float | None = None
    attention: Attention | None = None
    reactions_24h: int
    replies_24h: int


def attention_label(posts_24h: int, baseline: float | None) -> Attention | None:
    """Descriptive attention from chatter-vs-baseline. None when we can't say (no baseline yet)."""
    if posts_24h == 0:
        return "quiet"
    if baseline is None:
        return None
    if baseline > 0 and posts_24h / baseline >= _CHATTER_RISING and posts_24h >= _POSTS_FLOOR:
        return "rising"
    return "normal"


def shown_watcher_delta(watchers: int, delta: int | None) -> int | None:
    """Suppress watcher deltas too small or off too thin a base to be meaningful."""
    if delta is None:
        return None
    if abs(delta) >= _WATCHER_DELTA_FLOOR and watchers >= _WATCHER_MIN:
        return delta
    return None


async def gather_buzz(session, market: str, code: str, *, tenant_id: str) -> BuzzResponse:
    """Compute a symbol's buzz: live current counts + thresholded baseline-relative trend.

    Shared by the /buzz endpoint and the digest so the attention signal is computed one way.
    """
    code = code.upper()
    now = dt.datetime.now(dt.UTC)
    since = now - _WINDOW
    today = to_market_tz(now, market=market).date()
    tagged = select(Cashtag.post_id).where(Cashtag.market == market, Cashtag.code == code)

    # current values — live, always fresh
    watchers = await session.scalar(
        select(func.count())
        .select_from(WatchlistItem)
        .join(User, User.id == WatchlistItem.user_id)
        .where(
            WatchlistItem.market == market,
            WatchlistItem.code == code,
            User.tenant_id == tenant_id,
        )
    )
    posts_24h = await session.scalar(
        select(func.count(func.distinct(Post.id)))
        .join(Cashtag, Cashtag.post_id == Post.id)
        .where(
            Cashtag.market == market,
            Cashtag.code == code,
            Post.tenant_id == tenant_id,
            Post.created_at >= since,
            Post.moderation_status == "published",
        )
    )
    reactions_24h = await session.scalar(
        select(func.count())
        .select_from(PostReaction)
        .join(Post, Post.id == PostReaction.post_id)
        .where(
            PostReaction.post_id.in_(tagged),
            Post.tenant_id == tenant_id,
            PostReaction.created_at >= since,
            Post.moderation_status == "published",
        )
    )
    replies_24h = await session.scalar(
        select(func.count()).where(
            Post.id.in_(tagged),
            Post.tenant_id == tenant_id,
            Post.parent_id.is_not(None),
            Post.created_at >= since,
            Post.moderation_status == "published",
        )
    )

    # baseline chatter — mean of prior days' posts from the snapshot history (excludes today)
    prior = list(
        await session.scalars(
            select(TickerBuzzDaily.posts_24h).where(
                TickerBuzzDaily.market == market,
                TickerBuzzDaily.tenant_id == tenant_id,
                TickerBuzzDaily.code == code,
                TickerBuzzDaily.date < today,
                TickerBuzzDaily.date >= today - dt.timedelta(days=_BASELINE_DAYS),
            )
        )
    )
    baseline = sum(prior) / len(prior) if len(prior) >= _MIN_BASELINE_DAYS else None
    chatter_x = round(posts_24h / baseline, 1) if baseline else None

    # weekly watcher delta — vs the snapshot closest to a week ago (5-9 days back)
    watchers_prev = await session.scalar(
        select(TickerBuzzDaily.watchers_total)
        .where(
            TickerBuzzDaily.market == market,
            TickerBuzzDaily.tenant_id == tenant_id,
            TickerBuzzDaily.code == code,
            TickerBuzzDaily.date <= today - dt.timedelta(days=5),
            TickerBuzzDaily.date >= today - dt.timedelta(days=9),
        )
        .order_by(TickerBuzzDaily.date.desc())
        .limit(1)
    )
    delta = watchers - watchers_prev if watchers_prev is not None else None

    return BuzzResponse(
        code=code,
        watchers=watchers,
        watchers_delta_7d=shown_watcher_delta(watchers, delta),
        posts_24h=posts_24h,
        posts_baseline=round(baseline, 1) if baseline else None,
        chatter_x=chatter_x,
        attention=attention_label(posts_24h, baseline),
        reactions_24h=reactions_24h,
        replies_24h=replies_24h,
    )


@router.get("/symbols/{code}/buzz")
async def get_buzz(code: str, tenant: CurrentTenant, session: DbSession) -> BuzzResponse:
    code = code.upper()
    symbol = await session.get(Symbol, (tenant.market, code))
    if symbol is None or not symbol.is_public_research:
        raise HTTPException(status_code=404, detail=f"Unknown symbol {code!r}")
    return await gather_buzz(session, tenant.market, code, tenant_id=tenant.name)
