"""Symbol digest — "what's happening with $X".

Deterministic and templated, like the levels card. The facts (price stats + sentiment tally) are
computed in code, then rendered into fixed, hand-translated sentences — never written by an LLM.
A small local model mistranslated finance terms, dropped wrong units (e.g. "points" for a share
price), and editorialized ("only 7 posts"); a template can't drift, mis-unit, or misadvise.
"""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from api.deps import CurrentLocale, CurrentTenant, DbSession, enforce_market_feature
from api.routers.buzz import BuzzResponse, gather_buzz
from api.routers.market import load_freshest_quotes
from bulls.ai.tasks.digest import SymbolFacts, crowd_mood
from bulls.analytics import adjust_bars, compute
from bulls.core.markets import get_market_profile
from bulls.core.models import Cashtag, DailyBar, Post, Symbol

router = APIRouter(tags=["digest"])

_FLAT = 0.1  # |1-session move| at or below this (%) reads as "little changed", not up/down


class DigestResponse(BaseModel):
    code: str
    summary: str
    mood: str
    posts: int
    change_pct_1d: float


async def _gather_facts(
    session, market: str, code: str, *, tenant_id: str
) -> SymbolFacts | None:
    symbol = await session.get(Symbol, (market, code))
    if symbol is None or not symbol.is_retail_ready:
        return None

    bars = list(
        await session.scalars(
            select(DailyBar)
            .where(DailyBar.market == market, DailyBar.code == code)
            .order_by(DailyBar.date.desc())
            .limit(260)  # enough for the 200-day SMA the analytics engine needs
        )
    )
    profile = get_market_profile(market)
    quote = (await load_freshest_quotes(session, market, [code], profile.tz)).get(code)

    # Deterministic technicals from the analytics engine (descriptive facts the LLM can weave in).
    ta = compute(adjust_bars(list(reversed(bars)))) if bars else None

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
            .where(
                Post.id.in_(tagged),
                Post.tenant_id == tenant_id,
                Post.created_at >= since,
                Post.moderation_status == "published",
            )
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
        rsi_14=ta.rsi_14 if ta else None,
        above_sma_50=ta.above_sma_50 if ta else None,
        above_sma_200=ta.above_sma_200 if ta else None,
        nearest_support=ta.nearest_support if ta else None,
        nearest_resistance=ta.nearest_resistance if ta else None,
        pct_from_52w_high=ta.pct_from_52w_high if ta else None,
    )


def _rel_volume(f: SymbolFacts) -> float | None:
    if not f.avg_volume_5d:
        return None
    return f.last_volume / f.avg_volume_5d


def _head(f: SymbolFacts) -> str:
    # Avoid "GP (GP)" when the display name is just the ticker code.
    return f.name if f.name.upper() == f.code.upper() else f"{f.name} ({f.code})"


def _attention_extras_en(buzz: BuzzResponse | None) -> list[str]:
    # Only when the buzz thresholds are already cleared; descriptive, never causal.
    extras: list[str] = []
    if buzz and buzz.attention == "rising" and buzz.chatter_x:
        extras.append(f"discussion is running about {buzz.chatter_x:g}x heavier than usual")
    if buzz and buzz.watchers_delta_7d and buzz.watchers_delta_7d > 0:
        extras.append(f"watchers are up {buzz.watchers_delta_7d} this week")
    return extras


def _render_digest_en(
    f: SymbolFacts,
    buzz: BuzzResponse | None = None,
    currency: str = "৳",
    *,
    eod: bool = False,
) -> str:
    def move(pct: float) -> str:
        if pct > _FLAT:
            return f"rose {pct:.2f}%"
        if pct < -_FLAT:
            return f"fell {abs(pct):.2f}%"
        return f"was little changed ({pct:+.2f}%)"

    delayed = " (delayed)" if f.is_delayed else ""
    period = "in the latest session" if eod else "today"
    parts = [
        f"{_head(f)} {move(f.change_pct_1d)} {period} to {currency}{f.last_price:g}{delayed}."
    ]
    if f.change_pct_5d is not None:
        parts.append(f"Over the last 5 sessions it {move(f.change_pct_5d)}.")
    rel = _rel_volume(f)
    if rel is not None:
        parts.append(f"Volume ran {rel:.1f}x its 5-day average.")
    total = f.bull_posts + f.bear_posts + f.neutral_posts
    if total == 0:
        parts.append("No posts about it in the last 7 days.")
    else:
        lean = {
            "bullish": "leans bullish",
            "bearish": "leans bearish",
            "mixed": "is split",
            "quiet": "is quiet",
        }[crowd_mood(f.bull_posts, f.bear_posts, f.neutral_posts)]
        parts.append(
            f"Across {total} posts this week the crowd {lean} ({f.bull_posts}▲ / {f.bear_posts}▼)."
        )
    extras = _attention_extras_en(buzz)
    if extras:
        s = " and ".join(extras)
        parts.append(s[0].upper() + s[1:] + ".")
    return " ".join(parts)


