"""Discovery screener — top tickers per descriptive condition, as fast SQL over ticker_analytics.

Every screen is a computed FACT (RSI <= 30, close near support, positive money flow, ...), named by
the condition, never by implication. No advice, no AI — pure data the analytics scheduler persisted.
"""

from __future__ import annotations

import datetime as dt
from collections import defaultdict
from dataclasses import dataclass

import redis.asyncio as aioredis
from fastapi import APIRouter, HTTPException, Query, Response
from pydantic import BaseModel
from sqlalchemy import ColumnElement, and_, case, func, or_, select

from api.deps import CurrentTenant, DbSession, visible_codes
from api.routers.buzz import _MIN_BASELINE_DAYS, attention_label
from bulls.analytics.indicators import index_change_pct
from bulls.core.config import get_settings
from bulls.core.models import (
    Announcement,
    Cashtag,
    DailyBar,
    MarketSummary,
    Post,
    QuoteSnapshot,
    ShareholdingSnapshot,
    Symbol,
    TickerAnalytics,
    TickerBuzzDaily,
    User,
    WatchlistItem,
)
from bulls.market_data.calendar import to_market_tz

router = APIRouter(tags=["screener"])

T = TickerAnalytics
PER_SCREEN = 8
_DISCUSSED_DAYS = 2  # window for "most discussed"
_BUZZ_HISTORY = 14  # look-back for the attention baseline
DSE_SETTLEMENT_CYCLE = "T+2"

# Reused metric expressions
_PCT_ABOVE_SUPPORT = (T.last_close - T.nearest_support) / T.nearest_support * 100
_PCT_BELOW_RESISTANCE = (T.nearest_resistance - T.last_close) / T.last_close * 100
_PCT_ABOVE_200 = (T.last_close - T.sma_200) / T.sma_200 * 100

# --- Institutional liquidity floor ------------------------------------------
# DSE screens should surface names a real desk can plausibly trade without dominating the tape. This
# is still a discovery floor, not a full capacity model: execution sizing, spread and impact checks
# belong in the next layer. Z-category names stay out of default investable screens; community screens
# are tenant-filtered, but not liquidity/category-filtered.
_MIN_ADTV_MN = 5.0  # average daily turnover over 20 sessions, ৳ millions (~৳50 lakh/day)
_MIN_MCAP_MN = 500.0  # market capitalisation, ৳ millions (~৳50 crore)
_MIN_FREE_FLOAT_CAP_MN = 100.0  # applied when available, ৳ millions
_MATERIAL_ANNOUNCEMENT_CATEGORIES = (
    "dividend",
    "earnings",
    "board_meeting",
    "rating",
    "halt",
    "corporate_action",
    "insider",
    "psi",
)

_LIQUID = and_(
    T.last_close > 0,
    T.avg_volume_20.isnot(None),
    T.avg_volume_20 > 0,
    T.avg_volume_20 * T.last_close / 1e6 >= _MIN_ADTV_MN,
    func.coalesce(T.market_cap_mn, 0) >= _MIN_MCAP_MN,
    or_(T.free_float_cap_mn.is_(None), T.free_float_cap_mn >= _MIN_FREE_FLOAT_CAP_MN),
)


def _screenable_codes(market: str):
    """Visible codes eligible for default Market screens.

    DSE Z-category names are left out of the investable discovery boards. They can still appear in
    community attention widgets, where the product is showing what users follow rather than surfacing
    a clean tradeable universe.
    """
    return select(Symbol.code).where(
        Symbol.market == market,
        Symbol.is_active.is_(True),
        Symbol.is_hidden.is_(False),
        or_(Symbol.category.is_(None), Symbol.category != "Z"),
    )


def _investable(market: str):
    """Subquery of investable codes — visible AND liquid — for builders that don't query T."""
    return select(T.code).where(T.market == market, T.code.in_(_screenable_codes(market)), _LIQUID)


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
    # Quiet accumulation: strong money inflow while the price is still FLAT (hasn't run up) — the
    # Wyckoff / Chaikin A-D divergence setup hedge funds watch for: smart money loading a base
    # before the move. Differs from plain "Money flowing in" (CMF>0) by the not-yet-moved filter.
    ScreenSpec(
        "quiet_accumulation",
        "Quiet accumulation",
        "Money flowing in while the price is still flat — accumulation before a move",
        "CMF",
        and_(
            T.cmf_20 >= 0.10,  # clear money inflow (Chaikin)
            T.obv_slope.isnot(None),
            T.obv_slope > 0,  # volume confirming — OBV trending up (volume leads price)
            T.sma_50.isnot(None),
            T.sma_50 > 0,
            # Still in its base — price within ±10% of its 50-day average (not yet run up / not crashing).
            T.last_close <= T.sma_50 * 1.10,
            T.last_close >= T.sma_50 * 0.90,
        ),
        T.cmf_20.desc(),
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
        "Top cash dividend",
        "Last declared cash dividend ÷ today's price (trailing — past payout, not a forecast)",
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
]

# Screen → display group. Anything unlisted defaults to 'technical' (collapsed in the UI).
_GROUP: dict[str, str] = {
    "top_gainers": "movers",
    "top_losers": "movers",
    "most_active": "movers",
    "beating_market": "movers",
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
    "quiet_accumulation": "value",
    "foreign_buying": "value",
    "institutional_buying": "value",
    "sponsor_selling": "value",
    "momentum_12_1": "movers",
    "quality_roe": "value",
    "low_volatility": "value",
}

