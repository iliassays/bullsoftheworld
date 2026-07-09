"""Market read endpoints — surface what ingestion persisted.

Everything is scoped to the active tenant's market, so Bulls of Dhaka only ever sees DSE.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import asdict
from typing import Any
from zoneinfo import ZoneInfo

import redis.asyncio as aioredis
from fastapi import APIRouter, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import case, func, or_, select

from api.deps import CurrentLocale, CurrentTenant, DbSession, visible_codes
from bulls.analytics import (
    AnalyticsResult,
    MoodIndex,
    PatternMatch,
    build_mood,
    compute,
    detect_patterns,
)
from bulls.core.config import get_settings
from bulls.core.markets import get_market_profile
from bulls.core.models import (
    Announcement,
    CompanyLogo,
    DailyBar,
    MarketSummary,
    QuoteSnapshot,
    Symbol,
    TickerAnalytics,
    TrendingScore,
)
from bulls.core.schemas.market import BarOut, QuoteOut, SymbolDetail, SymbolOut
from bulls.market_data.calendar import market_close, session_phase

_MOOD_TTL = 3600  # 1h — the mood is an EOD-stable, slow-changing read

router = APIRouter(tags=["market"])

_MIN_ADTV_MN = 5.0


def _escape_like(value: str) -> str:
    """Escape user input used inside SQL LIKE patterns."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class MarketStatusOut(BaseModel):
    """Where the session is right now (holiday-aware) + the latest quote timestamp, for the header."""

    phase: str  # open | pre_open | post_close | weekend (weekend covers public holidays too)
    as_of: str | None


class MarketConfigOut(BaseModel):
    market: str
    exchange_code: str
    exchange_label_bn: str | None
    exchange_name: str
    exchange_name_bn: str | None
    country_code: str
    currency_code: str
    currency_symbol: str
    timezone: str
    timezone_label: str
    place_label_en: str
    place_label_bn: str
    open_time: str
    close_time: str
    settlement_cycle: str
    benchmark_label: str
    default_locale: str
    price_decimals: int
    compact_money_units: list[dict[str, float | int | str]]
    market_cap_money_units: list[dict[str, float | int | str]]
    features: dict[str, bool]
    tenant_name: str
    brand_name: str


@router.get("/market/config")
async def market_config(tenant: CurrentTenant) -> MarketConfigOut:
    profile = get_market_profile(tenant.market)
    return MarketConfigOut(
        market=profile.market,
        exchange_code=profile.exchange_code,
        exchange_label_bn=profile.exchange_label_bn,
        exchange_name=profile.exchange_name,
        exchange_name_bn=profile.exchange_name_bn,
        country_code=profile.country_code,
        currency_code=profile.currency_code,
        currency_symbol=profile.currency_symbol,
        timezone=profile.timezone,
        timezone_label=profile.timezone_label,
        place_label_en=profile.place_label_en,
        place_label_bn=profile.place_label_bn,
        open_time=profile.open_time.isoformat(timespec="minutes"),
        close_time=profile.close_time.isoformat(timespec="minutes"),
        settlement_cycle=profile.settlement_cycle,
        benchmark_label=profile.benchmark_label,
        default_locale=profile.default_locale,
        price_decimals=profile.price_decimals,
        compact_money_units=[asdict(unit) for unit in profile.compact_money_units],
        market_cap_money_units=[asdict(unit) for unit in profile.market_cap_money_units],
        features=asdict(profile.features),
        tenant_name=tenant.name,
        brand_name=tenant.display_name,
    )


@router.get("/market/status")
async def market_status(tenant: CurrentTenant, session: DbSession) -> MarketStatusOut:
    phase = session_phase(dt.datetime.now(dt.UTC), ZoneInfo(tenant.timezone), market=tenant.market)
    quote_ts = await session.scalar(
        select(func.max(QuoteSnapshot.as_of)).where(QuoteSnapshot.market == tenant.market)
    )
    return MarketStatusOut(phase=str(phase), as_of=quote_ts.isoformat() if quote_ts else None)


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


