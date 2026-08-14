"""Market read endpoints — surface what ingestion persisted.

Everything is scoped to the active tenant's market, so Bulls of Dhaka only ever sees DSE.
"""

from __future__ import annotations

import datetime as dt
import itertools
import statistics
from collections.abc import Sequence
from dataclasses import asdict
from typing import Any
from zoneinfo import ZoneInfo

import redis.asyncio as aioredis
from fastapi import APIRouter, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import case, func, or_, select

from api.deps import (
    CurrentLocale,
    CurrentTenant,
    DbSession,
    enforce_market_feature,
    visible_codes,
)
from api.market_freshness import quote_data_status
from bulls.analytics import (
    AnalyticsResult,
    MoodIndex,
    PatternMatch,
    adjust_bars,
    build_mood,
    compute,
    detect_patterns,
)
from bulls.analytics.research_conditions import ResearchBar, build_condition_workbench
from bulls.core.config import get_settings
from bulls.core.markets import get_market_profile
from bulls.core.models import (
    Announcement,
    CompanyLogo,
    DailyBar,
    MarketSummary,
    QuoteSnapshot,
    SecFiling,
    Symbol,
    TickerAnalytics,
    TrendingScore,
    UniverseOnboardingResult,
)
from bulls.core.scheduling import analysis_schedule
from bulls.core.schemas.market import (
    BarOut,
    PublicResearchChartOut,
    QuoteOut,
    SymbolDetail,
    SymbolOut,
    VolumeProfileCapabilityOut,
)
from bulls.market_data.calendar import is_trading_day, market_close_on, session_phase, to_market_tz

_MOOD_TTL = 180  # quote-driven intraday read; stay well inside the 15-minute poll cadence
_MOOD_QUOTE_BATCH_WINDOW = dt.timedelta(minutes=30)

router = APIRouter(tags=["market"])

_MIN_ADTV_MN = 5.0
_RESEARCH_CHART_LOOKBACK = 520


