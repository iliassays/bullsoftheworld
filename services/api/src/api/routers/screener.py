"""Discovery screener — top tickers per descriptive condition, as fast SQL over ticker_analytics.

Every screen is a computed FACT (RSI <= 30, close near support, positive money flow, ...), named by
the condition, never by implication. No advice, no AI — pure data the analytics scheduler persisted.
"""

from __future__ import annotations

import datetime as dt
from collections import defaultdict
from contextlib import suppress
from dataclasses import dataclass

import redis.asyncio as aioredis
from fastapi import APIRouter, HTTPException, Query, Response
from pydantic import BaseModel
from redis.exceptions import RedisError
from sqlalchemy import ColumnElement, and_, case, func, or_, select
from sqlalchemy.orm import aliased

from api.deps import CurrentTenant, DbSession, enforce_market_feature, visible_codes
from api.market_freshness import quote_data_status
from api.routers.buzz import _MIN_BASELINE_DAYS, attention_label
from api.screen_membership import (
    apply_stored_screen_memberships,
    screen_membership_key,
    update_screen_memberships,
)
from bulls.analytics.indicators import index_change_pct
from bulls.core.config import get_settings
from bulls.core.markets import format_money_millions, get_market_profile
from bulls.core.models import (
    Announcement,
    Cashtag,
    DailyBar,
    InstitutionalHoldingSummary,
    MarketSummary,
    Post,
    QuoteSnapshot,
    ShareholdingSnapshot,
    Symbol,
    TickerAnalytics,
    TickerBuzzDaily,
    TickerPattern,
    User,
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


@dataclass(frozen=True)
class ScreenMarketSettings:
    min_adtv_mn: float
    min_mcap_mn: float
    min_free_float_cap_mn: float
    dse_category_filter: bool = False


_SCREEN_SETTINGS: dict[str, ScreenMarketSettings] = {
    # DSE screens should surface names a real desk can plausibly trade without dominating the tape.
    # Values are in currency millions: BDT mn for DSE.
    "DSE": ScreenMarketSettings(
        min_adtv_mn=5.0,
        min_mcap_mn=500.0,
        min_free_float_cap_mn=100.0,
        dse_category_filter=True,
    ),
    # US placeholder values are deliberately conservative and in USD mn. They only apply once a US
    # provider populates ticker_analytics for market="US".
    "US": ScreenMarketSettings(min_adtv_mn=2.0, min_mcap_mn=300.0, min_free_float_cap_mn=50.0),
}


def _screen_settings(market: str) -> ScreenMarketSettings:
    return _SCREEN_SETTINGS.get(market.upper(), _SCREEN_SETTINGS["DSE"])


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


def _screenable_codes(market: str, cap_tier: str | None = None):
    """Visible codes eligible for default Market screens.

    DSE Z-category names are left out of investable discovery boards. Other markets do not inherit
    that filter unless their settings explicitly ask for it.
    """
    conds = [
        Symbol.market == market,
        Symbol.is_active.is_(True),
        Symbol.is_hidden.is_(False),
        Symbol.data_status == "ready",
    ]
    if _screen_settings(market).dse_category_filter:
        conds.append(or_(Symbol.category.is_(None), Symbol.category != "Z"))
    fresh = aliased(TickerAnalytics)
    if cap_tier is not None:
        conds.append(fresh.cap_tier == cap_tier)
    latest_date = (
        select(func.max(TickerAnalytics.as_of_date))
        .where(TickerAnalytics.market == market)
        .scalar_subquery()
    )
    return (
        select(Symbol.code)
        .join(fresh, and_(fresh.market == Symbol.market, fresh.code == Symbol.code))
        .where(*conds, fresh.as_of_date == latest_date)
    )


def _minimum_market_cap(market: str, cap_tier: str | None = None) -> float:
    """Default discovery floor, except when the user explicitly researches micro caps.

    The canonical micro tier is below the default floor by definition (DSE <500mn, US <300mn).
    Keeping that floor in micro mode would make the universe structurally empty. Turnover and
    free-float checks still protect basic tradability.
    """

    return 0.0 if cap_tier == "micro" else _screen_settings(market).min_mcap_mn


def _liquid(market: str, cap_tier: str | None = None):
    settings = _screen_settings(market)
    return and_(
        T.last_close > 0,
        T.avg_volume_20.isnot(None),
        T.avg_volume_20 > 0,
        T.avg_volume_20 * T.last_close / 1e6 >= settings.min_adtv_mn,
        func.coalesce(T.market_cap_mn, 0) >= _minimum_market_cap(market, cap_tier),
        or_(
            T.free_float_cap_mn.is_(None),
            T.free_float_cap_mn >= settings.min_free_float_cap_mn,
        ),
    )


def _investable(market: str, cap_tier: str | None = None):
    """Subquery of investable codes — visible AND liquid — for builders that don't query T."""
    return select(T.code).where(
        T.market == market,
        T.code.in_(_screenable_codes(market, cap_tier)),
        _liquid(market, cap_tier),
    )


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
        "Positive CMF",
        "Volume-weighted closes favored the upper daily range",
        "CMF",
        T.cmf_20 > 0,
        T.cmf_20.desc(),
        T.cmf_20,
    ),
    ScreenSpec(
        "distribution",
        "Negative CMF",
        "Volume-weighted closes favored the lower daily range",
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
        "Quiet price-volume divergence",
        "Positive CMF and rising OBV while price remains near its 50-day average",
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
        "Most profit per unit of shareholder capital (ROE)",
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
    "institutional_selling": "utility",
    "institutional_13f_accumulation": "utility",
    "institutional_13f_distribution": "utility",
    "foreign_buying": "utility",
    "sponsor_selling": "utility",
    "dividend_yield": "utility",
    "value_vs_sector": "utility",
    "quality_roe": "utility",
    "most_discussed": "utility",
    # chart_pattern_* (one board per pattern type — ascending_triangle, double_top, etc.) are
    # handled by prefix below, not listed individually here.
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
    comparison_as_of: str | None = None  # prior disclosure/report date for the displayed change
    data_as_of: str | None = None  # latest disclosure/report date for the displayed change
    period_spark: list[float] = []  # ownership: price over the disclosure window (oldest→newest)
    category: str | None = None  # DSE category (A/B/G/N/Z), for execution context
    adtv_mn: float | None = None  # 20D average daily traded value, ৳ millions
    turnover_mn: float | None = None  # latest quote turnover, ৳ millions
    safe_order_mn: float | None = None  # 5% ADTV proxy, ৳ millions
    market_cap_mn: float | None = None
    cap_tier: str | None = None  # canonical size tier (mega|large|mid|small|micro); None = unclassified
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
    pattern_status: str | None = None
    pattern_metrics: dict[str, float] | None = None
    # Set only while this ticker is a recent entrant to this exact tenant/market/universe board.
    # NULL means either long-standing membership or that no trustworthy prior baseline exists.
    new_since: str | None = None
    new_reason: str | None = None  # board_entry | new_disclosure


class ScreenOut(BaseModel):
    key: str
    title: str
    description: str
    value_label: str
    group: str = "technical"  # movers | community | value | technical
    # Truth-in-labeling: backtested (historical edge) | experimental (tested, no stable edge) |
    # framework (classic method, not locally validated) | utility (descriptive, no edge claimed).
    evidence: str | None = None
    total_count: int | None = None
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
    cap_tier: str | None = None
    screens: list[ScreenOut]


class MarketPulseOut(BaseModel):
    as_of: str | None
    quote_as_of: str | None = None
    close_as_of: str | None = None
    data_status: str
    refresh_interval_minutes: int = 15
    benchmark_is_live: bool = False
    turnover_is_partial: bool = False
    turnover_is_estimated: bool = False
    dsex: float | None = None
    dsex_change_pct: float | None = None
    turnover_cr: float | None = None
    benchmark_label: str | None = None
    benchmark_close: float | None = None
    benchmark_change_pct: float | None = None
    turnover_mn: float | None = None
    turnover_vs_20d: float | None = None
    advancers: int
    decliners: int
    unchanged: int
    total: int
    published_symbols: int
    eligible_symbols: int
    coverage_ratio: float
    coverage_complete: bool
    top_sector: str | None = None
    top_sector_change: float | None = None
    weak_sector: str | None = None
    weak_sector_change: float | None = None
    risk_mode: str  # risk_on | mixed | defensive


async def _movers(
    session,
    market: str,
    *,
    gainers: bool,
    limit: int = PER_SCREEN,
    cap_tier: str | None = None,
) -> ScreenOut:
    order = QuoteSnapshot.change_pct.desc() if gainers else QuoteSnapshot.change_pct.asc()
    rows = (
        await session.execute(
            select(QuoteSnapshot.code, QuoteSnapshot.ltp, QuoteSnapshot.change_pct)
            .where(
                QuoteSnapshot.market == market,
                QuoteSnapshot.code.in_(_investable(market, cap_tier)),
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
    session,
    market: str,
    *,
    window: str = "1d",
    limit: int = PER_SCREEN,
    cap_tier: str | None = None,
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
                T.code.in_(_screenable_codes(market, cap_tier)),
                _liquid(market, cap_tier),
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


async def _most_active(
    session, market: str, limit: int = PER_SCREEN, *, cap_tier: str | None = None
) -> ScreenOut:
    """Most heavily traded by value today — DSE's classic 'top turnover' board. Surfaces where the
    money actually is, including the cheap, heavily-churned names retail follows."""
    turnover = QuoteSnapshot.volume * QuoteSnapshot.ltp
    rows = (
        await session.execute(
            select(QuoteSnapshot.code, QuoteSnapshot.ltp, turnover.label("t"))
            .where(
                QuoteSnapshot.market == market,
                QuoteSnapshot.code.in_(_investable(market, cap_tier)),
            )
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
        items=[ScreenItem(code=c, last_close=p, value=round(t / 1e6, 2)) for c, p, t in rows],
    )


async def _institutional_13f(
    session,
    market: str,
    *,
    accumulation: bool,
    limit: int = PER_SCREEN,
    cap_tier: str | None = None,
) -> ScreenOut:
    previous_summary = aliased(InstitutionalHoldingSummary)
    latest_period = (
        select(
            InstitutionalHoldingSummary.code,
            func.max(InstitutionalHoldingSummary.report_date).label("report_date"),
        )
        .where(InstitutionalHoldingSummary.market == market)
        .group_by(InstitutionalHoldingSummary.code)
        .subquery()
    )
    change = InstitutionalHoldingSummary.net_change_pct
    rows = (
        await session.execute(
            select(
                InstitutionalHoldingSummary.code,
                T.last_close,
                change,
                InstitutionalHoldingSummary.report_date,
                InstitutionalHoldingSummary.prior_report_date,
                previous_summary.net_change_pct.label("prior_net_change_pct"),
            )
            .join(
                latest_period,
                (latest_period.c.code == InstitutionalHoldingSummary.code)
                & (latest_period.c.report_date == InstitutionalHoldingSummary.report_date),
            )
            .join(T, (T.market == market) & (T.code == InstitutionalHoldingSummary.code))
            .outerjoin(
                previous_summary,
                (previous_summary.market == InstitutionalHoldingSummary.market)
                & (previous_summary.code == InstitutionalHoldingSummary.code)
                & (
                    previous_summary.report_date
                    == InstitutionalHoldingSummary.prior_report_date
                ),
            )
            .where(
                InstitutionalHoldingSummary.market == market,
                T.code.in_(_screenable_codes(market, cap_tier)),
                change.isnot(None),
                change > 0 if accumulation else change < 0,
                _liquid(market, cap_tier),
            )
            .order_by(change.desc() if accumulation else change.asc())
            .limit(limit)
        )
    ).all()
    direction = "accumulation" if accumulation else "distribution"
    return ScreenOut(
        key=f"institutional_13f_{direction}",
        title=f"13F reported {direction}",
        description=(
            "Largest quarter-over-quarter increases in aggregate reported shares"
            if accumulation
            else "Largest quarter-over-quarter reductions in aggregate reported shares"
        ),
        value_label="% reported shares",
        group="value",
        evidence="utility",
        items=[
            ScreenItem(
                code=code,
                last_close=last_close,
                value=round(net_change, 2),
                comparison_as_of=prior_report_date.isoformat() if prior_report_date else None,
                data_as_of=report_date.isoformat(),
                **_new_disclosure_fields(
                    prior_net_change,
                    direction="buy" if accumulation else "sell",
                    data_date=report_date.isoformat(),
                ),
            )
            for code, last_close, net_change, report_date, prior_report_date, prior_net_change in rows
        ],
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
    session,
    market: str,
    tenant_id: str,
    limit: int = PER_SCREEN,
    *,
    cap_tier: str | None = None,
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
                Cashtag.code.in_(
                    _screenable_codes(market, cap_tier)
                    if cap_tier is not None
                    else visible_codes(market)
                ),
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


async def _most_watched(
    session,
    market: str,
    tenant_id: str,
    limit: int = PER_SCREEN,
    *,
    cap_tier: str | None = None,
) -> ScreenOut:
    """Most-followed names — the community's 'Watchers' leaderboard."""
    cnt = func.count()
    rows = (
        await session.execute(
            select(WatchlistItem.code, cnt)
            .join(User, WatchlistItem.user_id == User.id)
            .where(
                WatchlistItem.market == market,
                WatchlistItem.code.in_(
                    _screenable_codes(market, cap_tier)
                    if cap_tier is not None
                    else visible_codes(market)
                ),
            )
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


async def _attention_rising(
    session,
    market: str,
    tenant_id: str,
    limit: int = PER_SCREEN,
    *,
    cap_tier: str | None = None,
) -> ScreenOut:
    """Symbols whose chatter is well above their own usual pace, from the buzz snapshots."""
    today = to_market_tz(dt.datetime.now(dt.UTC), market=market).date()
    rows = (
        await session.execute(
            select(TickerBuzzDaily.code, TickerBuzzDaily.date, TickerBuzzDaily.posts_24h).where(
                TickerBuzzDaily.market == market,
                TickerBuzzDaily.tenant_id == tenant_id,
                TickerBuzzDaily.date >= today - dt.timedelta(days=_BUZZ_HISTORY),
                TickerBuzzDaily.code.in_(
                    _screenable_codes(market, cap_tier)
                    if cap_tier is not None
                    else visible_codes(market)
                ),
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
    session,
    market: str,
    *,
    window: str = "12m",
    limit: int = PER_SCREEN,
    cap_tier: str | None = None,
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
                T.code.in_(_screenable_codes(market, cap_tier)),
                _liquid(market, cap_tier),
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


async def _build_spec(
    session,
    market: str,
    spec: ScreenSpec,
    limit: int,
    *,
    cap_tier: str | None = None,
) -> ScreenOut:
    rows = (
        await session.execute(
            select(T.code, T.last_close, spec.value)
            .where(
                T.market == market,
                spec.where,
                T.code.in_(_screenable_codes(market, cap_tier)),
                _liquid(market, cap_tier),
            )
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


def _money_mn(n: float | None, market: str) -> str:
    """Compact currency text from currency millions."""
    return format_money_millions(n, market, none="n/a")


def _bdt_mn(n: float | None) -> str:
    """Backward-compatible DSE compact money helper."""
    return _money_mn(n, "DSE")


def _metric_text(label: str, value: float, market: str = "DSE") -> str:
    profile = get_market_profile(market)
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
        return f"{_money_mn(value * 10, market)} turnover"
    if label == "pp":
        return f"{value:+.1f} pp stake change"
    if label in {"ROE", "volatility", "% today", "% period", "% YoY"}:
        return f"{value:+.1f}%"
    if label == "momentum":
        return f"{value:+.0f}% momentum"
    if label == "vs market":
        return f"{value:+.1f}% vs {profile.benchmark_label}"
    return f"{value:.2f} {label}"


def _liquidity_label(adtv_mn: float | None, category: str | None, market: str) -> str | None:
    settings = _screen_settings(market)
    if settings.dse_category_filter and category == "Z":
        return "High-risk: Z category"
    if adtv_mn is None:
        return None
    if adtv_mn >= 50:
        return "Deep liquidity"
    if adtv_mn >= 10:
        return "Tradeable liquidity"
    if adtv_mn >= settings.min_adtv_mn:
        return "Watch order size"
    return "Thin liquidity"


def _setup_quality(screen: ScreenOut, item: ScreenItem, market: str = "DSE") -> str | None:
    settings = _screen_settings(market)
    high_risk_note = (item.note or "").lower()
    if (
        (settings.dse_category_filter and item.category == "Z")
        or "pump" in high_risk_note
        or (screen.key == "dividend_yield" and item.value > 15)
        or (item.adtv_mn is not None and item.adtv_mn < settings.min_adtv_mn)
    ):
        return "High-risk read"
    if (
        item.adtv_mn is not None
        and item.adtv_mn >= 20
        and (
            item.catalyst
            or screen.key.startswith(_CHART_PATTERN_PREFIX)  # plain descriptive geometry per
            # type — unlike sponsor_selling, none of these assert a real disclosed negative fact
            # (they're explicitly "framework, not a signal"), so a liquidity-based supported read
            # applies the same way regardless of whether the shape leans bullish or bearish.
            or screen.key
            in {
                # institutional_selling/sponsor_selling are deliberately NOT here — a green
                # support chip is the wrong tone on a distribution/insider-selling board regardless
                # of how liquid the stock is.
                "institutional_buying",
                "foreign_buying",
                "quality_roe",
                "value_vs_sector",  # same shape as quality_roe: a plain value ranking, no
                # catalyst concept — omitting it meant "Cheap vs sector" could never show
                # a supported read even for a deep-liquidity Cat-A stock (confirmed live: BSC,
                # BSRMSTEEL, MALEKSPIN all had >20mn ADTV and zero risk flags, 2026-07-05).
                "dividend_yield",
                "beating_market",
                "quiet_accumulation",
            }
        )
    ):
        return "Screen checks met"
    return "Mixed evidence"


def _why_text(screen: ScreenOut, item: ScreenItem, market: str) -> str:
    metric = _metric_text(screen.value_label, item.value, market)
    parts = [f"{screen.title}: {metric}"]
    if item.change_1d is not None:
        parts.append(f"1D {item.change_1d:+.1f}%")
    if item.adtv_mn is not None and item.safe_order_mn is not None:
        parts.append(f"ADTV {_money_mn(item.adtv_mn, market)}")
        parts.append(f"5% size {_money_mn(item.safe_order_mn, market)}")
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
                T.code,
                T.last_close,
                T.avg_volume_20,
                T.market_cap_mn,
                T.free_float_cap_mn,
                T.cap_tier,
            ).where(T.market == market, T.code.in_(codes))
        )
    ).all()
    for code, last_close, avg_vol_20, market_cap_mn, free_float_cap_mn, tier in ta_rows:
        adtv_mn = (avg_vol_20 * last_close / 1e6) if avg_vol_20 and last_close else None
        out.setdefault(code, {}).update(
            {
                "adtv_mn": round(adtv_mn, 2) if adtv_mn is not None else None,
                "safe_order_mn": round(adtv_mn * 0.05, 2) if adtv_mn is not None else None,
                "market_cap_mn": round(market_cap_mn, 2) if market_cap_mn is not None else None,
                "free_float_cap_mn": round(free_float_cap_mn, 2)
                if free_float_cap_mn is not None
                else None,
                "cap_tier": tier,
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
    cutoff = to_market_tz(dt.datetime.now(dt.UTC), market=market).date() - dt.timedelta(days=21)
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
# Distinct title for the sell direction so it reads as its own board, not a mislabeled "Institutions"
# — a user pointed out that Sponsor Selling being its own headline while institutional distribution
# had no equivalent made it look like only insiders' selling mattered (2026-07-05).
_OWN_SELL_TITLE = {"foreign": "Foreign Selling", "institute": "Institutional Selling"}
# Only show rises big enough to read as real buying — below this they'd display as "+0.0 pp"
# (foreign stakes on DSE are tiny, so this keeps the screen honest rather than full of noise).
_MIN_STAKE_DELTA = 0.05


def _new_directional_disclosure(
    previous_delta: float | None, *, direction: str, threshold: float = 0.0
) -> bool:
    """True only when the preceding disclosure did not qualify for the current direction."""

    if previous_delta is None:
        return False
    return previous_delta < threshold if direction == "buy" else previous_delta > -threshold


def _new_disclosure_fields(
    previous_delta: float | None,
    *,
    direction: str,
    data_date: str | None,
    threshold: float = 0.0,
) -> dict[str, str]:
    if data_date and _new_directional_disclosure(
        previous_delta, direction=direction, threshold=threshold
    ):
        return {"new_since": data_date, "new_reason": "new_disclosure"}
    return {}


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
    session,
    market: str,
    *,
    kind: str,
    direction: str = "buy",
    limit: int = PER_SCREEN,
    cap_tier: str | None = None,
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
            .where(
                T.market == market,
                cond,
                T.code.in_(_screenable_codes(market, cap_tier)),
                _liquid(market, cap_tier),
            )
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
                comparison_as_of=f.dates[-2] if len(f.dates) >= 2 else None,
                data_as_of=f.dates[-1] if f.dates else None,
                period_spark=psparks.get(c, []),
                **_new_disclosure_fields(
                    f.prev_delta,
                    direction=direction,
                    threshold=_MIN_STAKE_DELTA,
                    data_date=f.dates[-1] if f.dates else None,
                ),
            )
        )
    verb = "trimmed" if selling else "raised"
    kind_name = "foreign" if kind == "foreign" else "institutional"
    return ScreenOut(
        key=f"{kind_name}_{'selling' if selling else 'buying'}",
        title=_OWN_SELL_TITLE[kind] if selling else title,
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


async def _sponsor_selling(
    session, market: str, limit: int = PER_SCREEN, *, cap_tier: str | None = None
) -> ScreenOut:
    """Insiders reducing their own stake — the disclosure-synthesis red-flag board.

    No sponsor delta lives in ticker_analytics, so the deltas come straight from the last two
    shareholding disclosures per code (the whole table is ~3 rows/stock — this is cheap)."""
    codes = list(await session.scalars(_screenable_codes(market, cap_tier)))
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
                    T.market == market,
                    T.code.in_([c for c, _, _ in drops]),
                    _liquid(market, cap_tier),
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
            comparison_as_of=f.dates[-2] if len(f.dates) >= 2 else None,
            data_as_of=f.dates[-1] if f.dates else None,
            period_spark=psparks.get(c, []),
            **_new_disclosure_fields(
                f.prev_delta,
                direction="sell",
                threshold=_MIN_SPONSOR_DROP,
                data_date=f.dates[-1] if f.dates else None,
            ),
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


_PATTERN_TITLE = {
    "high_volume_flat_base": "High-Volume Flat Base",
    "ascending_triangle": "Ascending Triangle",
    "descending_triangle": "Descending Triangle",
    "channel_up": "Rising Channel",
    "channel_down": "Falling Channel",
    "channel_horizontal": "Horizontal Channel",
    "double_top": "Double Top",
    "double_bottom": "Double Bottom",
}
_PATTERN_STATUS_TITLE = {
    "forming": "forming",
    "confirmed_breakout_up": "moved above the pattern boundary",
    "confirmed_breakout_down": "moved below the pattern boundary",
}
_CHART_PATTERN_PREFIX = "chart_pattern_"  # e.g. "chart_pattern_ascending_triangle"


async def _chart_pattern_board(
    session,
    market: str,
    pattern_type: str,
    limit: int = PER_SCREEN,
    *,
    cap_tier: str | None = None,
) -> ScreenOut:
    """Stocks currently showing ONE specific classic chart pattern (Finviz-style: e.g. just
    ascending triangles, or just double tops), precomputed nightly alongside ticker_analytics —
    see bulls.analytics.patterns.detect_patterns for the geometry. One board per pattern type
    (not a single combined list) — a user asked for this split so each shape reads as its own
    thing rather than everything blended into one list sorted only by strength score.

    Framework evidence, not backtested: this is textbook technical analysis, and our own factor
    study found the conceptually-related momentum factor actually hurt returns on DSE — see that
    module's docstring for the full reasoning."""
    rows = (
        await session.execute(
            select(
                TickerPattern.code,
                T.last_close,
                TickerPattern.status,
                TickerPattern.strength_score,
                TickerPattern.payload,
                func.count().over().label("total_count"),
            )
            .join(T, and_(T.market == TickerPattern.market, T.code == TickerPattern.code))
            .where(
                TickerPattern.market == market,
                TickerPattern.pattern_type == pattern_type,
                TickerPattern.status != "invalidated",
                T.code.in_(_screenable_codes(market, cap_tier)),
                _liquid(market, cap_tier),
            )
            .order_by(TickerPattern.strength_score.desc())
            .limit(limit)
        )
    ).all()
    items = []
    for code, lc, status, strength, payload, _total_count in rows:
        status_text = _PATTERN_STATUS_TITLE[status]
        why = f"{_PATTERN_TITLE[pattern_type]}, {status_text} (strength {strength:.0f}/100)."
        note = status_text
        if pattern_type == "high_volume_flat_base":
            metrics = (payload or {}).get("metrics", {})
            depth = float(metrics.get("base_depth_pct", 0))
            if status == "forming":
                distance = float(metrics.get("distance_to_breakout_pct", 0))
                note = f"forming {distance:.1f}% below resistance · {depth:.1f}% base"
                why = (
                    f"Tight 15-session base, {distance:.1f}% below resistance; breakout is not "
                    "confirmed. Historical watchlist structure, not a buy signal."
                )
            else:
                volume_ratio = float(metrics.get("volume_ratio", 0))
                note = f"breakout on {volume_ratio:.1f}x base volume · {depth:.1f}% base"
                why = (
                    f"Closed above a tight 15-session base on {volume_ratio:.1f}x base volume. "
                    "The DSE study found regime-dependent outcomes, not a stable standalone edge."
                )
        items.append(
            ScreenItem(
                code=code,
                last_close=lc,
                value=round(strength, 0),
                note=note,
                why=why,
                pattern_status=status,
                pattern_metrics=(payload or {}).get("metrics", {}),
            )
        )
    title = _PATTERN_TITLE[pattern_type]
    return ScreenOut(
        key=f"{_CHART_PATTERN_PREFIX}{pattern_type}",
        title=title,
        description=(
            "Liquid stocks compressing near resistance or clearing it on at least 2x base "
            "volume. Tested as a research watchlist, but not a proven standalone trade signal."
            if pattern_type == "high_volume_flat_base"
            else (
                f"Stocks currently forming or just resolving a {title.lower()}. Descriptive "
                "geometry, not a signal — see the lesson for what 'usually happens' means and "
                "doesn't mean."
            )
        ),
        value_label="score",
        group="technical",
        evidence="experimental" if pattern_type == "high_volume_flat_base" else "framework",
        total_count=int(rows[0].total_count) if rows else 0,
        items=items,
    )


async def _enrich(session, market: str, screens_list: list[ScreenOut]) -> None:
    """Fill name + 1d change + sparkline on every item, batched across all screens."""
    codes = sorted({it.code for s in screens_list for it in s.items})
    names = await _names(session, market, codes)
    # _NO_1D screens (top_gainers/top_losers) already show the move as their headline value, so
    # change_1d is suppressed per-screen below — but the code's change is still fetched here, since
    # the same code appears on OTHER boards (e.g. today's top gainer can also be in value_vs_sector)
    # and needs its 1D change there. Excluding it from this query too silently blanked it everywhere.
    changes = await _change_1d(session, market, codes)
    sparks = await _sparks(session, market, codes)
    context = await _execution_context(session, market, codes)
    catalysts = await _recent_catalysts(session, market, codes)
    for s in screens_list:
        default_evidence = "framework" if s.key.startswith(_CHART_PATTERN_PREFIX) else None
        mapped_evidence = _SCREEN_EVIDENCE.get(s.key)
        if mapped_evidence == "backtested" and market != "DSE":
            mapped_evidence = "framework"
        s.evidence = s.evidence or mapped_evidence or default_evidence
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
            it.cap_tier = ctx.get("cap_tier") if isinstance(ctx.get("cap_tier"), str) else None
            it.free_float_cap_mn = (
                ctx.get("free_float_cap_mn")
                if isinstance(ctx.get("free_float_cap_mn"), float)
                else None
            )
            it.liquidity = _liquidity_label(it.adtv_mn, it.category, market)
            catalyst = catalysts.get(it.code)
            if catalyst:
                it.catalyst = catalyst.headline
                it.catalyst_date = str(catalyst.published_at)
                it.catalyst_category = catalyst.category
            it.setup_quality = _setup_quality(s, it, market)
            # A board builder may have written a richer per-name sentence (e.g. the scanner's
            # Quality Reversal / Oversold Quality prose) — never clobber it with the generic line.
            it.why = it.why or _why_text(s, it, market)


def _filter_screens_by_cap_tier(
    screens_list: list[ScreenOut], *, cap_tier: str, limit: int
) -> None:
    """Narrow enriched, ranked screens without changing score or row order."""

    for screen in screens_list:
        screen.items = [item for item in screen.items if item.cap_tier == cap_tier][:limit]
        screen.total_count = len(screen.items)


def _validated_cap_tier(market: str, value: str | None) -> str | None:
    """Reject a tier that belongs to another market instead of returning a misleading empty list."""

    if value is None:
        return None
    valid_tiers = {tier for tier, _ in get_market_profile(market).cap_tiers}
    if value not in valid_tiers:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown size tier {value!r} for {market}; "
            f"expected one of {sorted(valid_tiers)}",
        )
    return value


_SPEC_BY_KEY = {s.key: s for s in _SCREENS}


async def build_screen(
    session,
    market: str,
    key: str,
    limit: int,
    *,
    tenant_id: str,
    direction: str = "buy",
    cap_tier: str | None = None,
) -> ScreenOut | None:
    """Build a single screen by key (used by the detail/explore page)."""
    if key in ("top_gainers", "top_losers"):
        return await _movers(
            session,
            market,
            gainers=key == "top_gainers",
            limit=limit,
            cap_tier=cap_tier,
        )
    if key == "most_active":
        return await _most_active(session, market, limit=limit, cap_tier=cap_tier)
    if key == "momentum_12_1":
        return await _momentum(session, market, limit=limit, cap_tier=cap_tier)
    if key == "unusual_volume":
        return await _unusual_volume(session, market, limit=limit, cap_tier=cap_tier)
    if key == "beating_market":
        return await _beating_market(session, market, limit=limit, cap_tier=cap_tier)
    if key == "foreign_buying":
        return await _ownership(
            session,
            market,
            kind="foreign",
            direction=direction,
            limit=limit,
            cap_tier=cap_tier,
        )
    if key == "institutional_buying":
        return await _ownership(
            session,
            market,
            kind="institute",
            direction=direction,
            limit=limit,
            cap_tier=cap_tier,
        )
    if key == "institutional_selling":
        # Its own headline board, not a toggle state — always distribution, mirroring sponsor_selling.
        return await _ownership(
            session,
            market,
            kind="institute",
            direction="sell",
            limit=limit,
            cap_tier=cap_tier,
        )
    if key == "institutional_13f_accumulation":
        return await _institutional_13f(
            session, market, accumulation=True, limit=limit, cap_tier=cap_tier
        )
    if key == "institutional_13f_distribution":
        return await _institutional_13f(
            session, market, accumulation=False, limit=limit, cap_tier=cap_tier
        )
    if key == "sponsor_selling":
        return await _sponsor_selling(session, market, limit=limit, cap_tier=cap_tier)
    if key.startswith(_CHART_PATTERN_PREFIX):
        return await _chart_pattern_board(
            session,
            market,
            pattern_type=key.removeprefix(_CHART_PATTERN_PREFIX),
            limit=limit,
            cap_tier=cap_tier,
        )
    if key == "most_watched":
        return await _most_watched(
            session, market, tenant_id=tenant_id, limit=limit, cap_tier=cap_tier
        )
    if key == "most_discussed":
        return await _most_discussed(
            session, market, tenant_id=tenant_id, limit=limit, cap_tier=cap_tier
        )
    if key == "attention_rising":
        return await _attention_rising(
            session, market, tenant_id=tenant_id, limit=limit, cap_tier=cap_tier
        )
    spec = _SPEC_BY_KEY.get(key)
    return (
        await _build_spec(session, market, spec, limit, cap_tier=cap_tier) if spec else None
    )


# Cache safety-sweep TTL. Real invalidation is the data-fingerprinted key (quote + analytics
# timestamps), so this only reaps keys for days/polls that will never be requested again.
_SCREENS_TTL = 6 * 60 * 60


@router.get("/screens")
async def screens(
    tenant: CurrentTenant,
    session: DbSession,
    size: str | None = Query(None, description="cap tier: mega | large | mid | small | micro"),
) -> ScreensResponse:
    """Cached, but keyed on data freshness so it's never staler than the data itself.

    The key folds in BOTH the latest quote snapshot (changes every 15-min poll → intraday prices /
    'today's move' stay current) AND the analytics recompute time (changes nightly at EOD → the
    screen rankings refresh). Within a poll window every request is a ~ms Redis read; the heavy
    multi-screen compute runs once per poll, not once per request.
    """
    enforce_market_feature(tenant, "curated_screens")
    market = tenant.market
    size = _validated_cap_tier(market, size)
    quote_ts = await session.scalar(
        select(func.max(QuoteSnapshot.as_of)).where(QuoteSnapshot.market == market)
    )
    ana_ts = await session.scalar(select(func.max(T.computed_at)).where(T.market == market))
    # Version bumps invalidate code/label changes; timestamps invalidate source-data changes.
    # v18 distinguishes refresh-to-refresh entries from source-derived disclosure entries.
    key = f"screens:v18:{tenant.name}:{market}:{size or 'all'}:{quote_ts}:{ana_ts}"
    membership_key = screen_membership_key(tenant.name, market, size)
    redis = aioredis.from_url(get_settings().redis_url)
    try:
        cached = await redis.get(key)
        if cached:
            # Serve the cached JSON bytes verbatim — skip the pydantic parse + re-serialize of ~65KB.
            return Response(content=cached, media_type="application/json")
        resp = await _build_screens(tenant, session, quote_ts, cap_tier=size)
        await update_screen_memberships(redis, membership_key, resp.screens)
        await redis.set(key, resp.model_dump_json(), ex=_SCREENS_TTL)
        return resp
    finally:
        await redis.aclose()


async def _build_screens(
    tenant: CurrentTenant,
    session: DbSession,
    quote_ts: dt.datetime | None,
    *,
    cap_tier: str | None = None,
) -> ScreensResponse:
    profile = get_market_profile(tenant.market)
    out: list[ScreenOut] = [
        await _build_spec(
            session,
            tenant.market,
            spec,
            PER_SCREEN,
            cap_tier=cap_tier,
        )
        for spec in _SCREENS
    ]
    out.append(
        await _movers(
            session, tenant.market, gainers=True, limit=PER_SCREEN, cap_tier=cap_tier
        )
    )
    out.append(
        await _movers(
            session, tenant.market, gainers=False, limit=PER_SCREEN, cap_tier=cap_tier
        )
    )
    out.append(
        await _most_active(session, tenant.market, limit=PER_SCREEN, cap_tier=cap_tier)
    )
    out.append(
        await _momentum(session, tenant.market, limit=PER_SCREEN, cap_tier=cap_tier)
    )
    out.append(
        await _unusual_volume(session, tenant.market, limit=PER_SCREEN, cap_tier=cap_tier)
    )
    out.append(
        await _beating_market(session, tenant.market, limit=PER_SCREEN, cap_tier=cap_tier)
    )
    if profile.features.shareholding_breakdown:
        out.append(
            await _ownership(
                session,
                tenant.market,
                kind="foreign",
                limit=PER_SCREEN,
                cap_tier=cap_tier,
            )
        )
        out.append(
            await _ownership(
                session,
                tenant.market,
                kind="institute",
                limit=PER_SCREEN,
                cap_tier=cap_tier,
            )
        )
        out.append(
            await _ownership(
                session,
                tenant.market,
                kind="institute",
                direction="sell",
                limit=PER_SCREEN,
                cap_tier=cap_tier,
            )
        )
    if profile.features.sponsor_director_disclosures:
        out.append(
            await _sponsor_selling(
                session, tenant.market, limit=PER_SCREEN, cap_tier=cap_tier
            )
        )
    if profile.features.institutional_holdings:
        out.append(
            await _institutional_13f(
                session,
                tenant.market,
                accumulation=True,
                limit=PER_SCREEN,
                cap_tier=cap_tier,
            )
        )
        out.append(
            await _institutional_13f(
                session,
                tenant.market,
                accumulation=False,
                limit=PER_SCREEN,
                cap_tier=cap_tier,
            )
        )
    for pattern_type in _PATTERN_TITLE:
        out.append(
            await _chart_pattern_board(
                session,
                tenant.market,
                pattern_type=pattern_type,
                limit=PER_SCREEN,
                cap_tier=cap_tier,
            )
        )
    out.append(
        await _most_watched(
            session,
            tenant.market,
            tenant_id=tenant.name,
            limit=PER_SCREEN,
            cap_tier=cap_tier,
        )
    )
    out.append(
        await _most_discussed(
            session,
            tenant.market,
            tenant_id=tenant.name,
            limit=PER_SCREEN,
            cap_tier=cap_tier,
        )
    )
    out.append(
        await _attention_rising(
            session,
            tenant.market,
            tenant.name,
            limit=PER_SCREEN,
            cap_tier=cap_tier,
        )
    )

    await _enrich(session, tenant.market, out)
    if cap_tier is not None:
        _filter_screens_by_cap_tier(out, cap_tier=cap_tier, limit=PER_SCREEN)
    # Page-level freshness must describe the newest analytics batch. A bare LIMIT 1 is unordered
    # and can label the whole page with any older ticker's date.
    as_of = await session.scalar(
        select(func.max(T.as_of_date)).where(T.market == tenant.market)
    )
    settings = _screen_settings(tenant.market)
    methodology = MarketMethodology(
        market=tenant.market,
        settlement_cycle=profile.settlement_cycle,
        data_clock=(
            f"End-of-day analytics from {profile.exchange_code} closes; "
            "live quote boards use latest quote snapshot."
        ),
        liquidity_floor=(
            "Institutional discovery: minimum 20-session average daily turnover and market cap; "
            "free-float cap floor is applied when available."
        ),
        min_adtv_mn=settings.min_adtv_mn,
        min_mcap_mn=_minimum_market_cap(tenant.market, cap_tier),
        min_free_float_cap_mn=settings.min_free_float_cap_mn,
    )
    return ScreensResponse(
        as_of=str(as_of) if as_of else None,
        quote_as_of=quote_ts.isoformat() if quote_ts else None,
        methodology=methodology,
        cap_tier=cap_tier,
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


async def _breadth(
    session, market: str, quote_cutoff: dt.datetime | None = None
) -> tuple[int, int, int, int]:
    conditions = [
        QuoteSnapshot.market == market,
        QuoteSnapshot.code.in_(visible_codes(market)),
    ]
    if quote_cutoff is not None:
        conditions.append(QuoteSnapshot.as_of >= quote_cutoff)
    adv, dec, flat, total = (
        await session.execute(
            select(
                func.count().filter(QuoteSnapshot.change_pct > 0),
                func.count().filter(QuoteSnapshot.change_pct < 0),
                func.count().filter(QuoteSnapshot.change_pct == 0),
                func.count(),
            ).where(*conditions)
        )
    ).one()
    return int(adv or 0), int(dec or 0), int(flat or 0), int(total or 0)


def _coverage_from_counts(published: int, eligible: int) -> tuple[int, int, float, bool]:
    """Normalize coverage counts and apply the explicit near-complete threshold."""
    published_n = max(0, int(published))
    eligible_n = max(0, int(eligible))
    ratio = min(1.0, published_n / eligible_n) if eligible_n else 0.0
    return published_n, eligible_n, round(ratio, 4), eligible_n > 0 and ratio >= 0.95


async def _universe_coverage(session, market: str) -> tuple[int, int, float, bool]:
    """Published research coverage versus the active product-eligible symbol universe.

    Breadth over a launch cohort is useful, but it is not exchange-wide breadth. Keeping the
    denominator in the API prevents any tenant UI from silently overstating its scope.
    """
    published, eligible = (
        await session.execute(
            select(
                func.count().filter(Symbol.data_status == "ready"),
                func.count(),
            ).where(
                Symbol.market == market,
                Symbol.is_active.is_(True),
                Symbol.is_hidden.is_(False),
            )
        )
    ).one()
    return _coverage_from_counts(published or 0, eligible or 0)


async def _sector_rows(
    session, market: str, quote_cutoff: dt.datetime | None = None
) -> list[SectorRow]:
    avg_chg = func.avg(QuoteSnapshot.change_pct)
    adv = func.count().filter(QuoteSnapshot.change_pct > 0)
    dec = func.count().filter(QuoteSnapshot.change_pct < 0)
    conditions = [
        Symbol.market == market,
        Symbol.code.in_(visible_codes(market)),
        Symbol.sector.isnot(None),
    ]
    if quote_cutoff is not None:
        conditions.append(QuoteSnapshot.as_of >= quote_cutoff)
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
            .where(*conditions)
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


def _intraday_risk_mode(adv: int, dec: int) -> str:
    """Quote-only intraday regime when the official benchmark is still yesterday's close."""

    decided = adv + dec
    breadth = adv / decided if decided else 0.5
    if breadth >= 0.58:
        return "risk_on"
    if breadth <= 0.42:
        return "defensive"
    return "mixed"


def _turnover_ratio(
    current_turnover: float | None, completed_turnovers: list[float]
) -> float | None:
    """Compare one turnover reading with up to 20 completed sessions."""

    baseline = completed_turnovers[:20]
    average = sum(baseline) / len(baseline) if baseline else None
    if current_turnover is None or not average:
        return None
    return round(current_turnover / average, 2)


def _select_live_turnover(
    reported_turnover: float | None,
    reported_count: int,
    total_count: int,
    estimated_turnover: float | None,
) -> tuple[float | None, bool]:
    """Prefer provider-reported value when it covers at least 95% of the quote batch."""

    reported_coverage = reported_count / total_count if total_count else 0.0
    if reported_turnover is not None and reported_coverage >= 0.95:
        return float(reported_turnover), False
    return (float(estimated_turnover) if estimated_turnover is not None else None), True


@router.get("/market-pulse")
async def market_pulse(tenant: CurrentTenant, session: DbSession) -> MarketPulseOut:
    """One institutional-style market regime read before drilling into individual screens."""
    enforce_market_feature(tenant, "curated_screens")
    market = tenant.market
    summary = await session.scalar(
        select(MarketSummary)
        .where(MarketSummary.market == market)
        .order_by(MarketSummary.date.desc())
        .limit(1)
    )
    completed_turnovers = list(
        (
            await session.scalars(
                select(MarketSummary.total_value_mn)
                .where(MarketSummary.market == market, MarketSummary.total_value_mn.isnot(None))
                .order_by(MarketSummary.date.desc())
                .limit(21)
            )
        ).all()
    )
    quote_ts = await session.scalar(
        select(func.max(QuoteSnapshot.as_of)).where(QuoteSnapshot.market == market)
    )
    if quote_ts is not None and quote_ts.tzinfo is None:
        quote_ts = quote_ts.replace(tzinfo=dt.UTC)
    close_as_of = summary.date if summary else None
    data_status = quote_data_status(dt.datetime.now(dt.UTC), market, quote_ts, close_as_of)
    quote_date = to_market_tz(quote_ts, market=market).date() if quote_ts else None
    quotes_lead_close = bool(
        quote_date is not None and (close_as_of is None or quote_date > close_as_of)
    )
    quote_cutoff = quote_ts - dt.timedelta(minutes=30) if quote_ts else None

    adv, dec, flat, total = await _breadth(session, market, quote_cutoff)
    _, eligible, _, _ = await _universe_coverage(session, market)
    published, eligible, coverage_ratio, coverage_complete = _coverage_from_counts(total, eligible)
    sectors = await _sector_rows(session, market, quote_cutoff)

    live_turnover = None
    turnover_is_estimated = False
    if quotes_lead_close and quote_cutoff is not None:
        reported_turnover, reported_count, estimated_turnover = (
            await session.execute(
                select(
                    func.sum(QuoteSnapshot.turnover_mn),
                    func.count().filter(QuoteSnapshot.turnover_mn.isnot(None)),
                    func.sum(QuoteSnapshot.volume * QuoteSnapshot.ltp) / 1_000_000,
                ).where(
                    QuoteSnapshot.market == market,
                    QuoteSnapshot.code.in_(visible_codes(market)),
                    QuoteSnapshot.as_of >= quote_cutoff,
                )
            )
        ).one()
        live_turnover, turnover_is_estimated = _select_live_turnover(
            reported_turnover,
            int(reported_count or 0),
            total,
            estimated_turnover,
        )

    if quotes_lead_close:
        turnover_mn = float(live_turnover) if live_turnover is not None else None
        turnover_vs_20d = _turnover_ratio(turnover_mn, completed_turnovers)
    else:
        turnover_mn = (
            float(summary.total_value_mn)
            if summary and summary.total_value_mn is not None
            else None
        )
        turnover_vs_20d = _turnover_ratio(turnover_mn, completed_turnovers[1:])

    benchmark_close = summary.benchmark_close or summary.dsex if summary else None
    benchmark_change = (
        summary.benchmark_change
        if summary and summary.benchmark_change is not None
        else summary.dsex_change
        if summary
        else None
    )
    dsex_pct = _index_pct_from_points(benchmark_close, benchmark_change)
    top = sectors[0] if sectors else None
    weak = sectors[-1] if sectors else None
    return MarketPulseOut(
        as_of=str(quote_date or close_as_of) if (quote_date or close_as_of) else None,
        quote_as_of=quote_ts.isoformat() if quote_ts else None,
        close_as_of=str(close_as_of) if close_as_of else None,
        data_status=data_status,
        benchmark_is_live=False,
        turnover_is_partial=quotes_lead_close and data_status != "official_close",
        turnover_is_estimated=quotes_lead_close and turnover_is_estimated,
        dsex=round(summary.dsex, 2) if summary and summary.dsex is not None else None,
        dsex_change_pct=dsex_pct,
        turnover_cr=round(turnover_mn / 10, 1) if turnover_mn is not None else None,
        benchmark_label=get_market_profile(market).benchmark_label,
        benchmark_close=round(benchmark_close, 2) if benchmark_close is not None else None,
        benchmark_change_pct=dsex_pct,
        turnover_mn=round(turnover_mn, 1) if turnover_mn is not None else None,
        turnover_vs_20d=turnover_vs_20d,
        advancers=adv,
        decliners=dec,
        unchanged=flat,
        total=total,
        published_symbols=published,
        eligible_symbols=eligible,
        coverage_ratio=coverage_ratio,
        coverage_complete=coverage_complete,
        top_sector=top.sector if top else None,
        top_sector_change=top.avg_change if top else None,
        weak_sector=weak.sector if weak else None,
        weak_sector_change=weak.avg_change if weak else None,
        risk_mode=(
            "mixed"
            if data_status == "stale"
            else _intraday_risk_mode(adv, dec)
            if quotes_lead_close
            else _risk_mode(dsex_pct, turnover_vs_20d, adv, dec)
        ),
    )


@router.get("/sectors")
async def sectors(tenant: CurrentTenant, session: DbSession) -> list[SectorRow]:
    """Today's move aggregated by sector — DSE retail thinks in sectors (bank, pharma, textile…).
    Average change + advancers/decliners breadth across the visible universe, hottest first."""
    enforce_market_feature(tenant, "curated_screens")
    return await _sector_rows(session, tenant.market)


_PERIOD_DAYS = {"1d": 1, "5d": 5, "7d": 7, "15d": 15, "1m": 22}  # trading-days back for movers


async def _movers_period(
    session,
    market: str,
    *,
    gainers: bool,
    days: int,
    limit: int,
    cap_tier: str | None = None,
) -> ScreenOut:
    """Top gainers/losers over a trailing window, from the daily bars (EOD-consistent)."""
    rn = (
        func.row_number()
        .over(partition_by=DailyBar.code, order_by=DailyBar.date.desc())
        .label("rn")
    )
    ranked = (
        select(DailyBar.code, DailyBar.close, rn)
        .where(DailyBar.market == market, DailyBar.code.in_(_investable(market, cap_tier)))
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
    """Configured benchmark index % change over the trailing `days` sessions."""
    benchmark = func.coalesce(MarketSummary.benchmark_close, MarketSummary.dsex)
    levels = (
        await session.scalars(
            select(benchmark)
            .where(MarketSummary.market == market, benchmark.isnot(None))
            .order_by(MarketSummary.date.desc())
            .limit(days + 1)
        )
    ).all()
    if len(levels) < days + 1 or not levels[days]:
        return None
    return (levels[0] - levels[days]) / levels[days] * 100


async def _beating_market(
    session, market: str, *, limit: int = PER_SCREEN, cap_tier: str | None = None
) -> ScreenOut:
    """Stocks outperforming the market benchmark over ~1 month — relative strength, the institutional tell for
    genuine strength (up while, or more than, the market). Value = excess return vs the index."""
    idx = await _index_return(session, market, _RS_DAYS)
    desc_idx = f"{idx:+.1f}%" if idx is not None else "n/a"
    benchmark = get_market_profile(market).benchmark_label
    base = ScreenOut(
        key="beating_market",
        title="Beating the market",
        description=f"Outperforming {benchmark} ({desc_idx} over ~1 month)",
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
        .where(DailyBar.market == market, DailyBar.code.in_(_investable(market, cap_tier)))
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
    size: str | None = Query(None, description="cap tier: mega | large | mid | small | micro"),
) -> ScreenOut:
    """One screen's full list — for the explore page's tab view.

    `size` narrows the database candidate universe to one canonical cap tier before ranking.
    The frontend also keeps this choice tenant-local, so a DSE preference cannot affect US.
    Ranking rules are unchanged, and total_count keeps meaning "rows shown".
    """
    enforce_market_feature(tenant, "curated_screens")
    size = _validated_cap_tier(tenant.market, size)
    if key in ("top_gainers", "top_losers") and period in _PERIOD_DAYS:
        screen = await _movers_period(
            session,
            tenant.market,
            gainers=key == "top_gainers",
            days=_PERIOD_DAYS[period],
            limit=limit,
            cap_tier=size,
        )
    elif key == "momentum_12_1":
        screen = await _momentum(
            session,
            tenant.market,
            window=window if window in _MOM_FIELD else "12m",
            limit=limit,
            cap_tier=size,
        )
    elif key == "unusual_volume":
        screen = await _unusual_volume(
            session,
            tenant.market,
            window=period if period in _RVOL_FIELD else "1d",
            limit=limit,
            cap_tier=size,
        )
    else:
        screen = await build_screen(
            session,
            tenant.market,
            key,
            limit,
            tenant_id=tenant.name,
            direction="sell" if direction == "sell" else "buy",
            cap_tier=size,
        )
    if screen is None:
        raise HTTPException(status_code=404, detail=f"Unknown screen {key!r}")
    await _enrich(session, tenant.market, [screen])
    if size is not None:
        _filter_screens_by_cap_tier([screen], cap_tier=size, limit=limit)
    redis = aioredis.from_url(get_settings().redis_url)
    try:
        with suppress(RedisError):
            await apply_stored_screen_memberships(
                redis,
                screen_membership_key(tenant.name, tenant.market, size),
                [screen],
            )
    finally:
        await redis.aclose()
    return screen