# Truth-in-labeling (matches the scanner's chips): backtested = validated on our DSE data,
# utility = descriptive with no edge claimed. Unlisted screens carry no chip.
_SCREEN_EVIDENCE: dict[str, str] = {
    "oversold": "backtested",  # strongest single signal in the factor study
    "unusual_volume": "utility",
    "beating_market": "utility",  # momentum family — frontend adds the trend-chasing caution
    "momentum_12_1": "utility",
    "near_52w_high": "utility",
    "institutional_buying": "utility",
    "foreign_buying": "utility",
    "sponsor_selling": "utility",
    "dividend_yield": "utility",
    "value_vs_sector": "utility",
    "quality_roe": "utility",
    "most_discussed": "utility",
}


class MomHorizons(BaseModel):
    """3-/6-/12-month returns for the momentum screen, so a row can show trend consistency
    across lookbacks (climbing in all three = broad/durable; only recent = newer move)."""

    m3: float | None = None
    m6: float | None = None
    m12: float | None = None


class ScreenItem(BaseModel):
    code: str
    name: str = ""  # company short name, for readability
    last_close: float
    value: float
    change_1d: float | None = None  # today's % move, the universal anchor (None for movers)
    note: str | None = None  # optional per-row qualifier (e.g. momentum: steady vs pump-risk)
    spark: list[float] = []  # recent closes (oldest→newest) for an inline sparkline
    horizons: MomHorizons | None = None  # momentum screen only: 3M/6M/12M returns for the cue
    flow: list[float] = []  # ownership screens: stake % over last disclosures (oldest→newest)
    flow_dates: list[str] = []  # ISO date of each flow point, aligned with `flow`
    period_spark: list[float] = []  # ownership: price over the disclosure window (oldest→newest)
    category: str | None = None  # DSE category (A/B/G/N/Z), for execution context
    adtv_mn: float | None = None  # 20D average daily traded value, ৳ millions
    turnover_mn: float | None = None  # latest quote turnover, ৳ millions
    safe_order_mn: float | None = None  # 5% ADTV proxy, ৳ millions
    market_cap_mn: float | None = None
    free_float_cap_mn: float | None = None
    liquidity: str | None = None  # Deep | Tradeable | Thin | Watch size
    setup_quality: str | None = None  # Clean setup | Mixed setup | High-risk setup
    why: str | None = None  # short row-level explanation of why this ticker appears
    catalyst: str | None = None  # latest material DSE announcement, if any
    catalyst_date: str | None = None
    catalyst_category: str | None = None
    scanner_label: str | None = None  # short board-specific label for Scanner rows/sheets
    how_to_read: str | None = None  # Scanner: plain-language read, not advice
    risk_note: str | None = None  # Scanner: what this pattern does not prove
    check_next: list[str] = []  # Scanner: concrete verification checklist


class ScreenOut(BaseModel):
    key: str
    title: str
    description: str
    value_label: str
    group: str = "technical"  # movers | community | value | technical
    # Truth-in-labeling: backtested (validated on our DSE data) | framework (classic
    # investing lens, not locally validated) | utility (descriptive, no edge claimed).
    evidence: str | None = None
    items: list[ScreenItem]


class MarketMethodology(BaseModel):
    market: str
    settlement_cycle: str
    data_clock: str
    liquidity_floor: str
    min_adtv_mn: float
    min_mcap_mn: float
    min_free_float_cap_mn: float


class ScreensResponse(BaseModel):
    as_of: str | None  # EOD analytics date — the screen RANKINGS are as-of this close
    quote_as_of: str | None = (
        None  # latest 15-min quote snapshot — prices / "today's move" freshness
    )
    methodology: MarketMethodology
    screens: list[ScreenOut]


class MarketPulseOut(BaseModel):
    as_of: str | None
    quote_as_of: str | None = None
    dsex: float | None = None
    dsex_change_pct: float | None = None
    turnover_cr: float | None = None
    turnover_vs_20d: float | None = None
    advancers: int
    decliners: int
    unchanged: int
    total: int
    top_sector: str | None = None
    top_sector_change: float | None = None
    weak_sector: str | None = None
    weak_sector_change: float | None = None
    risk_mode: str  # risk_on | mixed | defensive


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
                T.code.in_(_screenable_codes(market)),
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