def _escape_like(value: str) -> str:
    """Escape user input used inside SQL LIKE patterns."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class MarketStatusOut(BaseModel):
    """Where the session is right now (holiday-aware) + the latest quote timestamp, for the header."""

    phase: str  # open | pre_open | post_close | weekend (weekend covers public holidays too)
    as_of: str | None
    market_time: str
    expected_analysis_date: str
    next_analysis_at: str
    quote_is_stale: bool


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
    supported_locales: list[str]
    price_alert_evaluation: str
    price_decimals: int
    compact_money_units: list[dict[str, float | int | str]]
    market_cap_money_units: list[dict[str, float | int | str]]
    cap_tiers: list[str]  # canonical size-tier vocabulary, largest first (market-specific)
    features: dict[str, bool]
    tenant_name: str
    brand_name: str
    site_url: str
    research_site_url: str
    support_email: str
    logo_url: str
    tagline_en: str
    tagline_bn: str
    research_beta: bool
    social_url: str | None


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
        default_locale=tenant.locale,
        supported_locales=tenant.supported_locales,
        price_alert_evaluation=profile.price_alert_evaluation,
        price_decimals=profile.price_decimals,
        compact_money_units=[asdict(unit) for unit in profile.compact_money_units],
        market_cap_money_units=[asdict(unit) for unit in profile.market_cap_money_units],
        cap_tiers=[name for name, _ in profile.cap_tiers],
        features=asdict(profile.features),
        tenant_name=tenant.name,
        brand_name=tenant.display_name,
        site_url=tenant.site_url,
        research_site_url=tenant.research_site_url,
        support_email=tenant.support_email,
        logo_url=tenant.logo_url,
        tagline_en=tenant.tagline_en,
        tagline_bn=tenant.tagline_bn,
        research_beta=tenant.research_beta,
        social_url=tenant.social_url,
    )


@router.get("/market/status")
async def market_status(tenant: CurrentTenant, session: DbSession) -> MarketStatusOut:
    now = dt.datetime.now(dt.UTC)
    phase = session_phase(now, ZoneInfo(tenant.timezone), market=tenant.market)
    quote_ts = await session.scalar(
        select(func.max(QuoteSnapshot.as_of)).where(QuoteSnapshot.market == tenant.market)
    )
    expected, next_analysis = analysis_schedule(now, tenant.market)
    quote_is_stale = str(phase) == "open" and (
        quote_ts is None
        or to_market_tz(quote_ts, market=tenant.market).date()
        != to_market_tz(now, market=tenant.market).date()
        or (now - quote_ts).total_seconds() > 35 * 60
    )
    return MarketStatusOut(
        phase=str(phase),
        as_of=quote_ts.isoformat() if quote_ts else None,
        market_time=to_market_tz(now, market=tenant.market).isoformat(),
        expected_analysis_date=str(expected),
        next_analysis_at=next_analysis.astimezone(get_market_profile(tenant.market).tz).isoformat(),
        quote_is_stale=quote_is_stale,
    )


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
    enforce_market_feature(tenant, "curated_screens")
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
    status: str = "confirmed"
    source: str | None = None
    url: str | None = None
    day_total: int | None = None


def _bounded_calendar_events(
    events: list[EarningsEventOut],
    *,
    per_day: int,
    priority_by_code: dict[str, float] | None = None,
) -> list[EarningsEventOut]:
    """Return a representative per-day sample while preserving the true daily count."""

    priority_by_code = priority_by_code or {}
    by_day: dict[str, list[EarningsEventOut]] = {}
    for event in events:
        by_day.setdefault(event.meeting_date, []).append(event)

    bounded: list[EarningsEventOut] = []
    for meeting_date in sorted(by_day):
        day_events = sorted(
            by_day[meeting_date],
            key=lambda event: (-priority_by_code.get(event.code, 0.0), event.code),
        )
        bounded.extend(
            event.model_copy(update={"day_total": len(day_events)})
            for event in day_events[:per_day]
        )
    return bounded


async def _estimated_sec_reporting_windows(
    session, market: str, since: dt.date, until: dt.date, *, per_day: int
) -> list[EarningsEventOut]:
    filings = list(
        await session.scalars(
            select(SecFiling)
            .where(
                SecFiling.market == market,
                SecFiling.category.in_(("quarterly_report", "annual_report", "earnings")),
                SecFiling.code.in_(visible_codes(market)),
                SecFiling.filing_date >= since - dt.timedelta(days=500),
            )
            .order_by(SecFiling.code, SecFiling.filing_date)
        )
    )
    by_code: dict[str, list[SecFiling]] = {}
    for filing in filings:
        by_code.setdefault(filing.code, []).append(filing)
    estimates: dict[str, tuple[dt.date, SecFiling]] = {}
    for code, rows in by_code.items():
        dates = sorted({row.filing_date for row in rows})
        intervals = [
            (current - prior).days
            for prior, current in itertools.pairwise(dates)
            if 60 <= (current - prior).days <= 130
        ]
        if not intervals:
            continue
        cadence = round(statistics.median(intervals[-4:]))
        expected = dates[-1] + dt.timedelta(days=cadence)
        while expected < since:
            expected += dt.timedelta(days=cadence)
        while not is_trading_day(expected, market=market):
            expected += dt.timedelta(days=1)
        if expected <= until:
            estimates[code] = (expected, rows[-1])
    if not estimates:
        return []
    symbols = {
        row.code: row
        for row in await session.scalars(
            select(Symbol).where(Symbol.market == market, Symbol.code.in_(estimates))
        )
    }
    market_caps = {
        row.code: float(row.market_cap_mn or 0)
        for row in await session.scalars(
            select(TickerAnalytics).where(
                TickerAnalytics.market == market,
                TickerAnalytics.code.in_(estimates),
            )
        )
    }
    events = [
        EarningsEventOut(
            code=code,
            name_en=symbols[code].name_en if code in symbols else code,
            name_bn=symbols[code].name_bn if code in symbols else None,
            category=symbols[code].category if code in symbols else None,
            meeting_date=str(expected),
            period=last.category,
            status="estimated",
            source="Estimated SEC filing window from the issuer's prior filing cadence",
            url=last.filing_url,
        )
        for code, (expected, last) in estimates.items()
    ]
    return _bounded_calendar_events(
        events,
        per_day=per_day,
        priority_by_code=market_caps,
    )


@router.get("/market/earnings-calendar")
async def earnings_calendar(
    tenant: CurrentTenant,
    session: DbSession,
    days: int = Query(7, ge=1, le=30),
    back: int = Query(0, ge=0, le=7, description="Also include this many past days (week views)"),
    per_day: int = Query(4, ge=1, le=12, description="Representative companies per date"),
) -> list[EarningsEventOut]:
    """Upcoming earnings — board meetings called to consider financials within the next `days`.

    Descriptive heads-up only: the date + period come straight from the decoded DSE board-meeting
    notice (companies can still reschedule). One row per company, nearest date first.
    """
    enforce_market_feature(tenant, "official_disclosures")
    today = to_market_tz(dt.datetime.now(dt.UTC), market=tenant.market).date()
    since = today - dt.timedelta(days=back)
    until = today + dt.timedelta(days=days)
    if get_market_profile(tenant.market).features.sec_filings:
        return await _estimated_sec_reporting_windows(
            session, tenant.market, since, until, per_day=per_day
        )
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
            status="confirmed",
            source="Official exchange board-meeting notice",
        )
        for code, a in by_code.items()
    ]
    return _bounded_calendar_events(events, per_day=per_day)


@router.get("/symbols/{code}/logo")
async def get_symbol_logo(code: str, tenant: CurrentTenant, session: DbSession) -> Response:
    """Cached company logo bytes (fetched from the company website at onboarding). 404 when we have
    none — the frontend then falls back to a monogram."""
    logo = await session.get(CompanyLogo, (tenant.market, code.upper()))
    allowed_types = {"image/png", "image/jpeg", "image/webp", "image/gif", "image/x-icon"}
    if logo is None or logo.image is None or logo.content_type not in allowed_types:
        raise HTTPException(status_code=404, detail="no logo")
    return Response(
        content=logo.image,
        media_type=logo.content_type or "image/png",
        headers={
            "Cache-Control": "public, max-age=86400",
            "X-Content-Type-Options": "nosniff",
        },  # logos change rarely
    )


# Enough history for the longest indicator (200-day SMA) plus headroom.
_ANALYTICS_LOOKBACK = 260


async def load_freshest_quotes(
    session, market: str, codes: list[str], tz: ZoneInfo
) -> dict[str, QuoteOut]:
    """Batch current snapshots with adjusted EOD fallback for markets without intraday data.

    The intraday scrape (QuoteSnapshot) and the EOD bars update on different schedules; after the
    close the bar is the freshest truth, so the header price/date matches the analytics cards
    instead of showing a day-stale snapshot.
    """
    if not codes:
        return {}
    snapshots = {
        q.code: q
        for q in await session.scalars(
            select(QuoteSnapshot).where(
                QuoteSnapshot.market == market,
                QuoteSnapshot.code.in_(codes),
            )
        )
    }
    ranked = (
        select(
            DailyBar.code.label("code"),
            DailyBar.date.label("date"),
            DailyBar.open.label("open"),
            DailyBar.high.label("high"),
            DailyBar.low.label("low"),
            DailyBar.close.label("close"),
            DailyBar.adjusted_close.label("adjusted_close"),
            DailyBar.volume.label("volume"),
            func.row_number()
            .over(partition_by=DailyBar.code, order_by=DailyBar.date.desc())
            .label("row_num"),
        )
        .where(DailyBar.market == market, DailyBar.code.in_(codes))
        .subquery()
    )
    bars_by_code: dict[str, list[Any]] = {}
    for row in (
        await session.execute(
            select(ranked)
            .where(ranked.c.row_num <= 2)
            .order_by(ranked.c.code, ranked.c.date.desc())
        )
    ).mappings():
        bars_by_code.setdefault(row["code"], []).append(row)

    out: dict[str, QuoteOut] = {}
    for code in codes:
        snapshot = snapshots.get(code)
        bars = bars_by_code.get(code, [])
        snapshot_date = snapshot.as_of.astimezone(tz).date() if snapshot else None
        if not bars or (snapshot_date is not None and bars[0]["date"] <= snapshot_date):
            if snapshot is not None:
                out[code] = QuoteOut.model_validate(snapshot)
            continue

        bar = bars[0]
        factor = (
            bar["adjusted_close"] / bar["close"]
            if bar["adjusted_close"] is not None and bar["close"] > 0
            else 1.0
        )
        close = bar["close"] * factor
        prev_close = None
        if len(bars) > 1:
            previous = bars[1]
            prev_factor = (
                previous["adjusted_close"] / previous["close"]
                if previous["adjusted_close"] is not None and previous["close"] > 0
                else 1.0
            )
            prev_close = previous["close"] * prev_factor
        change = close - prev_close if prev_close is not None else 0.0
        change_pct = (change / prev_close * 100) if prev_close else 0.0
        out[code] = QuoteOut(
            market=market,
            code=code,
            ltp=close,
            change=round(change, 2),
            change_pct=round(change_pct, 2),
            open=bar["open"] * factor,
            high=bar["high"] * factor,
            low=bar["low"] * factor,
            close=close,
            prev_close=prev_close,
            volume=bar["volume"],
            trades=0,
            as_of=dt.datetime.combine(bar["date"], market_close_on(bar["date"], market), tzinfo=tz),
            is_delayed=True,
        )
    return out


@router.get("/quotes")
async def get_quotes(
    tenant: CurrentTenant,
    session: DbSession,
    codes: str | None = Query(None, description="Comma-separated codes, e.g. GP,BEXIMCO"),
) -> list[QuoteOut]:
    profile = get_market_profile(tenant.market)
    if not profile.features.intraday_quotes:
        wanted = [c.strip().upper() for c in codes.split(",") if c.strip()] if codes else None
        stmt = select(Symbol.code).where(Symbol.code.in_(visible_codes(tenant.market)))
        if wanted:
            stmt = stmt.where(Symbol.code.in_(wanted))
        else:
            stmt = stmt.order_by(Symbol.code).limit(500)
        public_codes = list(await session.scalars(stmt))
        quotes = await load_freshest_quotes(
            session,
            tenant.market,
            public_codes,
            ZoneInfo(tenant.timezone),
        )
        if wanted:
            return [quotes[code] for code in wanted if code in quotes]
        return sorted(quotes.values(), key=lambda quote: quote.change_pct, reverse=True)[:50]

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
    offset: int = Query(0, ge=0, le=100_000),
    q: str | None = Query(None, min_length=1, max_length=64),
) -> list[SymbolOut]:
    raw_query = q.strip() if q else ""
    statuses = (
        ("ready", "research_only", "reference_only", "onboarding", "degraded")
        if tenant.market == "US" and raw_query
        else ("ready",)
    )
    stmt = (
        select(Symbol)
        .where(
            Symbol.market == tenant.market,
            Symbol.is_active.is_(True),
            Symbol.is_hidden.is_(False),
            Symbol.data_status.in_(statuses),
        )
        .offset(offset)
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
    if symbol is None or not symbol.is_public_research:
        raise HTTPException(status_code=404, detail=f"Unknown symbol {code!r} in {tenant.market}")
    quote = (await load_freshest_quotes(session, key[0], [key[1]], ZoneInfo(tenant.timezone))).get(
        key[1]
    )
    limitations: list[str] = []
    if symbol.data_status == "research_only":
        result = await session.scalar(
            select(UniverseOnboardingResult)
            .where(
                UniverseOnboardingResult.market == key[0],
                UniverseOnboardingResult.code == key[1],
            )
            .order_by(UniverseOnboardingResult.evaluated_at.desc())
            .limit(1)
        )
        if result is not None:
            limitations = list(result.failure_reasons or [])
    return SymbolDetail(
        symbol=SymbolOut.model_validate(symbol),
        quote=quote,
        research_limitations=limitations,
    )


@router.get("/symbols/{code}/bars")
async def get_bars(
    code: str,
    tenant: CurrentTenant,
    session: DbSession,
    limit: int = Query(180, ge=1, le=2000, description="Most recent N daily bars"),
) -> list[BarOut]:
    """OHLCV history, oldest-first, with the current delayed quote appended during the session."""
    code = code.upper()
    symbol = await session.get(Symbol, (tenant.market, code))
    if symbol is None or not symbol.is_public_research:
        raise HTTPException(status_code=404, detail=f"No public price history for {code!r} yet")
    stmt = (
        select(DailyBar)
        .where(
            DailyBar.market == tenant.market,
            DailyBar.code == code,
        )
        .order_by(DailyBar.date.desc())
        .limit(limit)
    )
    rows = list(await session.scalars(stmt))
    if not rows:
        raise HTTPException(status_code=404, detail=f"No public price history for {code!r} yet")
    rows.reverse()  # charts want ascending time
    out = [BarOut.from_daily_bar(r) for r in rows]

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


def _public_research_chart(
    market: str, code: str, bars: Sequence[ResearchBar]
) -> PublicResearchChartOut:
    """Project shared analytics into the bounded, read-only Portal contract."""

    workbench = asdict(build_condition_workbench(bars))
    return PublicResearchChartOut(
        market=market,
        code=code,
        source_frequency="completed_daily",
        price_basis="corporate_action_adjusted",
        **workbench,
        volume_profile=VolumeProfileCapabilityOut(
            status="unavailable",
            method="not_available",
            source_frequency="none",
            reason=(
                "Verified intraday volume-at-price coverage is not available for this symbol. "
                "Daily OHLCV is deliberately not converted into an estimated volume profile."
            ),
        ),
    )


@router.get("/symbols/{code}/research-chart")
async def get_research_chart(
    code: str, tenant: CurrentTenant, session: DbSession
) -> PublicResearchChartOut:
    """Completed-session chart conditions scoped to the active tenant's market.

    This endpoint intentionally excludes private Atlas evidence, strategy admission, paper
    targets, and portfolio state. It uses the same versioned analytics implementation as Atlas.
    """

    code = code.upper()
    symbol = await session.get(Symbol, (tenant.market, code))
    if symbol is None or not symbol.is_public_research:
        raise HTTPException(status_code=404, detail=f"Unknown symbol {code!r} in {tenant.market}")

    rows = list(
        await session.scalars(
            select(DailyBar)
            .where(DailyBar.market == tenant.market, DailyBar.code == code)
            .order_by(DailyBar.date.desc())
            .limit(_RESEARCH_CHART_LOOKBACK)
        )
    )
    if not rows:
        raise HTTPException(status_code=404, detail=f"No price history for {code!r} yet")

    adjusted = adjust_bars(list(reversed(rows)))
    return _public_research_chart(tenant.market, code, adjusted)


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
    if symbol is None or not symbol.is_public_research:
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
    adjusted = adjust_bars(list(reversed(rows)))
    result = compute(adjusted)
    return AnalyticsWithPatterns(**result.model_dump(), patterns=detect_patterns(adjusted))


def _mood_data_status(
    now: dt.datetime,
    market: str,
    quote_as_of: dt.datetime | None,
    close_as_of_date: dt.date | None,
) -> str:
    """Backwards-compatible name retained for focused mood tests and callers."""

    return quote_data_status(now, market, quote_as_of, close_as_of_date)


async def _mood_inputs(session, market: str) -> dict[str, Any]:
    """Gather a coherent mood snapshot, using delayed quotes only where price is sufficient."""
    codes = visible_codes(market)
    now = dt.datetime.now(dt.UTC)

    latest_quote_as_of = await session.scalar(
        select(func.max(QuoteSnapshot.as_of)).where(
            QuoteSnapshot.market == market,
            QuoteSnapshot.code.in_(codes),
        )
    )
    if latest_quote_as_of is not None and latest_quote_as_of.tzinfo is None:
        latest_quote_as_of = latest_quote_as_of.replace(tzinfo=dt.UTC)
    quote_date = (
        to_market_tz(latest_quote_as_of, market=market).date() if latest_quote_as_of else None
    )
    batch_cutoff = latest_quote_as_of - _MOOD_QUOTE_BATCH_WINDOW if latest_quote_as_of else None

    if batch_cutoff is not None:
        adv, dec = (
            await session.execute(
                select(
                    func.count().filter(QuoteSnapshot.change_pct > 0),
                    func.count().filter(QuoteSnapshot.change_pct < 0),
                ).where(
                    QuoteSnapshot.market == market,
                    QuoteSnapshot.code.in_(codes),
                    QuoteSnapshot.as_of >= batch_cutoff,
                )
            )
        ).one()
    else:
        adv, dec = 0, 0

    latest_analytics_date = await session.scalar(
        select(func.max(TickerAnalytics.as_of_date)).where(
            TickerAnalytics.market == market,
            TickerAnalytics.code.in_(codes),
        )
    )
    use_quote_levels = bool(
        batch_cutoff is not None
        and quote_date is not None
        and (latest_analytics_date is None or quote_date > latest_analytics_date)
    )

    if use_quote_levels:
        quote_analytics = (QuoteSnapshot.market == TickerAnalytics.market) & (
            QuoteSnapshot.code == TickerAnalytics.code
        )
        above, total_ma = (
            await session.execute(
                select(
                    func.count().filter(QuoteSnapshot.ltp > TickerAnalytics.sma_200),
                    func.count(),
                )
                .join(TickerAnalytics, quote_analytics)
                .where(
                    QuoteSnapshot.market == market,
                    QuoteSnapshot.code.in_(codes),
                    QuoteSnapshot.as_of >= batch_cutoff,
                    TickerAnalytics.sma_200.isnot(None),
                )
            )
        ).one()
        n_high, n_low = (
            await session.execute(
                select(
                    func.count().filter(QuoteSnapshot.ltp >= TickerAnalytics.week52_high * 0.97),
                    func.count().filter(QuoteSnapshot.ltp <= TickerAnalytics.week52_low * 1.03),
                )
                .join(TickerAnalytics, quote_analytics)
                .where(
                    QuoteSnapshot.market == market,
                    QuoteSnapshot.code.in_(codes),
                    QuoteSnapshot.as_of >= batch_cutoff,
                )
            )
        ).one()
    else:
        # At/after EOD, use the canonical analytics snapshot rather than re-deriving it.
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
        n_high, n_low = (
            await session.execute(
                select(
                    func.count().filter(TickerAnalytics.pct_from_52w_high >= -3),
                    func.count().filter(TickerAnalytics.pct_from_52w_low <= 3),
                ).where(TickerAnalytics.market == market, TickerAnalytics.code.in_(codes))
            )
        ).one()
    pct_above = (above / total_ma) if total_ma else None

    # DSEX history remains close-based. Intraday benchmark history is not available from the
    # delayed quote source, so the API exposes this mixed freshness instead of hiding it.
    summaries = list(
        await session.scalars(
            select(MarketSummary)
            .where(MarketSummary.market == market)
            .order_by(MarketSummary.date.desc())
            .limit(120)
        )
    )
    dsex_closes = [s.dsex for s in reversed(summaries) if s.dsex is not None]
    close_as_of_date = summaries[0].date if summaries else None
    data_status = _mood_data_status(now, market, latest_quote_as_of, close_as_of_date)
    as_of_date = max(
        (d for d in (quote_date, close_as_of_date, latest_analytics_date) if d is not None),
        default=None,
    )

    # Turnover vs its trailing 20-day average (context chip, not scored).
    values = [s.total_value_mn for s in summaries if s.total_value_mn is not None]
    turnover_vs_20d = None
    if len(values) > 1:
        prior = values[1:21]
        avg = sum(prior) / len(prior) if prior else None
        if avg:
            turnover_vs_20d = round(values[0] / avg, 2)

    return {
        "as_of_date": str(as_of_date) if as_of_date else "",
        "as_of": latest_quote_as_of.isoformat() if latest_quote_as_of else None,
        "data_status": data_status,
        "close_as_of_date": str(close_as_of_date) if close_as_of_date else None,
        "refresh_interval_minutes": 15,
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
    """Dhaka Mood Index — a deterministic delayed intraday/close fear-greed composite."""
    enforce_market_feature(tenant, "curated_screens")
    cache_key = f"mood:v3:{tenant.name}:{tenant.market}:{locale}"
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