class TrendingStockOut(BaseModel):
    """One row of the daily 'Watch today' activity ranking — descriptive, not a recommendation."""

    code: str
    name_en: str
    name_bn: str | None
    ltp: float | None
    change_pct: float
    direction: str
    heating_up: bool
    reasons: list[dict[str, Any]]
    category: str | None = None
    adtv_mn: float | None = None
    safe_order_mn: float | None = None
    turnover_mn: float | None = None
    liquidity: str | None = None


@router.get("/trending-stocks")
async def trending_stocks(
    tenant: CurrentTenant, session: DbSession, limit: int = Query(15, ge=1, le=25)
) -> list[TrendingStockOut]:
    """Precomputed nightly by the worker (anomaly-ranked by self-normalized volume + turnover surge,
    liquidity-gated). The frontend just reads this ordered list."""
    rows = list(
        await session.scalars(
            select(TrendingScore)
            .where(TrendingScore.market == tenant.market)
            .order_by(TrendingScore.rank)
            .limit(limit)
        )
    )
    if not rows:
        return []
    codes = [r.code for r in rows]
    names = {
        s.code: s
        for s in await session.scalars(
            select(Symbol).where(Symbol.market == tenant.market, Symbol.code.in_(codes))
        )
    }
    snapshots = {
        q.code: q
        for q in await session.scalars(
            select(QuoteSnapshot).where(
                QuoteSnapshot.market == tenant.market, QuoteSnapshot.code.in_(codes)
            )
        )
    }
    analytics = {
        a.code: a
        for a in await session.scalars(
            select(TickerAnalytics).where(
                TickerAnalytics.market == tenant.market,
                TickerAnalytics.code.in_(codes),
            )
        )
    }
    out: list[TrendingStockOut] = []
    for r in rows:
        symbol = names.get(r.code)
        quote = snapshots.get(r.code)
        ta = analytics.get(r.code)
        adtv_mn = (
            ta.avg_volume_20 * ta.last_close / 1e6
            if ta and ta.avg_volume_20 and ta.last_close
            else None
        )
        turnover_mn = (
            quote.volume * quote.ltp / 1e6
            if quote and quote.volume is not None and quote.ltp is not None
            else None
        )
        out.append(
            TrendingStockOut(
                code=r.code,
                name_en=(symbol.name_en if symbol else r.code),
                name_bn=(symbol.name_bn if symbol else None),
                ltp=quote.ltp if quote else None,
                change_pct=r.change_pct,
                direction=r.direction,
                heating_up=r.heating_up,
                reasons=r.reasons,
                category=(symbol.category if symbol else None),
                adtv_mn=round(adtv_mn, 2) if adtv_mn is not None else None,
                safe_order_mn=round(adtv_mn * 0.05, 2) if adtv_mn is not None else None,
                turnover_mn=round(turnover_mn, 2) if turnover_mn is not None else None,
                liquidity=_liquidity_label(adtv_mn, symbol.category if symbol else None),
            )
        )
    return out


class EarningsEventOut(BaseModel):
    """One upcoming earnings board meeting — the date a company will consider its results."""

    code: str
    name_en: str
    name_bn: str | None = None
    category: str | None = None
    meeting_date: str
    period: str | None = None


@router.get("/market/earnings-calendar")
async def earnings_calendar(
    tenant: CurrentTenant,
    session: DbSession,
    days: int = Query(7, ge=1, le=30),
    back: int = Query(0, ge=0, le=7, description="Also include this many past days (week views)"),
) -> list[EarningsEventOut]:
    """Upcoming earnings — board meetings called to consider financials within the next `days`.

    Descriptive heads-up only: the date + period come straight from the decoded DSE board-meeting
    notice (companies can still reschedule). One row per company, nearest date first.
    """
    today = dt.datetime.now(dt.UTC).date()
    since = today - dt.timedelta(days=back)
    until = today + dt.timedelta(days=days)
    meeting_date = Announcement.details["meeting_date"].astext
    rows = list(
        await session.scalars(
            select(Announcement)
            .where(
                Announcement.market == tenant.market,
                Announcement.category == "board_meeting",
                meeting_date >= since.isoformat(),
                meeting_date <= until.isoformat(),
            )
            .order_by(meeting_date.asc(), Announcement.strength.desc())
        )
    )
    # Earnings meetings only (agenda includes financials), one per code — the earliest wins since
    # rows are already date-ordered.
    by_code: dict[str, Announcement] = {}
    for a in rows:
        if "financials" in ((a.details or {}).get("agenda") or []):
            by_code.setdefault(a.code, a)
    if not by_code:
        return []
    names = {
        s.code: s
        for s in await session.scalars(
            select(Symbol).where(Symbol.market == tenant.market, Symbol.code.in_(list(by_code)))
        )
    }
    events = [
        EarningsEventOut(
            code=code,
            name_en=(names[code].name_en if code in names else code),
            name_bn=(names[code].name_bn if code in names else None),
            category=(names[code].category if code in names else None),
            meeting_date=(a.details or {}).get("meeting_date", ""),
            period=(a.details or {}).get("period"),
        )
        for code, a in by_code.items()
    ]
    events.sort(key=lambda e: e.meeting_date)
    return events


