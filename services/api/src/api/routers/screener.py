"""Discovery screener — top tickers per descriptive condition, as fast SQL over ticker_analytics.

Every screen is a computed FACT (RSI <= 30, close near support, positive money flow, ...), named by
the condition, never by implication. No advice, no AI — pure data the analytics scheduler persisted.
"""

from __future__ import annotations

import datetime as dt
from collections import defaultdict
from dataclasses import dataclass

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import ColumnElement, and_, case, func, or_, select

from api.deps import CurrentTenant, DbSession, visible_codes
from api.routers.buzz import _MIN_BASELINE_DAYS, attention_label
from bulls.core.models import (
    Cashtag,
    DailyBar,
    Post,
    QuoteSnapshot,
    Symbol,
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
# Combined rise in institutional + foreign holding (pp) since the last monthly disclosure.
_SMART_MONEY = func.coalesce(T.institute_delta, 0) + func.coalesce(T.foreign_delta, 0)

# --- Liquidity floor ---------------------------------------------------------
# Drop only names that are effectively UNTRADEABLE — near-zero turnover / suspended — where a signal
# is meaningless and you can't actually get in or out. This is a turnover floor, NOT a price floor:
# cheap penny stocks that retail actively trades have plenty of turnover and stay in. DSE retail
# loves low-priced names, so the bar is deliberately gentle (~97% of names clear it); it exists to
# weed out the dead/frozen tickers, not the cheap ones. Community screens (most watched / discussed)
# are NOT filtered at all — they reflect what the community actually follows.
_MIN_ADTV_MN = 0.5  # average daily turnover over 20 sessions, ৳ millions
_MIN_MCAP_MN = 100.0  # market capitalisation, ৳ millions

_LIQUID = and_(
    T.avg_volume_20.isnot(None),
    T.avg_volume_20 * T.last_close / 1e6 >= _MIN_ADTV_MN,
    func.coalesce(T.market_cap_mn, 0) >= _MIN_MCAP_MN,
)


def _investable(market: str):
    """Subquery of investable codes — visible AND liquid — for builders that don't query T."""
    return select(T.code).where(T.market == market, T.code.in_(visible_codes(market)), _LIQUID)


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
        # Cross-sectional rank: cheapest P/E relative to its sector (boundary = sector median, 1.0x),
        # not an arbitrary 0.8x cutoff.
        "value_vs_sector",
        "Cheap vs sector",
        "P/E below the sector median, cheapest first",
        "x sector",
        and_(T.pe_vs_sector.isnot(None), T.pe_vs_sector < 1.0, T.pe_ratio > 0),
        T.pe_vs_sector.asc(),
        T.pe_vs_sector,
    ),
    ScreenSpec(
        # Cross-sectional rank: highest YoY EPS growth (boundary = growing, >0), not a fixed 15%.
        "eps_growth",
        "Earnings growth",
        "EPS up year-on-year, fastest first",
        "% YoY",
        T.eps_growth_yoy > 0,
        T.eps_growth_yoy.desc(),
        T.eps_growth_yoy,
    ),
    ScreenSpec(
        "quality_roe",
        "High return on equity",
        "Most profit per taka of shareholder capital (ROE)",
        "ROE",
        and_(T.roe.isnot(None), T.roe > 0, T.roe <= 60),
        T.roe.desc(),
        T.roe,
    ),
    ScreenSpec(
        "low_volatility",
        "Steady (low volatility)",
        "Smallest day-to-day price swings over the past year",
        "volatility",
        and_(T.volatility.isnot(None), T.volatility > 0),
        T.volatility.asc(),
        T.volatility,
    ),
    ScreenSpec(
        "smart_money_buying",
        "Institutions & foreign buying",
        "Institutions or foreign investors raised their stake at the latest disclosure",
        "pp",
        _SMART_MONEY > 0,
        _SMART_MONEY.desc(),
        _SMART_MONEY,
    ),
]

