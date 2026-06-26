"""Discovery screener — top tickers per descriptive condition, as fast SQL over ticker_analytics.

Every screen is a computed FACT (RSI <= 30, close near support, positive money flow, ...), named by
the condition, never by implication. No advice, no AI — pure data the analytics scheduler persisted.
"""

from __future__ import annotations

import datetime as dt
from collections import defaultdict
from dataclasses import dataclass

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import ColumnElement, and_, func, select

from api.deps import CurrentTenant, DbSession, visible_codes
from api.routers.buzz import _MIN_BASELINE_DAYS, attention_label
from bulls.core.models import (
    Cashtag,
    Post,
    QuoteSnapshot,
    TickerAnalytics,
    TickerBuzzDaily,
    WatchlistItem,
)
from bulls.market_data.calendar import to_market_tz

router = APIRouter(tags=["screener"])

T = TickerAnalytics
PER_SCREEN = 8
_DISCUSSED_DAYS = 2  # window for "most discussed"
_BUZZ_HISTORY = 14  # look-back for the attention baseline

# Reused metric expressions
_PCT_ABOVE_SUPPORT = (T.last_close - T.nearest_support) / T.nearest_support * 100
_PCT_BELOW_RESISTANCE = (T.nearest_resistance - T.last_close) / T.last_close * 100
_PCT_ABOVE_200 = (T.last_close - T.sma_200) / T.sma_200 * 100


@dataclass
class ScreenSpec:
    key: str
    title: str
    description: str
    value_label: str
    where: ColumnElement[bool]
    order: ColumnElement
    value: ColumnElement


# Order here is the display order on the dashboard (structure → momentum → volume → trend → range).
_SCREENS: list[ScreenSpec] = [
    ScreenSpec(
        "near_support",
        "Near support",
        "Trading just above a support level",
        "% above support",
        and_(
            T.nearest_support.isnot(None),
            T.last_close >= T.nearest_support,
            T.last_close <= T.nearest_support * 1.03,
        ),
        _PCT_ABOVE_SUPPORT.asc(),
        _PCT_ABOVE_SUPPORT,
    ),
    ScreenSpec(
        "near_resistance",
        "Near resistance",
        "Approaching a resistance level",
        "% below resistance",
        and_(
            T.nearest_resistance.isnot(None),
            T.last_close <= T.nearest_resistance,
            T.last_close >= T.nearest_resistance * 0.97,
        ),
        _PCT_BELOW_RESISTANCE.asc(),
        _PCT_BELOW_RESISTANCE,
    ),
    ScreenSpec(
        "oversold",
        "Oversold (RSI ≤ 30)",
        "Low RSI — historically an oversold zone",
        "RSI",
        T.rsi_14 <= 30,
        T.rsi_14.asc(),
        T.rsi_14,
    ),
    ScreenSpec(
        "overbought",
        "Overbought (RSI ≥ 70)",
        "High RSI — historically an overbought zone",
        "RSI",
        T.rsi_14 >= 70,
        T.rsi_14.desc(),
        T.rsi_14,
    ),
    ScreenSpec(
        "accumulation",
        "Money flowing in",
        "Buying pressure — positive money flow",
        "CMF",
        T.cmf_20 > 0,
        T.cmf_20.desc(),
        T.cmf_20,
    ),
    ScreenSpec(
        "distribution",
        "Distribution",
        "Volume flowing out (negative money flow)",
        "CMF",
        T.cmf_20 < 0,
        T.cmf_20.asc(),
        T.cmf_20,
    ),
    ScreenSpec(
        "unusual_volume",
        "Unusual volume",
        "Trading well above its 20-day average",
        "x avg vol",
        T.relative_volume >= 1.5,
        T.relative_volume.desc(),
        T.relative_volume,
    ),
    ScreenSpec(
        "uptrend",
        "Above 200-day average",
        "In a longer-term uptrend",
        "% above 200-DMA",
        and_(T.above_sma_200.is_(True), T.sma_200.isnot(None)),
        _PCT_ABOVE_200.desc(),
        _PCT_ABOVE_200,
    ),
    ScreenSpec(
        "near_52w_high",
        "Near 52-week high",
        "Within 5% of the yearly high",
        "% from high",
        T.pct_from_52w_high >= -5,
        T.pct_from_52w_high.desc(),
        T.pct_from_52w_high,
    ),
    ScreenSpec(
        "near_52w_low",
        "Near 52-week low",
        "Within 5% of the yearly low",
        "% from low",
        and_(T.pct_from_52w_low.isnot(None), T.pct_from_52w_low <= 5),
        T.pct_from_52w_low.asc(),
        T.pct_from_52w_low,
    ),
    ScreenSpec(
        "dividend_yield",
        "Top dividend yield",
        "Highest cash dividend yield at today's price",
        "yield",
        T.dividend_yield > 0,
        T.dividend_yield.desc(),
        T.dividend_yield,
    ),
    ScreenSpec(
        "value_vs_sector",
        "Cheap vs sector",
        "P/E below the sector median",
        "x sector",
        and_(T.pe_vs_sector.isnot(None), T.pe_vs_sector < 0.8, T.pe_ratio > 0),
        T.pe_vs_sector.asc(),
        T.pe_vs_sector,
    ),
    ScreenSpec(
        "eps_growth",
        "Earnings growth",
        "EPS up year-on-year",
        "% YoY",
        T.eps_growth_yoy >= 15,
        T.eps_growth_yoy.desc(),
        T.eps_growth_yoy,
    ),
]