@router.get("/symbols/{code}/logo")
async def get_symbol_logo(code: str, tenant: CurrentTenant, session: DbSession) -> Response:
    """Cached company logo bytes (fetched from the company website at onboarding). 404 when we have
    none — the frontend then falls back to a monogram."""
    logo = await session.get(CompanyLogo, (tenant.market, code.upper()))
    if logo is None or logo.image is None:
        raise HTTPException(status_code=404, detail="no logo")
    return Response(
        content=logo.image,
        media_type=logo.content_type or "image/png",
        headers={"Cache-Control": "public, max-age=86400"},  # logos change rarely
    )


# Enough history for the longest indicator (200-day SMA) plus headroom.
_ANALYTICS_LOOKBACK = 260


async def _freshest_quote(
    session, market: str, code: str, snapshot: QuoteSnapshot | None, tz: ZoneInfo
) -> QuoteOut | None:
    """Prefer the latest EOD bar when it's newer than the intraday snapshot.

    The intraday scrape (QuoteSnapshot) and the EOD bars update on different schedules; after the
    close the bar is the freshest truth, so the header price/date matches the analytics cards
    instead of showing a day-stale snapshot.
    """
    bars = list(
        await session.scalars(
            select(DailyBar)
            .where(DailyBar.market == market, DailyBar.code == code)
            .order_by(DailyBar.date.desc())
            .limit(2)
        )
    )
    if bars and (snapshot is None or bars[0].date > snapshot.as_of.date()):
        bar = bars[0]
        prev_close = bars[1].close if len(bars) > 1 else None
        change = bar.close - prev_close if prev_close is not None else 0.0
        change_pct = (change / prev_close * 100) if prev_close else 0.0
        return QuoteOut(
            market=bar.market,
            code=bar.code,
            ltp=bar.close,
            change=round(change, 2),
            change_pct=round(change_pct, 2),
            open=bar.open,
            high=bar.high,
            low=bar.low,
            close=bar.close,
            prev_close=prev_close,
            volume=bar.volume,
            trades=0,
            as_of=dt.datetime.combine(bar.date, market_close(market), tzinfo=tz),
            is_delayed=True,
        )
    return QuoteOut.model_validate(snapshot) if snapshot else None


@router.get("/quotes")
async def get_quotes(
    tenant: CurrentTenant,
    session: DbSession,
    codes: str | None = Query(None, description="Comma-separated codes, e.g. GP,BEXIMCO"),
) -> list[QuoteOut]:
    stmt = select(QuoteSnapshot).where(
        QuoteSnapshot.market == tenant.market,
        QuoteSnapshot.code.in_(visible_codes(tenant.market)),
    )
    if codes:
        wanted = [c.strip().upper() for c in codes.split(",") if c.strip()]
        stmt = stmt.where(QuoteSnapshot.code.in_(wanted))
    else:
        # default: top movers by change%
        stmt = stmt.order_by(QuoteSnapshot.change_pct.desc()).limit(50)
    rows = (await session.execute(stmt)).scalars().all()
    return [QuoteOut.model_validate(r) for r in rows]