# Screen → display group. Anything unlisted defaults to 'technical' (collapsed in the UI).
_GROUP: dict[str, str] = {
    "top_gainers": "movers",
    "top_losers": "movers",
    "most_active": "movers",
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
    "smart_money_buying": "value",
    "momentum_12_1": "movers",
    "quality_roe": "value",
    "low_volatility": "value",
}


class ScreenItem(BaseModel):
    code: str
    name: str = ""  # company short name, for readability
    last_close: float
    value: float
    change_1d: float | None = None  # today's % move, the universal anchor (None for movers)
    note: str | None = None  # optional per-row qualifier (e.g. momentum: steady vs pump-risk)
    spark: list[float] = []  # recent closes (oldest→newest) for an inline sparkline


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


async def _movers(session, market: str, *, gainers: bool, limit: int = PER_SCREEN) -> ScreenOut:
    order = QuoteSnapshot.change_pct.desc() if gainers else QuoteSnapshot.change_pct.asc()
    rows = (
        await session.execute(
            select(QuoteSnapshot.code, QuoteSnapshot.ltp, QuoteSnapshot.change_pct)
            .where(
                QuoteSnapshot.market == market,
                QuoteSnapshot.code.in_(_investable(market)),
            )
            .order_by(order)
            .limit(limit)
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


# Unusual-volume windows: a 1-day spike vs sustained week/month interest, each vs the stock's normal.
_RVOL_FIELD = {"1d": T.relative_volume, "5d": T.rel_volume_5d, "1m": T.rel_volume_1m}
_RVOL_MIN = {"1d": 1.5, "5d": 1.3, "1m": 1.2}  # sustained windows need a lower bar to qualify
_RVOL_DESC = {"1d": "today", "5d": "over the past week", "1m": "over the past month"}


def _vol_note(chg: float | None) -> str:
    """Pair the volume surge with price direction (today's % move): up = buying, down = selling."""
    if chg is not None and chg >= 0.5:
        return "Heavy buying"
    if chg is not None and chg <= -0.5:
        return "Heavy selling"
    return "Heavy volume"


async def _unusual_volume(
    session, market: str, *, window: str = "1d", limit: int = PER_SCREEN
) -> ScreenOut:
    """Stocks trading above their normal pace — as a 1-day spike or sustained week/month interest —
    tagged by today's price direction (heavy buying vs heavy selling)."""
    field = _RVOL_FIELD[window]
    rows = (
        await session.execute(
            select(T.code, T.last_close, field)
            .where(
                T.market == market,
                field >= _RVOL_MIN[window],
                T.code.in_(visible_codes(market)),
                _LIQUID,
            )
            .order_by(field.desc())
            .limit(limit)
        )
    ).all()
    changes = await _change_1d(session, market, [c for c, _, _ in rows])
    return ScreenOut(
        key="unusual_volume",
        title="Unusual volume",
        description=f"Trading well above its usual pace ({_RVOL_DESC[window]})",
        value_label="x avg vol",
        group="movers",
        items=[
            ScreenItem(code=c, last_close=lc, value=round(v, 2), note=_vol_note(changes.get(c)))
            for c, lc, v in rows
        ],
    )


async def _most_active(session, market: str, limit: int = PER_SCREEN) -> ScreenOut:
    """Most heavily traded by value today — DSE's classic 'top turnover' board. Surfaces where the
    money actually is, including the cheap, heavily-churned names retail follows."""
    turnover = QuoteSnapshot.volume * QuoteSnapshot.ltp
    rows = (
        await session.execute(
            select(QuoteSnapshot.code, QuoteSnapshot.ltp, turnover.label("t"))
            .where(QuoteSnapshot.market == market, QuoteSnapshot.code.in_(_investable(market)))
            .order_by(turnover.desc())
            .limit(limit)
        )
    ).all()
    return ScreenOut(
        key="most_active",
        title="Most active today",
        description="Most heavily traded by value today",
        value_label="turnover",
        group="movers",
        items=[ScreenItem(code=c, last_close=p, value=round(t / 1e7, 2)) for c, p, t in rows],
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


async def _most_discussed(session, market: str, limit: int = PER_SCREEN) -> ScreenOut:
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
            .limit(limit)
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


async def _most_watched(session, market: str, limit: int = PER_SCREEN) -> ScreenOut:
    """Most-followed names — the community's 'Watchers' leaderboard."""
    cnt = func.count()
    rows = (
        await session.execute(
            select(WatchlistItem.code, cnt)
            .where(WatchlistItem.market == market, WatchlistItem.code.in_(visible_codes(market)))
            .group_by(WatchlistItem.code)
            .order_by(cnt.desc())
            .limit(limit)
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


async def _attention_rising(session, market: str, limit: int = PER_SCREEN) -> ScreenOut:
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
    rising = rising[:limit]

    closes = await _last_closes(session, market, [c for c, _ in rising])
    return ScreenOut(
        key="attention_rising",
        title="Attention rising",
        description="Discussion well above its usual pace",
        value_label="x usual",
        group="community",
        items=[ScreenItem(code=c, last_close=closes.get(c, 0.0), value=x) for c, x in rising],
    )


# Momentum windows: which precomputed field + label per timeframe. 1-week / 1-month are deliberately
# absent — short horizons are reversal, not momentum, and are covered by Top gainers.
_MOM_FIELD = {"3m": T.mom_3_1, "6m": T.mom_6_1, "12m": T.mom_12_1}
_MOM_LABEL = {"3m": "3-month", "6m": "6-month", "12m": "12-month"}


def _mom_note(mom: float, vol: float | None, mcap: float | None) -> str:
    """A per-row read of the trend: parabolic/small-cap runs are flagged as possible pumps so the
    most dangerous name doesn't headline the board unqualified; otherwise steady vs volatile climb."""
    if mom >= 300 or (mom >= 150 and (mcap or 0) < 1000):
        return "⚠ Possible pump"
    if vol is not None and vol < 35:
        return "Steady climb"
    if vol is not None and vol > 50:
        return "Volatile climb"
    return "Climbing"


async def _momentum(
    session, market: str, *, window: str = "12m", limit: int = PER_SCREEN
) -> ScreenOut:
    """Volatility-scaled momentum over 3/6/12 months: rank by trend-per-unit-of-risk, show the return,
    and tag each row (steady / volatile / possible pump)."""
    mom = _MOM_FIELD[window]
    # Push likely pumps to the bottom (same rule as _mom_note) so steady trends headline the board.
    is_pump = case(
        (or_(mom >= 300, and_(mom >= 150, func.coalesce(T.market_cap_mn, 0) < 1000)), 1),
        else_=0,
    )
    rows = (
        await session.execute(
            select(T.code, T.last_close, mom, T.volatility, T.market_cap_mn)
            .where(
                T.market == market,
                mom > 0,
                T.volatility > 0,
                T.code.in_(visible_codes(market)),
                _LIQUID,
            )
            .order_by(is_pump.asc(), (mom / T.volatility).desc())
            .limit(limit)
        )
    ).all()
    return ScreenOut(
        key="momentum_12_1",
        title=f"Strongest trend ({_MOM_LABEL[window]})",
        description=(
            "Stocks in the strongest, steadiest uptrend over this window. We skip the last month "
            "(it often reverses) and reward steady climbs over wild ones."
        ),
        value_label="momentum",
        group="movers",
        items=[
            ScreenItem(code=c, last_close=lc, value=round(m, 2), note=_mom_note(m, vol, mc))
            for c, lc, m, vol, mc in rows
        ],
    )


async def _build_spec(session, market: str, spec: ScreenSpec, limit: int) -> ScreenOut:
    rows = (
        await session.execute(
            select(T.code, T.last_close, spec.value)
            .where(T.market == market, spec.where, T.code.in_(visible_codes(market)), _LIQUID)
            .order_by(spec.order)
            .limit(limit)
        )
    ).all()
    return ScreenOut(
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


async def _names(session, market: str, codes: list[str]) -> dict[str, str]:
    if not codes:
        return {}
    rows = (
        await session.execute(
            select(Symbol.code, Symbol.name_en).where(
                Symbol.market == market, Symbol.code.in_(codes)
            )
        )
    ).all()
    return {c: (n or "") for c, n in rows}


async def _change_1d(session, market: str, codes: list[str]) -> dict[str, float]:
    """Today's % move (last two daily closes) for a set of codes — EOD-consistent."""
    if not codes:
        return {}
    rn = (
        func.row_number()
        .over(partition_by=DailyBar.code, order_by=DailyBar.date.desc())
        .label("rn")
    )
    ranked = (
        select(DailyBar.code, DailyBar.close, rn)
        .where(DailyBar.market == market, DailyBar.code.in_(codes))
        .subquery()
    )
    cur = select(ranked.c.code, ranked.c.close.label("cur")).where(ranked.c.rn == 1).subquery()
    prev = select(ranked.c.code, ranked.c.close.label("prev")).where(ranked.c.rn == 2).subquery()
    chg = (cur.c.cur - prev.c.prev) / prev.c.prev * 100
    rows = (
        await session.execute(
            select(cur.c.code, chg).join(prev, cur.c.code == prev.c.code).where(prev.c.prev > 0)
        )
    ).all()
    return {c: round(v, 2) for c, v in rows}


# Top gainers/losers already carry the price change in their value, so the separate 1d column would
# be redundant. Every other screen (incl. unusual_volume, near 52w high/low) shows it.
_NO_1D = {"top_gainers", "top_losers"}
_SPARK_DAYS = 30  # closes per inline sparkline


async def _sparks(session, market: str, codes: list[str]) -> dict[str, list[float]]:
    """Last ~30 daily closes per code (oldest→newest) for an inline trend sparkline, batched."""
    if not codes:
        return {}
    rn = (
        func.row_number()
        .over(partition_by=DailyBar.code, order_by=DailyBar.date.desc())
        .label("rn")
    )
    ranked = (
        select(DailyBar.code, DailyBar.close, DailyBar.date, rn)
        .where(DailyBar.market == market, DailyBar.code.in_(codes))
        .subquery()
    )
    rows = (
        await session.execute(
            select(ranked.c.code, ranked.c.close)
            .where(ranked.c.rn <= _SPARK_DAYS)
            .order_by(ranked.c.code, ranked.c.date)
        )
    ).all()
    out: dict[str, list[float]] = defaultdict(list)
    for code, close in rows:
        out[code].append(round(close, 2))
    return out


async def _enrich(session, market: str, screens_list: list[ScreenOut]) -> None:
    """Fill name + 1d change + sparkline on every item, batched across all screens."""
    codes = sorted({it.code for s in screens_list for it in s.items})
    names = await _names(session, market, codes)
    skip = {it.code for s in screens_list if s.key in _NO_1D for it in s.items}
    changes = await _change_1d(session, market, sorted(set(codes) - skip))
    sparks = await _sparks(session, market, codes)
    for s in screens_list:
        for it in s.items:
            it.name = names.get(it.code, "")
            it.change_1d = None if s.key in _NO_1D else changes.get(it.code)
            it.spark = sparks.get(it.code, [])


_SPEC_BY_KEY = {s.key: s for s in _SCREENS}


async def build_screen(session, market: str, key: str, limit: int) -> ScreenOut | None:
    """Build a single screen by key (used by the detail/explore page)."""
    if key in ("top_gainers", "top_losers"):
        return await _movers(session, market, gainers=key == "top_gainers", limit=limit)
    if key == "most_active":
        return await _most_active(session, market, limit=limit)
    if key == "momentum_12_1":
        return await _momentum(session, market, limit=limit)
    if key == "unusual_volume":
        return await _unusual_volume(session, market, limit=limit)
    if key == "most_watched":
        return await _most_watched(session, market, limit=limit)
    if key == "most_discussed":
        return await _most_discussed(session, market, limit=limit)
    if key == "attention_rising":
        return await _attention_rising(session, market, limit=limit)
    spec = _SPEC_BY_KEY.get(key)
    return await _build_spec(session, market, spec, limit) if spec else None


@router.get("/screens")
async def screens(tenant: CurrentTenant, session: DbSession) -> ScreensResponse:
    out: list[ScreenOut] = [
        await _build_spec(session, tenant.market, spec, PER_SCREEN) for spec in _SCREENS
    ]
    out.append(await _movers(session, tenant.market, gainers=True))
    out.append(await _movers(session, tenant.market, gainers=False))
    out.append(await _most_active(session, tenant.market))
    out.append(await _momentum(session, tenant.market))
    out.append(await _unusual_volume(session, tenant.market))
    out.append(await _most_watched(session, tenant.market))
    out.append(await _most_discussed(session, tenant.market))
    out.append(await _attention_rising(session, tenant.market))

    await _enrich(session, tenant.market, out)
    as_of = await session.scalar(select(T.as_of_date).where(T.market == tenant.market).limit(1))
    return ScreensResponse(as_of=str(as_of) if as_of else None, screens=out)


_PERIOD_DAYS = {"1d": 1, "5d": 5, "7d": 7, "15d": 15, "1m": 22}  # trading-days back for movers


async def _movers_period(
    session, market: str, *, gainers: bool, days: int, limit: int
) -> ScreenOut:
    """Top gainers/losers over a trailing window, from the daily bars (EOD-consistent)."""
    rn = (
        func.row_number()
        .over(partition_by=DailyBar.code, order_by=DailyBar.date.desc())
        .label("rn")
    )
    ranked = (
        select(DailyBar.code, DailyBar.close, rn)
        .where(DailyBar.market == market, DailyBar.code.in_(_investable(market)))
        .subquery()
    )
    cur = select(ranked.c.code, ranked.c.close.label("cur")).where(ranked.c.rn == 1).subquery()
    old = (
        select(ranked.c.code, ranked.c.close.label("old")).where(ranked.c.rn == days + 1).subquery()
    )
    chg = (cur.c.cur - old.c.old) / old.c.old * 100
    rows = (
        await session.execute(
            select(cur.c.code, cur.c.cur, chg.label("chg"))
            .join(old, cur.c.code == old.c.code)
            .where(old.c.old > 0)
            .order_by(chg.desc() if gainers else chg.asc())
            .limit(limit)
        )
    ).all()
    return ScreenOut(
        key="top_gainers" if gainers else "top_losers",
        title="Top gainers" if gainers else "Top losers",
        description=f"Biggest {'gains' if gainers else 'falls'} over {days} trading day(s)",
        value_label="% period",
        group="movers",
        items=[ScreenItem(code=c, last_close=p, value=round(chg, 2)) for c, p, chg in rows],
    )


@router.get("/screens/{key}")
async def screen_detail(
    key: str,
    tenant: CurrentTenant,
    session: DbSession,
    limit: int = Query(50, le=200),
    period: str | None = Query(None, description="movers only: 1d | 5d | 1m"),
    window: str | None = Query(None, description="momentum only: 3m | 6m | 12m"),
) -> ScreenOut:
    """One screen's full list — for the explore page's tab view."""
    if key in ("top_gainers", "top_losers") and period in _PERIOD_DAYS:
        screen = await _movers_period(
            session,
            tenant.market,
            gainers=key == "top_gainers",
            days=_PERIOD_DAYS[period],
            limit=limit,
        )
    elif key == "momentum_12_1":
        screen = await _momentum(
            session, tenant.market, window=window if window in _MOM_FIELD else "12m", limit=limit
        )
    elif key == "unusual_volume":
        screen = await _unusual_volume(
            session, tenant.market, window=period if period in _RVOL_FIELD else "1d", limit=limit
        )
    else:
        screen = await build_screen(session, tenant.market, key, limit)
    if screen is None:
        raise HTTPException(status_code=404, detail=f"Unknown screen {key!r}")
    await _enrich(session, tenant.market, [screen])
    return screen