def _attention_extras_bn(buzz: BuzzResponse | None) -> list[str]:
    extras: list[str] = []
    if buzz and buzz.attention == "rising" and buzz.chatter_x:
        extras.append(f"আলোচনা স্বাভাবিকের চেয়ে প্রায় {buzz.chatter_x:g} গুণ বেশি হচ্ছে")
    if buzz and buzz.watchers_delta_7d and buzz.watchers_delta_7d > 0:
        extras.append(f"এই সপ্তাহে {buzz.watchers_delta_7d} জন বেশি ওয়াচ করছেন")
    return extras


def _render_digest_bn(
    f: SymbolFacts,
    buzz: BuzzResponse | None = None,
    currency: str = "৳",
    *,
    eod: bool = False,
) -> str:
    def move(pct: float) -> str:
        if pct > _FLAT:
            return f"{pct:.2f}% বেড়েছে"
        if pct < -_FLAT:
            return f"{abs(pct):.2f}% কমেছে"
        return f"প্রায় অপরিবর্তিত ({pct:+.2f}%)"

    delayed = " (বিলম্বিত)" if f.is_delayed else ""
    period = "সর্বশেষ সেশনে" if eod else "আজ"
    parts = [f"{_head(f)} {period} {move(f.change_pct_1d)}, দর {currency}{f.last_price:g}{delayed}।"]
    if f.change_pct_5d is not None:
        parts.append(f"গত ৫ সেশনে {move(f.change_pct_5d)}।")
    rel = _rel_volume(f)
    if rel is not None:
        parts.append(f"লেনদেনের পরিমাণ ৫-দিনের গড়ের {rel:.1f} গুণ।")
    total = f.bull_posts + f.bear_posts + f.neutral_posts
    if total == 0:
        parts.append("গত সপ্তাহে এ নিয়ে কোনো পোস্ট নেই।")
    else:
        lean = {
            "bullish": "চাঙা",
            "bearish": "মন্দা",
            "mixed": "মিশ্র",
            "quiet": "শান্ত",
        }[crowd_mood(f.bull_posts, f.bear_posts, f.neutral_posts)]
        parts.append(
            f"গত সপ্তাহে {total}টি পোস্টে আলোচকদের ঝোঁক {lean} ({f.bull_posts}▲ / {f.bear_posts}▼)।"
        )
    extras = _attention_extras_bn(buzz)
    if extras:
        parts.append("; ".join(extras) + "।")
    return " ".join(parts)


@router.get("/symbols/{code}/digest")
async def get_digest(
    code: str, tenant: CurrentTenant, session: DbSession, locale: CurrentLocale
) -> DigestResponse:
    enforce_market_feature(tenant, "interpreted_analytics")
    code = code.upper()
    facts = await _gather_facts(session, tenant.market, code, tenant_id=tenant.name)
    if facts is None:
        raise HTTPException(status_code=404, detail=f"Unknown symbol {code!r}")

    buzz = await gather_buzz(session, tenant.market, code, tenant_id=tenant.name)
    render = _render_digest_bn if locale == "bn" else _render_digest_en
    return DigestResponse(
        code=code,
        summary=render(
            facts,
            buzz,
            get_market_profile(tenant.market).currency_symbol,
            eod=not get_market_profile(tenant.market).features.intraday_quotes,
        ),
        mood=crowd_mood(facts.bull_posts, facts.bear_posts, facts.neutral_posts),
        posts=facts.bull_posts + facts.bear_posts + facts.neutral_posts,
        change_pct_1d=facts.change_pct_1d,
    )