@router.get("/symbols")
async def list_symbols(
    tenant: CurrentTenant,
    session: DbSession,
    limit: int = Query(100, ge=1, le=500),
    q: str | None = Query(None, min_length=1, max_length=64),
) -> list[SymbolOut]:
    raw_query = q.strip() if q else ""
    stmt = (
        select(Symbol)
        .where(
            Symbol.market == tenant.market,
            Symbol.is_active.is_(True),
            Symbol.is_hidden.is_(False),
        )
        .limit(limit)
    )
    if raw_query:
        raw_like = _escape_like(raw_query)
        upper = raw_query.upper()
        upper_like = _escape_like(upper)
        code_upper = func.upper(Symbol.code)
        name_upper = func.upper(Symbol.name_en)
        name_bn_match = Symbol.name_bn.ilike(f"%{raw_like}%", escape="\\")
        stmt = stmt.where(
            or_(
                code_upper.like(f"{upper_like}%", escape="\\"),
                name_upper.like(f"%{upper_like}%", escape="\\"),
                name_bn_match,
            )
        ).order_by(
            case(
                (code_upper == upper, 0),
                (code_upper.like(f"{upper_like}%", escape="\\"), 1),
                (name_upper.like(f"{upper_like}%", escape="\\"), 2),
                else_=3,
            ),
            Symbol.code,
        )
    else:
        stmt = stmt.order_by(Symbol.code)
    rows = (await session.execute(stmt)).scalars().all()
    return [SymbolOut.model_validate(r) for r in rows]


@router.get("/symbols/{code}")
async def get_symbol(code: str, tenant: CurrentTenant, session: DbSession) -> SymbolDetail:
    key = (tenant.market, code.upper())
    symbol = await session.get(Symbol, key)
    if symbol is None:
        raise HTTPException(status_code=404, detail=f"Unknown symbol {code!r} in {tenant.market}")
    snapshot = await session.get(QuoteSnapshot, key)
    quote = await _freshest_quote(session, key[0], key[1], snapshot, ZoneInfo(tenant.timezone))
    return SymbolDetail(symbol=SymbolOut.model_validate(symbol), quote=quote)


@router.get("/symbols/{code}/bars")
async def get_bars(
    code: str,
    tenant: CurrentTenant,
    session: DbSession,
    limit: int = Query(180, ge=1, le=2000, description="Most recent N daily bars"),
) -> list[BarOut]:
    """OHLCV history, oldest-first, with the current delayed quote appended during the session."""
    code = code.upper()
    stmt = (
        select(DailyBar)
        .where(DailyBar.market == tenant.market, DailyBar.code == code)
        .order_by(DailyBar.date.desc())
        .limit(limit)
    )
    rows = list(await session.scalars(stmt))
    rows.reverse()  # charts want ascending time
    out = [BarOut.model_validate(r) for r in rows]

    snapshot = await session.get(QuoteSnapshot, (tenant.market, code))
    if snapshot is not None:
        quote_date = snapshot.as_of.astimezone(ZoneInfo(tenant.timezone)).date()
        last_date = out[-1].date if out else None
        if last_date is None or quote_date > last_date:
            open_price = snapshot.open or snapshot.prev_close or snapshot.ltp
            high = max(snapshot.high, snapshot.ltp, open_price)
            low = min(snapshot.low, snapshot.ltp, open_price)
            out.append(
                BarOut(
                    date=quote_date,
                    open=open_price,
                    high=high,
                    low=low,
                    close=snapshot.ltp,
                    volume=snapshot.volume,
                )
            )
            out = out[-limit:]
    return out


class AnalyticsWithPatterns(AnalyticsResult):
    """AnalyticsResult + any currently-active chart pattern, computed live over the same bars —
    cheap for a single symbol, unlike the Ideas board's market-wide scan (which reads the
    precomputed ticker_patterns table instead; see screener.py::_chart_patterns).

    evidence is always "framework": classic technical analysis, not proven to have an edge on
    DSE (see bulls.analytics.patterns' module docstring)."""

    patterns: list[PatternMatch] = Field(default_factory=list)


