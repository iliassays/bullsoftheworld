"""Market read endpoints — surface what ingestion persisted.

Everything is scoped to the active tenant's market, so Bulls of Dhaka only ever sees DSE.
"""

from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select

from api.deps import CurrentTenant, DbSession, visible_codes
from bulls.analytics import AnalyticsResult, compute
from bulls.core.models import DailyBar, QuoteSnapshot, Symbol
from bulls.core.schemas.market import BarOut, QuoteOut, SymbolDetail, SymbolOut
from bulls.market_data.calendar import MARKET_CLOSE

router = APIRouter(tags=["market"])

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
            as_of=dt.datetime.combine(bar.date, MARKET_CLOSE, tzinfo=tz),
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
    limit: int = Query(100, le=500),
) -> list[SymbolOut]:
    stmt = (
        select(Symbol)
        .where(
            Symbol.market == tenant.market,
            Symbol.is_active.is_(True),
            Symbol.is_hidden.is_(False),
        )
        .order_by(Symbol.code)
        .limit(limit)
    )
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
    """Daily OHLCV history, oldest-first (ready for a candlestick chart)."""
    stmt = (
        select(DailyBar)
        .where(DailyBar.market == tenant.market, DailyBar.code == code.upper())
        .order_by(DailyBar.date.desc())
        .limit(limit)
    )
    rows = list(await session.scalars(stmt))
    rows.reverse()  # charts want ascending time
    return [BarOut.model_validate(r) for r in rows]


@router.get("/symbols/{code}/analytics")
async def get_analytics(code: str, tenant: CurrentTenant, session: DbSession) -> AnalyticsResult:
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
    return compute(rows)
