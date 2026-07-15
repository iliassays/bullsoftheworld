"""Watchlist: track symbols, see them with their latest quote."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from api.deps import CurrentTenant, CurrentUser, DbSession
from api.routers.market import load_freshest_quotes
from bulls.core.models import Symbol, WatchlistItem
from bulls.core.schemas.market import SymbolDetail, SymbolOut
from bulls.core.schemas.social import WatchlistAdd
from bulls.market_data.calendar import market_timezone

router = APIRouter(prefix="/watchlist", tags=["watchlist"])


@router.post("", status_code=201)
async def add(
    body: WatchlistAdd, user: CurrentUser, tenant: CurrentTenant, session: DbSession
) -> dict[str, str]:
    code = body.code.upper()
    symbol = await session.get(Symbol, (tenant.market, code))
    if symbol is None or not symbol.is_public_research:
        raise HTTPException(status_code=404, detail=f"Unknown symbol {code!r}")
    if await session.get(WatchlistItem, (user.id, tenant.market, code)) is None:
        session.add(
            WatchlistItem(
                user_id=user.id,
                tenant_id=tenant.name,
                market=tenant.market,
                code=code,
            )
        )
    return {"status": "ok", "code": code}


@router.delete("/{code}", status_code=204)
async def remove(code: str, user: CurrentUser, tenant: CurrentTenant, session: DbSession) -> None:
    item = await session.get(WatchlistItem, (user.id, tenant.market, code.upper()))
    if item is not None:
        await session.delete(item)


@router.get("")
async def list_watchlist(
    user: CurrentUser, tenant: CurrentTenant, session: DbSession
) -> list[SymbolDetail]:
    codes = list(
        await session.scalars(
            select(WatchlistItem.code)
            .where(WatchlistItem.user_id == user.id, WatchlistItem.market == tenant.market)
            .order_by(WatchlistItem.created_at)
        )
    )
    if not codes:
        return []

    symbols = {
        s.code: s
        for s in await session.scalars(
            select(Symbol).where(
                Symbol.market == tenant.market,
                Symbol.code.in_(codes),
                Symbol.data_status.in_(("ready", "research_only")),
                Symbol.is_active.is_(True),
                Symbol.is_hidden.is_(False),
            )
        )
    }
    quotes = await load_freshest_quotes(
        session, tenant.market, codes, market_timezone(tenant.market)
    )
    out = []
    for code in codes:
        if code in symbols:
            q = quotes.get(code)
            out.append(
                SymbolDetail(
                    symbol=SymbolOut.model_validate(symbols[code]),
                    quote=q,
                )
            )
    return out