@router.get("/symbols/{code}/analytics")
async def get_analytics(
    code: str, tenant: CurrentTenant, session: DbSession
) -> AnalyticsWithPatterns:
    """Deterministic technical-analysis snapshot for a symbol (descriptive facts only).

    Pure computation over end-of-day bars — trend, momentum, levels, volume. No recommendation.
    """
    code = code.upper()
    symbol = await session.get(Symbol, (tenant.market, code))
    if symbol is None:
        raise HTTPException(status_code=404, detail=f"Unknown symbol {code!r} in {tenant.market}")

    stmt = (
        select(DailyBar)
        .where(DailyBar.market == tenant.market, DailyBar.code == code)
        .order_by(DailyBar.date.desc())
        .limit(_ANALYTICS_LOOKBACK)
    )
    rows = list(await session.scalars(stmt))
    if not rows:
        raise HTTPException(status_code=404, detail=f"No price history for {code!r} yet")
    rows.reverse()  # engine expects oldest-first
    result = compute(rows)
    return AnalyticsWithPatterns(**result.model_dump(), patterns=detect_patterns(rows))


async def _mood_inputs(session, market: str) -> dict[str, Any]:
    """Gather the raw stats the Dhaka Mood Index is built from — all from persisted tables."""
    codes = visible_codes(market)

    adv, dec = (
        await session.execute(
            select(
                func.count().filter(QuoteSnapshot.change_pct > 0),
                func.count().filter(QuoteSnapshot.change_pct < 0),
            ).where(QuoteSnapshot.market == market, QuoteSnapshot.code.in_(codes))
        )
    ).one()

    # % of the liquid universe above its 200-day average (only rows where the MA is defined).
    above, total_ma = (
        await session.execute(
            select(
                func.count().filter(TickerAnalytics.above_sma_200.is_(True)),
                func.count(),
            ).where(
                TickerAnalytics.market == market,
                TickerAnalytics.code.in_(codes),
                TickerAnalytics.sma_200.isnot(None),
            )
        )
    ).one()
    pct_above = (above / total_ma) if total_ma else None

    # Shares pressed against their 52-week extremes (within 3%).
    n_high, n_low = (
        await session.execute(
            select(
                func.count().filter(TickerAnalytics.pct_from_52w_high >= -3),
                func.count().filter(TickerAnalytics.pct_from_52w_low <= 3),
            ).where(TickerAnalytics.market == market, TickerAnalytics.code.in_(codes))
        )
    ).one()

    # DSEX history for the volatility read + latest date for the as-of stamp.
    summaries = list(
        await session.scalars(
            select(MarketSummary)
            .where(MarketSummary.market == market)
            .order_by(MarketSummary.date.desc())
            .limit(120)
        )
    )
    dsex_closes = [s.dsex for s in reversed(summaries) if s.dsex is not None]
    as_of = str(summaries[0].date) if summaries else ""

    # Turnover vs its trailing 20-day average (context chip, not scored).
    values = [s.total_value_mn for s in summaries if s.total_value_mn is not None]
    turnover_vs_20d = None
    if len(values) > 1:
        prior = values[1:21]
        avg = sum(prior) / len(prior) if prior else None
        if avg:
            turnover_vs_20d = round(values[0] / avg, 2)

    return {
        "as_of_date": as_of,
        "advancers": int(adv or 0),
        "decliners": int(dec or 0),
        "pct_above_200dma": pct_above,
        "n_near_52w_high": int(n_high or 0),
        "n_near_52w_low": int(n_low or 0),
        "dsex_closes": dsex_closes,
        "turnover_vs_20d": turnover_vs_20d,
    }


@router.get("/market-mood")
async def market_mood(
    tenant: CurrentTenant, session: DbSession, locale: CurrentLocale
) -> MoodIndex:
    """Dhaka Mood Index — a descriptive 0-100 fear/greed read built from breadth, strength,
    52-week highs/lows and DSEX volatility. Deterministic and templated (no AI); cached per day."""
    cache_key = f"mood:v1:{tenant.market}:{locale}"
    redis = aioredis.from_url(get_settings().redis_url)
    try:
        cached = await redis.get(cache_key)
        if cached:
            return MoodIndex.model_validate_json(cached)
        mood = build_mood(locale=locale, **await _mood_inputs(session, tenant.market))
        await redis.set(cache_key, mood.model_dump_json(), ex=_MOOD_TTL)
        return mood
    finally:
        await redis.aclose()
