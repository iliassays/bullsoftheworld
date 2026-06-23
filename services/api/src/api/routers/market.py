"""Market read endpoints — surface what ingestion persisted.

Everything is scoped to the active tenant's market, so Bulls of Dhaka only ever sees DSE.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select

from api.deps import CurrentTenant, DbSession
from bulls.core.models import DailyBar, QuoteSnapshot, Symbol
from bulls.core.schemas.market import BarOut, QuoteOut, SymbolDetail, SymbolOut

router = APIRouter(tags=["market"])


@router.get("/quotes")
async def get_quotes(
    tenant: CurrentTenant,
    session: DbSession,
    codes: str | None = Query(None, description="Comma-separated codes, e.g. GP,BEXIMCO"),
) -> list[QuoteOut]:
    stmt = select(QuoteSnapshot).where(QuoteSnapshot.market == tenant.market)
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
        .where(Symbol.market == tenant.market, Symbol.is_active.is_(True))
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
    quote = await session.get(QuoteSnapshot, key)
    return SymbolDetail(
        symbol=SymbolOut.model_validate(symbol),
        quote=QuoteOut.model_validate(quote) if quote else None,
    )


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