# Screen → display group. Anything unlisted defaults to 'technical' (collapsed in the UI).
_GROUP: dict[str, str] = {
    "top_gainers": "movers",
    "top_losers": "movers",
    "near_52w_high": "movers",
    "near_52w_low": "movers",
    "unusual_volume": "movers",
    "most_watched": "community",
    "most_discussed": "community",
    "attention_rising": "community",
    "dividend_yield": "value",
    "value_vs_sector": "value",
    "eps_growth": "value",
    "accumulation": "value",
}


class ScreenItem(BaseModel):
    code: str
    last_close: float
    value: float


class ScreenOut(BaseModel):
    key: str
    title: str
    description: str
    value_label: str
    group: str = "technical"  # movers | community | value | technical
    items: list[ScreenItem]


class ScreensResponse(BaseModel):
    as_of: str | None
    screens: list[ScreenOut]


async def _movers(session, market: str, *, gainers: bool) -> ScreenOut:
    order = QuoteSnapshot.change_pct.desc() if gainers else QuoteSnapshot.change_pct.asc()
    rows = (
        await session.execute(
            select(QuoteSnapshot.code, QuoteSnapshot.ltp, QuoteSnapshot.change_pct)
            .where(
                QuoteSnapshot.market == market,
                QuoteSnapshot.code.in_(visible_codes(market)),
            )
            .order_by(order)
            .limit(PER_SCREEN)
        )
    ).all()
    return ScreenOut(
        key="top_gainers" if gainers else "top_losers",
        title="Top gainers" if gainers else "Top losers",
        description="Biggest moves up today" if gainers else "Biggest moves down today",
        value_label="% today",
        group="movers",
        items=[ScreenItem(code=c, last_close=p, value=round(chg, 2)) for c, p, chg in rows],
    )


async def _last_closes(session, market: str, codes: list[str]) -> dict[str, float]:
    if not codes:
        return {}
    rows = (
        await session.execute(
            select(QuoteSnapshot.code, QuoteSnapshot.ltp).where(
                QuoteSnapshot.market == market, QuoteSnapshot.code.in_(codes)
            )
        )
    ).all()
    return {c: ltp for c, ltp in rows}


async def _most_discussed(session, market: str) -> ScreenOut:
    """Symbols with the most posts in the last couple of days (live, descriptive)."""
    since = dt.datetime.now(dt.UTC) - dt.timedelta(days=_DISCUSSED_DAYS)
    posts = func.count(func.distinct(Post.id))
    rows = (
        await session.execute(
            select(Cashtag.code, posts)
            .join(Post, Cashtag.post_id == Post.id)
            .where(
                Cashtag.market == market,
                Post.created_at >= since,
                Cashtag.code.in_(visible_codes(market)),
            )
            .group_by(Cashtag.code)
            .order_by(posts.desc())
            .limit(PER_SCREEN)
        )
    ).all()
    closes = await _last_closes(session, market, [c for c, _ in rows])
    return ScreenOut(
        key="most_discussed",
        title="Most discussed",
        description="Most posts in the last 2 days",
        value_label="posts",
        group="community",
        items=[ScreenItem(code=c, last_close=closes.get(c, 0.0), value=float(n)) for c, n in rows],
    )