async def _most_discussed(
    session, market: str, tenant_id: str, limit: int = PER_SCREEN
) -> ScreenOut:
    """Symbols with the most posts in the last couple of days (live, descriptive)."""
    since = dt.datetime.now(dt.UTC) - dt.timedelta(days=_DISCUSSED_DAYS)
    posts = func.count(func.distinct(Post.id))
    rows = (
        await session.execute(
            select(Cashtag.code, posts)
            .join(Post, Cashtag.post_id == Post.id)
            .where(
                Cashtag.market == market,
                Post.tenant_id == tenant_id,
                Post.created_at >= since,
                Post.moderation_status == "published",
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


async def _most_watched(session, market: str, tenant_id: str, limit: int = PER_SCREEN) -> ScreenOut:
    """Most-followed names — the community's 'Watchers' leaderboard."""
    cnt = func.count()
    rows = (
        await session.execute(
            select(WatchlistItem.code, cnt)
            .join(User, WatchlistItem.user_id == User.id)
            .where(WatchlistItem.market == market, WatchlistItem.code.in_(visible_codes(market)))
            .where(User.tenant_id == tenant_id)
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
            select(
                T.code,
                T.last_close,
                mom,
                T.volatility,
                T.market_cap_mn,
                T.mom_3_1,
                T.mom_6_1,
                T.mom_12_1,
            )
            .where(
                T.market == market,
                mom > 0,
                T.volatility > 0,
                T.code.in_(_screenable_codes(market)),
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
            ScreenItem(
                code=c,
                last_close=lc,
                value=round(m, 2),
                note=_mom_note(m, vol, mc),
                horizons=MomHorizons(
                    m3=None if m3 is None else round(m3, 1),
                    m6=None if m6 is None else round(m6, 1),
                    m12=None if m12 is None else round(m12, 1),
                ),
            )
            for c, lc, m, vol, mc, m3, m6, m12 in rows
        ],
    )


async def _build_spec(session, market: str, spec: ScreenSpec, limit: int) -> ScreenOut:
    rows = (
        await session.execute(
            select(T.code, T.last_close, spec.value)
            .where(T.market == market, spec.where, T.code.in_(_screenable_codes(market)), _LIQUID)
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


def _bdt_mn(n: float | None) -> str:
    """Compact BDT text from ৳ millions: >=10mn as crore, below as lakh."""
    if n is None:
        return "n/a"
    if n >= 10:
        return f"৳{n / 10:,.1f}cr"
    return f"৳{n * 10:,.0f}L"


def _metric_text(label: str, value: float) -> str:
    if label == "RSI":
        return f"RSI {value:.0f}"
    if label == "CMF":
        return f"CMF {value:.2f}"
    if label == "yield":
        return f"{value:.1f}% yield"
    if "sector" in label:
        return f"{value:.2f}x sector P/E"
    if "avg vol" in label or "usual" in label:
        return f"{value:.1f}x normal volume"
    if label == "turnover":
        return f"{_bdt_mn(value * 10)} turnover"
    if label == "pp":
        return f"{value:+.1f} pp stake change"
    if label in {"ROE", "volatility", "% today", "% period", "% YoY"}:
        return f"{value:+.1f}%"
    if label == "momentum":
        return f"{value:+.0f}% momentum"
    if label == "vs market":
        return f"{value:+.1f}% vs DSEX"
    return f"{value:.2f} {label}"


def _liquidity_label(adtv_mn: float | None, category: str | None) -> str | None:
    if category == "Z":
        return "High-risk: Z category"
    if adtv_mn is None:
        return None
    if adtv_mn >= 50:
        return "Deep liquidity"
    if adtv_mn >= 10:
        return "Tradeable liquidity"
    if adtv_mn >= _MIN_ADTV_MN:
        return "Watch order size"
    return "Thin liquidity"


def _setup_quality(screen: ScreenOut, item: ScreenItem) -> str | None:
    high_risk_note = (item.note or "").lower()
    if (
        item.category == "Z"
        or "pump" in high_risk_note
        or (item.adtv_mn is not None and item.adtv_mn < _MIN_ADTV_MN)
    ):
        return "High-risk read"
    if (
        item.adtv_mn is not None
        and item.adtv_mn >= 20
        and (
            item.catalyst
            or screen.key
            in {
                "institutional_buying",
                "foreign_buying",
                "quality_roe",
                "value_vs_sector",  # same shape as quality_roe: a plain value ranking, no
                # catalyst concept — omitting it meant "Cheap vs sector" could never show
                # "Clean read" even for a deep-liquidity Cat-A stock (confirmed live: BSC,
                # BSRMSTEEL, MALEKSPIN all had >20mn ADTV and zero risk flags, 2026-07-05).
                "dividend_yield",
                "beating_market",
                "quiet_accumulation",
            }
        )
    ):
        return "Clean read"
    return "Mixed read"


def _why_text(screen: ScreenOut, item: ScreenItem) -> str:
    metric = _metric_text(screen.value_label, item.value)
    parts = [f"{screen.title}: {metric}"]
    if item.change_1d is not None:
        parts.append(f"1D {item.change_1d:+.1f}%")
    if item.adtv_mn is not None and item.safe_order_mn is not None:
        parts.append(f"ADTV {_bdt_mn(item.adtv_mn)}")
        parts.append(f"5% size {_bdt_mn(item.safe_order_mn)}")
    if item.category:
        parts.append(f"Cat {item.category}")
    if item.catalyst:
        parts.append(f"{item.catalyst_category} {item.catalyst_date}")
    return " · ".join(parts)


async def _execution_context(
    session, market: str, codes: list[str]
) -> dict[str, dict[str, float | str | None]]:
    if not codes:
        return {}
    out: dict[str, dict[str, float | str | None]] = {c: {} for c in codes}
    ta_rows = (
        await session.execute(
            select(
                T.code, T.last_close, T.avg_volume_20, T.market_cap_mn, T.free_float_cap_mn
            ).where(T.market == market, T.code.in_(codes))
        )
    ).all()
    for code, last_close, avg_vol_20, market_cap_mn, free_float_cap_mn in ta_rows:
        adtv_mn = (avg_vol_20 * last_close / 1e6) if avg_vol_20 and last_close else None
        out.setdefault(code, {}).update(
            {
                "adtv_mn": round(adtv_mn, 2) if adtv_mn is not None else None,
                "safe_order_mn": round(adtv_mn * 0.05, 2) if adtv_mn is not None else None,
                "market_cap_mn": round(market_cap_mn, 2) if market_cap_mn is not None else None,
                "free_float_cap_mn": round(free_float_cap_mn, 2)
                if free_float_cap_mn is not None
                else None,
            }
        )
    q_rows = (
        await session.execute(
            select(QuoteSnapshot.code, QuoteSnapshot.volume, QuoteSnapshot.ltp).where(
                QuoteSnapshot.market == market, QuoteSnapshot.code.in_(codes)
            )
        )
    ).all()
    for code, volume, ltp in q_rows:
        turnover_mn = volume * ltp / 1e6 if volume is not None and ltp is not None else None
        out.setdefault(code, {})["turnover_mn"] = (
            round(turnover_mn, 2) if turnover_mn is not None else None
        )
    s_rows = (
        await session.execute(
            select(Symbol.code, Symbol.category).where(
                Symbol.market == market, Symbol.code.in_(codes)
            )
        )
    ).all()
    for code, category in s_rows:
        out.setdefault(code, {})["category"] = category
    return out


async def _recent_catalysts(session, market: str, codes: list[str]) -> dict[str, Announcement]:
    if not codes:
        return {}
    cutoff = to_market_tz(dt.datetime.now(dt.UTC)).date() - dt.timedelta(days=21)
    rows = list(
        await session.scalars(
            select(Announcement)
            .where(
                Announcement.market == market,
                Announcement.code.in_(codes),
                Announcement.category.in_(_MATERIAL_ANNOUNCEMENT_CATEGORIES),
                Announcement.published_at >= cutoff,
            )
            .order_by(
                Announcement.code, Announcement.published_at.desc(), Announcement.strength.desc()
            )
        )
    )
    out: dict[str, Announcement] = {}
    for row in rows:
        out.setdefault(row.code, row)
    return out


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


# --- Ownership flow (institutional vs foreign accumulation) ------------------
# Foreign investors (pickier, longer-horizon) and local institutions carry different sentiment, so
# we keep them as two screens. DSE discloses shareholding ~quarterly, so the "trend" is the last few
# disclosures — enough to tell sustained accumulation from a one-off bump, not a long history.
_OWN = {
    "foreign": (T.foreign_delta, "foreign_pct", "Foreign", "Foreign investors"),
    "institute": (T.institute_delta, "institute", "Institutions", "Local institutions"),
}
# Only show rises big enough to read as real buying — below this they'd display as "+0.0 pp"
# (foreign stakes on DSE are tiny, so this keeps the screen honest rather than full of noise).
_MIN_STAKE_DELTA = 0.05


def _flow_tag(prev_delta: float | None, direction: str) -> str:
    """The latest disclosure already moved the filtered way. Distinguish sustained vs one-off,
    worded to avoid implying equal periods (our captured disclosures aren't evenly spaced)."""
    if direction == "sell":
        if prev_delta is None:
            return "Selling"
        return "Selling more" if prev_delta < 0 else "Started selling"
    if prev_delta is None:
        return "Buying"
    return "Buying more" if prev_delta > 0 else "Started buying"


def _persistence_note(series: list[float], direction: str) -> str | None:
    """How professionals actually read holder flow: persistence over single prints.

    Counts consecutive same-direction steps ending at the latest disclosure; from 3 steps the
    row says so explicitly with the cumulative move ("3 straight rises · +2.4 pp total")."""
    if len(series) < 4:
        return None
    run = 0
    for newer, older in zip(reversed(series), list(reversed(series))[1:], strict=False):
        step = newer - older
        if (direction == "sell" and step < 0) or (direction != "sell" and step > 0):
            run += 1
        else:
            break
    if run < 3:
        return None
    total = series[-1] - series[-1 - run]
    word = "falls" if direction == "sell" else "rises"
    return f"{run} straight {word} · {total:+.1f} pp total"


@dataclass
class _Flow:
    series: list[float]  # stake % at each disclosure, oldest→newest
    dates: list[str]  # ISO date of each disclosure, aligned with series
    prev_delta: float | None  # the step BEFORE the latest, to judge sustained vs one-off


async def _ownership_flow(session, market: str, codes: list[str], attr: str) -> dict[str, _Flow]:
    """For each code: the last 3 disclosed stake %s + their dates (oldest→newest), so the row can
    show WHEN the change happened and over what gap (our scrape is irregular, not strictly monthly)."""
    if not codes:
        return {}
    rows = list(
        await session.scalars(
            select(ShareholdingSnapshot)
            .where(
                ShareholdingSnapshot.market == market,
                ShareholdingSnapshot.code.in_(codes),
            )
            .order_by(ShareholdingSnapshot.code, ShareholdingSnapshot.as_of_date.desc())
        )
    )
    by_code: dict[str, list[ShareholdingSnapshot]] = {}
    for r in rows:
        by_code.setdefault(r.code, []).append(r)  # newest-first per code
    out: dict[str, _Flow] = {}
    for code, snaps in by_code.items():
        # 5 disclosures: 3 draw the dots, the extra depth feeds the persistence read.
        pairs = [
            (s.as_of_date, getattr(s, attr)) for s in snaps[:5] if getattr(s, attr) is not None
        ]
        pairs.reverse()  # oldest→newest
        series = [round(v, 2) for _, v in pairs]
        dates = [d.isoformat() for d, _ in pairs]
        prev_delta = series[-2] - series[-3] if len(series) >= 3 else None
        out[code] = _Flow(series=series, dates=dates, prev_delta=prev_delta)
    return out


def _downsample(xs: list[float], n: int) -> list[float]:
    """Evenly thin a series to ~n points so a long price window fits a tiny sparkline."""
    if len(xs) <= n:
        return xs
    step = (len(xs) - 1) / (n - 1)
    return [xs[round(i * step)] for i in range(n)]


async def _period_sparks(
    session, market: str, code_from: dict[str, dt.date]
) -> dict[str, list[float]]:
    """Closing prices from each code's earliest disclosure date to now — the accumulation window."""
    if not code_from:
        return {}
    earliest = min(code_from.values())
    rows = (
        await session.execute(
            select(DailyBar.code, DailyBar.date, DailyBar.close)
            .where(
                DailyBar.market == market,
                DailyBar.code.in_(list(code_from)),
                DailyBar.date >= earliest,
            )
            .order_by(DailyBar.code, DailyBar.date)
        )
    ).all()
    by_code: dict[str, list[float]] = defaultdict(list)
    for code, date, close in rows:
        if date >= code_from[code]:
            by_code[code].append(round(close, 2))
    return {code: _downsample(closes, 30) for code, closes in by_code.items()}


async def _ownership(
    session, market: str, *, kind: str, direction: str = "buy", limit: int = PER_SCREEN
) -> ScreenOut:
    """Institutions / foreign investors who moved their stake at the latest disclosure.
    direction='buy' → accumulation (stake up); 'sell' → distribution (stake down)."""
    delta_col, attr, title, who = _OWN[kind]
    selling = direction == "sell"
    cond = delta_col <= -_MIN_STAKE_DELTA if selling else delta_col >= _MIN_STAKE_DELTA
    order = delta_col.asc() if selling else delta_col.desc()  # biggest move of that kind first
    rows = (
        await session.execute(
            select(T.code, T.last_close, delta_col)
            .where(T.market == market, cond, T.code.in_(_screenable_codes(market)), _LIQUID)
            .order_by(order)
            .limit(limit)
        )
    ).all()
    flows = await _ownership_flow(session, market, [c for c, _, _ in rows], attr)
    # Price over the move window: from the prior disclosure (the comparison point) to now.
    code_from = {}
    for c, _, _ in rows:
        ds = flows[c].dates if c in flows else []
        if ds:
            code_from[c] = dt.date.fromisoformat(ds[-2] if len(ds) >= 2 else ds[0])
    psparks = await _period_sparks(session, market, code_from)
    empty = _Flow(series=[], dates=[], prev_delta=None)
    items = []
    for c, lc, d in rows:
        f = flows.get(c, empty)
        items.append(
            ScreenItem(
                code=c,
                last_close=lc,
                value=round(d, 1),
                # Persistence beats a single print — pros' first question is "how many
                # disclosures in a row?", so a real streak overrides the basic tag.
                note=_persistence_note(f.series, direction) or _flow_tag(f.prev_delta, direction),
                flow=f.series,
                flow_dates=f.dates,
                period_spark=psparks.get(c, []),
            )
        )
    verb = "trimmed" if selling else "raised"
    return ScreenOut(
        key=f"{'foreign' if kind == 'foreign' else 'institutional'}_buying",
        title=title,
        description=(
            f"{who} {verb} their stake since the prior disclosure (the 'since' date on each row). "
            "Streaks are marked — persistence across disclosures matters more than one print. "
            "Line = price over that window; dots = stake at each disclosure."
        ),
        value_label="pp",
        group="value",
        items=items,
    )


# Sponsors/directors reducing needs a lower floor than institutions: insiders trimming their own
# stake is material even in small steps, and DSE sponsor floors (30% joint) make big prints rare.
_MIN_SPONSOR_DROP = 0.5


async def _sponsor_selling(session, market: str, limit: int = PER_SCREEN) -> ScreenOut:
    """Insiders reducing their own stake — the disclosure-synthesis red-flag board.

    No sponsor delta lives in ticker_analytics, so the deltas come straight from the last two
    shareholding disclosures per code (the whole table is ~3 rows/stock — this is cheap)."""
    codes = list(await session.scalars(_screenable_codes(market)))
    flows = await _ownership_flow(session, market, codes, "sponsor_director")
    drops: list[tuple[str, float, _Flow]] = []
    for code, f in flows.items():
        if len(f.series) < 2:
            continue
        delta = f.series[-1] - f.series[-2]
        if delta <= -_MIN_SPONSOR_DROP:
            drops.append((code, delta, f))
    drops.sort(key=lambda x: x[1])  # deepest reduction first
    drops = drops[:limit]

    closes = {
        c: lc
        for c, lc in (
            await session.execute(
                select(T.code, T.last_close).where(
                    T.market == market, T.code.in_([c for c, _, _ in drops]), _LIQUID
                )
            )
        ).all()
    }
    code_from = {
        c: dt.date.fromisoformat(f.dates[-2])
        for c, _, f in drops
        if c in closes and len(f.dates) >= 2
    }
    psparks = await _period_sparks(session, market, code_from)
    items = [
        ScreenItem(
            code=c,
            last_close=closes[c],
            value=round(delta, 1),
            note=_persistence_note(f.series, "sell") or _flow_tag(f.prev_delta, "sell"),
            why=(
                f"Sponsor/director holding fell {f.series[-2]:.1f}% → {f.series[-1]:.1f}% "
                f"({delta:+.1f} pp) at the latest disclosure."
            ),
            flow=f.series,
            flow_dates=f.dates,
            period_spark=psparks.get(c, []),
        )
        for c, delta, f in drops
        if c in closes
    ]
    return ScreenOut(
        key="sponsor_selling",
        title="Sponsor Selling",
        description=(
            "Sponsors/directors reduced their own stake since the prior disclosure — insiders' "
            "own money leaving. A disclosed fact to research, not a sell signal. "
            "Source: DSE shareholding disclosures."
        ),
        value_label="pp",
        group="value",
        items=items,
    )


async def _enrich(session, market: str, screens_list: list[ScreenOut]) -> None:
    """Fill name + 1d change + sparkline on every item, batched across all screens."""
    codes = sorted({it.code for s in screens_list for it in s.items})
    names = await _names(session, market, codes)
    skip = {it.code for s in screens_list if s.key in _NO_1D for it in s.items}
    changes = await _change_1d(session, market, sorted(set(codes) - skip))
    sparks = await _sparks(session, market, codes)
    context = await _execution_context(session, market, codes)
    catalysts = await _recent_catalysts(session, market, codes)
    for s in screens_list:
        s.evidence = s.evidence or _SCREEN_EVIDENCE.get(s.key)
        for it in s.items:
            it.name = names.get(it.code, "")
            it.change_1d = None if s.key in _NO_1D else changes.get(it.code)
            it.spark = sparks.get(it.code, [])
            ctx = context.get(it.code, {})
            it.category = ctx.get("category") if isinstance(ctx.get("category"), str) else None
            it.adtv_mn = ctx.get("adtv_mn") if isinstance(ctx.get("adtv_mn"), float) else None
            it.turnover_mn = (
                ctx.get("turnover_mn") if isinstance(ctx.get("turnover_mn"), float) else None
            )
            it.safe_order_mn = (
                ctx.get("safe_order_mn") if isinstance(ctx.get("safe_order_mn"), float) else None
            )
            it.market_cap_mn = (
                ctx.get("market_cap_mn") if isinstance(ctx.get("market_cap_mn"), float) else None
            )
            it.free_float_cap_mn = (
                ctx.get("free_float_cap_mn")
                if isinstance(ctx.get("free_float_cap_mn"), float)
                else None
            )
            it.liquidity = _liquidity_label(it.adtv_mn, it.category)
            catalyst = catalysts.get(it.code)
            if catalyst:
                it.catalyst = catalyst.headline
                it.catalyst_date = str(catalyst.published_at)
                it.catalyst_category = catalyst.category
            it.setup_quality = _setup_quality(s, it)
            # A board builder may have written a richer per-name sentence (e.g. the scanner's
            # Quality Reversal / Oversold Quality prose) — never clobber it with the generic line.
            it.why = it.why or _why_text(s, it)


_SPEC_BY_KEY = {s.key: s for s in _SCREENS}


async def build_screen(
    session, market: str, key: str, limit: int, *, tenant_id: str, direction: str = "buy"
) -> ScreenOut | None:
    """Build a single screen by key (used by the detail/explore page)."""
    if key in ("top_gainers", "top_losers"):
        return await _movers(session, market, gainers=key == "top_gainers", limit=limit)
    if key == "most_active":
        return await _most_active(session, market, limit=limit)
    if key == "momentum_12_1":
        return await _momentum(session, market, limit=limit)
    if key == "unusual_volume":
        return await _unusual_volume(session, market, limit=limit)
    if key == "beating_market":
        return await _beating_market(session, market, limit=limit)
    if key == "foreign_buying":
        return await _ownership(session, market, kind="foreign", direction=direction, limit=limit)
    if key == "institutional_buying":
        return await _ownership(session, market, kind="institute", direction=direction, limit=limit)
    if key == "sponsor_selling":
        return await _sponsor_selling(session, market, limit=limit)
    if key == "most_watched":
        return await _most_watched(session, market, tenant_id=tenant_id, limit=limit)
    if key == "most_discussed":
        return await _most_discussed(session, market, tenant_id=tenant_id, limit=limit)
    if key == "attention_rising":
        return await _attention_rising(session, market, limit=limit)
    spec = _SPEC_BY_KEY.get(key)
    return await _build_spec(session, market, spec, limit) if spec else None


# Cache safety-sweep TTL. Real invalidation is the data-fingerprinted key (quote + analytics
# timestamps), so this only reaps keys for days/polls that will never be requested again.
_SCREENS_TTL = 6 * 60 * 60


@router.get("/screens")
async def screens(tenant: CurrentTenant, session: DbSession) -> ScreensResponse:
    """Cached, but keyed on data freshness so it's never staler than the data itself.

    The key folds in BOTH the latest quote snapshot (changes every 15-min poll → intraday prices /
    'today's move' stay current) AND the analytics recompute time (changes nightly at EOD → the
    screen rankings refresh). Within a poll window every request is a ~ms Redis read; the heavy
    multi-screen compute runs once per poll, not once per request.
    """
    market = tenant.market
    quote_ts = await session.scalar(
        select(func.max(QuoteSnapshot.as_of)).where(QuoteSnapshot.market == market)
    )
    ana_ts = await session.scalar(select(func.max(T.computed_at)).where(T.market == market))
    # v4: value_vs_sector added to the Clean-read whitelist in _setup_quality (bump on shape
    # changes — the key folds in data freshness, but only a version bump invalidates on code
    # changes; confirmed live 2026-07-05 that skipping this left stale "Mixed read" cached).
    key = f"screens:v4:{market}:{quote_ts}:{ana_ts}"
    redis = aioredis.from_url(get_settings().redis_url)
    try:
        cached = await redis.get(key)
        if cached:
            # Serve the cached JSON bytes verbatim — skip the pydantic parse + re-serialize of ~65KB.
            return Response(content=cached, media_type="application/json")
        resp = await _build_screens(tenant, session, quote_ts)
        await redis.set(key, resp.model_dump_json(), ex=_SCREENS_TTL)
        return resp
    finally:
        await redis.aclose()


async def _build_screens(
    tenant: CurrentTenant, session: DbSession, quote_ts: dt.datetime | None
) -> ScreensResponse:
    out: list[ScreenOut] = [
        await _build_spec(session, tenant.market, spec, PER_SCREEN) for spec in _SCREENS
    ]
    out.append(await _movers(session, tenant.market, gainers=True))
    out.append(await _movers(session, tenant.market, gainers=False))
    out.append(await _most_active(session, tenant.market))
    out.append(await _momentum(session, tenant.market))
    out.append(await _unusual_volume(session, tenant.market))
    out.append(await _beating_market(session, tenant.market))
    out.append(await _ownership(session, tenant.market, kind="foreign"))
    out.append(await _ownership(session, tenant.market, kind="institute"))
    out.append(await _sponsor_selling(session, tenant.market))
    out.append(await _most_watched(session, tenant.market, tenant_id=tenant.name))
    out.append(await _most_discussed(session, tenant.market, tenant_id=tenant.name))
    out.append(await _attention_rising(session, tenant.market))

    await _enrich(session, tenant.market, out)
    as_of = await session.scalar(select(T.as_of_date).where(T.market == tenant.market).limit(1))
    methodology = MarketMethodology(
        market=tenant.market,
        settlement_cycle=DSE_SETTLEMENT_CYCLE,
        data_clock="End-of-day analytics from DSE closes; live quote boards use latest quote snapshot.",
        liquidity_floor=(
            "Institutional discovery: minimum 20-session average daily turnover and market cap; "
            "free-float cap floor is applied when available."
        ),
        min_adtv_mn=_MIN_ADTV_MN,
        min_mcap_mn=_MIN_MCAP_MN,
        min_free_float_cap_mn=_MIN_FREE_FLOAT_CAP_MN,
    )
    return ScreensResponse(
        as_of=str(as_of) if as_of else None,
        quote_as_of=quote_ts.isoformat() if quote_ts else None,
        methodology=methodology,
        screens=out,
    )


class SectorRow(BaseModel):
    sector: str
    avg_change: float
    advancers: int
    decliners: int
    count: int


def _index_pct_from_points(level: float | None, points: float | None) -> float | None:
    pct = index_change_pct(level, points)
    return round(pct, 2) if pct is not None else None


async def _breadth(session, market: str) -> tuple[int, int, int, int]:
    adv, dec, flat, total = (
        await session.execute(
            select(
                func.count().filter(QuoteSnapshot.change_pct > 0),
                func.count().filter(QuoteSnapshot.change_pct < 0),
                func.count().filter(QuoteSnapshot.change_pct == 0),
                func.count(),
            ).where(QuoteSnapshot.market == market, QuoteSnapshot.code.in_(visible_codes(market)))
        )
    ).one()
    return int(adv or 0), int(dec or 0), int(flat or 0), int(total or 0)


async def _sector_rows(session, market: str) -> list[SectorRow]:
    avg_chg = func.avg(QuoteSnapshot.change_pct)
    adv = func.count().filter(QuoteSnapshot.change_pct > 0)
    dec = func.count().filter(QuoteSnapshot.change_pct < 0)
    rows = (
        await session.execute(
            select(Symbol.sector, avg_chg, adv, dec, func.count())
            .join(
                QuoteSnapshot,
                and_(
                    QuoteSnapshot.market == Symbol.market,
                    QuoteSnapshot.code == Symbol.code,
                ),
            )
            .where(
                Symbol.market == market,
                Symbol.code.in_(visible_codes(market)),
                Symbol.sector.isnot(None),
            )
            .group_by(Symbol.sector)
            .having(func.count() >= 3)  # ignore tiny one-off "sectors"
            .order_by(avg_chg.desc())
        )
    ).all()
    return [
        SectorRow(
            sector=s,
            avg_change=round(float(a), 2),
            advancers=int(up),
            decliners=int(down),
            count=int(n),
        )
        for s, a, up, down, n in rows
    ]


def _risk_mode(dsex_pct: float | None, turnover_vs_20d: float | None, adv: int, dec: int) -> str:
    decided = adv + dec
    breadth = adv / decided if decided else 0.5
    turn = turnover_vs_20d or 1.0
    pct = dsex_pct or 0.0
    if pct >= 0.25 and breadth >= 0.58 and turn >= 0.9:
        return "risk_on"
    if pct <= -0.25 and breadth <= 0.42:
        return "defensive"
    return "mixed"


@router.get("/market-pulse")
async def market_pulse(tenant: CurrentTenant, session: DbSession) -> MarketPulseOut:
    """One institutional-style market regime read before drilling into individual screens."""
    market = tenant.market
    summary = await session.scalar(
        select(MarketSummary)
        .where(MarketSummary.market == market)
        .order_by(MarketSummary.date.desc())
        .limit(1)
    )
    values = (
        await session.scalars(
            select(MarketSummary.total_value_mn)
            .where(MarketSummary.market == market, MarketSummary.total_value_mn.isnot(None))
            .order_by(MarketSummary.date.desc())
            .limit(21)
        )
    ).all()
    latest_turnover = values[0] if values else None
    prior_values = values[1:] if len(values) > 1 else values
    avg_turnover = sum(prior_values) / len(prior_values) if prior_values else None
    turnover_vs_20d = (
        round(latest_turnover / avg_turnover, 2)
        if latest_turnover is not None and avg_turnover
        else None
    )
    adv, dec, flat, total = await _breadth(session, market)
    sectors = await _sector_rows(session, market)
    quote_ts = await session.scalar(
        select(func.max(QuoteSnapshot.as_of)).where(QuoteSnapshot.market == market)
    )
    dsex_pct = _index_pct_from_points(
        summary.dsex if summary else None, summary.dsex_change if summary else None
    )
    top = sectors[0] if sectors else None
    weak = sectors[-1] if sectors else None
    return MarketPulseOut(
        as_of=str(summary.date) if summary else None,
        quote_as_of=quote_ts.isoformat() if quote_ts else None,
        dsex=round(summary.dsex, 2) if summary and summary.dsex is not None else None,
        dsex_change_pct=dsex_pct,
        turnover_cr=round(summary.total_value_mn / 10, 1)
        if summary and summary.total_value_mn is not None
        else None,
        turnover_vs_20d=turnover_vs_20d,
        advancers=adv,
        decliners=dec,
        unchanged=flat,
        total=total,
        top_sector=top.sector if top else None,
        top_sector_change=top.avg_change if top else None,
        weak_sector=weak.sector if weak else None,
        weak_sector_change=weak.avg_change if weak else None,
        risk_mode=_risk_mode(dsex_pct, turnover_vs_20d, adv, dec),
    )


@router.get("/sectors")
async def sectors(tenant: CurrentTenant, session: DbSession) -> list[SectorRow]:
    """Today's move aggregated by sector — DSE retail thinks in sectors (bank, pharma, textile…).
    Average change + advancers/decliners breadth across the visible universe, hottest first."""
    return await _sector_rows(session, tenant.market)


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


_RS_DAYS = 22  # relative-strength lookback (~1 month of sessions)


async def _index_return(session, market: str, days: int) -> float | None:
    """DSEX index % change over the trailing `days` sessions."""
    levels = (
        await session.scalars(
            select(MarketSummary.dsex)
            .where(MarketSummary.market == market, MarketSummary.dsex.isnot(None))
            .order_by(MarketSummary.date.desc())
            .limit(days + 1)
        )
    ).all()
    if len(levels) < days + 1 or not levels[days]:
        return None
    return (levels[0] - levels[days]) / levels[days] * 100


async def _beating_market(session, market: str, *, limit: int = PER_SCREEN) -> ScreenOut:
    """Stocks outperforming the DSEX over ~1 month — relative strength, the institutional tell for
    genuine strength (up while, or more than, the market). Value = excess return vs the index."""
    idx = await _index_return(session, market, _RS_DAYS)
    desc_idx = f"{idx:+.1f}%" if idx is not None else "n/a"
    base = ScreenOut(
        key="beating_market",
        title="Beating the market",
        description=f"Outperforming the DSEX (index {desc_idx} over ~1 month)",
        value_label="vs market",
        group="movers",
        items=[],
    )
    if idx is None:
        return base
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
        select(ranked.c.code, ranked.c.close.label("old"))
        .where(ranked.c.rn == _RS_DAYS + 1)
        .subquery()
    )
    ret = (cur.c.cur - old.c.old) / old.c.old * 100
    rows = (
        await session.execute(
            select(cur.c.code, cur.c.cur, ret.label("ret"))
            .join(old, cur.c.code == old.c.code)
            .where(old.c.old > 0, ret > idx)
            .order_by(ret.desc())
            .limit(limit)
        )
    ).all()
    base.items = [ScreenItem(code=c, last_close=p, value=round(r - idx, 2)) for c, p, r in rows]
    return base


@router.get("/screens/{key}")
async def screen_detail(
    key: str,
    tenant: CurrentTenant,
    session: DbSession,
    limit: int = Query(50, le=200),
    period: str | None = Query(None, description="movers only: 1d | 5d | 1m"),
    window: str | None = Query(None, description="momentum only: 3m | 6m | 12m"),
    direction: str | None = Query(None, description="ownership only: buy | sell"),
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
        screen = await build_screen(
            session,
            tenant.market,
            key,
            limit,
            tenant_id=tenant.name,
            direction="sell" if direction == "sell" else "buy",
        )
    if screen is None:
        raise HTTPException(status_code=404, detail=f"Unknown screen {key!r}")
    await _enrich(session, tenant.market, [screen])
    return screen