async def _most_watched(session, market: str) -> ScreenOut:
    """Most-followed names — the community's 'Watchers' leaderboard."""
    cnt = func.count()
    rows = (
        await session.execute(
            select(WatchlistItem.code, cnt)
            .where(WatchlistItem.market == market, WatchlistItem.code.in_(visible_codes(market)))
            .group_by(WatchlistItem.code)
            .order_by(cnt.desc())
            .limit(PER_SCREEN)
        )
    ).all()
    closes = await _last_closes(session, market, [c for c, _ in rows])
    return ScreenOut(
        key="most_watched",
        title="Most watched",
        description="Most-followed by the community",
        value_label="watchers",
        group="community",
        items=[ScreenItem(code=c, last_close=closes.get(c, 0.0), value=float(n)) for c, n in rows],
    )


async def _attention_rising(session, market: str) -> ScreenOut:
    """Symbols whose chatter is well above their own usual pace, from the buzz snapshots."""
    today = to_market_tz(dt.datetime.now(dt.UTC)).date()
    rows = (
        await session.execute(
            select(TickerBuzzDaily.code, TickerBuzzDaily.date, TickerBuzzDaily.posts_24h).where(
                TickerBuzzDaily.market == market,
                TickerBuzzDaily.date >= today - dt.timedelta(days=_BUZZ_HISTORY),
                TickerBuzzDaily.code.in_(visible_codes(market)),
            )
        )
    ).all()
    series: dict[str, list[tuple[dt.date, int]]] = defaultdict(list)
    for code, d, posts in rows:
        series[code].append((d, posts))

    rising: list[tuple[str, float]] = []
    for code, points in series.items():
        points.sort()
        latest_date, latest_posts = points[-1]
        prior = [p for d, p in points if d < latest_date]
        baseline = sum(prior) / len(prior) if len(prior) >= _MIN_BASELINE_DAYS else None
        if baseline and attention_label(latest_posts, baseline) == "rising":
            rising.append((code, round(latest_posts / baseline, 1)))
    rising.sort(key=lambda x: -x[1])
    rising = rising[:PER_SCREEN]

    closes = await _last_closes(session, market, [c for c, _ in rising])
    return ScreenOut(
        key="attention_rising",
        title="Attention rising",
        description="Discussion well above its usual pace",
        value_label="x usual",
        group="community",
        items=[ScreenItem(code=c, last_close=closes.get(c, 0.0), value=x) for c, x in rising],
    )


@router.get("/screens")
async def screens(tenant: CurrentTenant, session: DbSession) -> ScreensResponse:
    out: list[ScreenOut] = []
    for spec in _SCREENS:
        rows = (
            await session.execute(
                select(T.code, T.last_close, spec.value)
                .where(
                    T.market == tenant.market,
                    spec.where,
                    T.code.in_(visible_codes(tenant.market)),
                )
                .order_by(spec.order)
                .limit(PER_SCREEN)
            )
        ).all()
        out.append(
            ScreenOut(
                key=spec.key,
                title=spec.title,
                description=spec.description,
                value_label=spec.value_label,
                group=_GROUP.get(spec.key, "technical"),
                items=[
                    ScreenItem(code=c, last_close=lc, value=round(v, 2))
                    for c, lc, v in rows
                    if v is not None
                ],
            )
        )

    out.append(await _movers(session, tenant.market, gainers=True))
    out.append(await _movers(session, tenant.market, gainers=False))
    out.append(await _most_watched(session, tenant.market))
    out.append(await _most_discussed(session, tenant.market))
    out.append(await _attention_rising(session, tenant.market))

    as_of = await session.scalar(select(T.as_of_date).where(T.market == tenant.market).limit(1))
    return ScreensResponse(as_of=str(as_of) if as_of else None, screens=out)
