"""Portfolio — manual holdings, valued at read time against the latest (delayed) quotes.

The math lives in compute_portfolio() as a pure function so it unit-tests without a database.
We never connect to a broker account; every row is something the user typed in themselves.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from api.deps import CurrentTenant, CurrentUser, DbSession
from bulls.core.models import PortfolioHolding, QuoteSnapshot, Symbol

router = APIRouter(prefix="/portfolio", tags=["portfolio"])

MAX_HOLDINGS_PER_USER = 100


class HoldingIn(BaseModel):
    code: str
    quantity: int = Field(gt=0)
    avg_cost: float = Field(gt=0)


class HoldingOut(BaseModel):
    code: str
    name: str | None
    quantity: int
    avg_cost: float
    ltp: float | None
    as_of: dt.datetime | None
    value: float | None
    day_change_pct: float | None
    pnl: float | None
    pnl_pct: float | None


class PortfolioOut(BaseModel):
    holdings: list[HoldingOut]
    total_value: float | None
    total_cost: float
    day_pnl: float | None
    day_pnl_pct: float | None
    total_pnl: float | None
    total_pnl_pct: float | None


@dataclass
class QuoteView:
    """The slice of a quote the valuation needs — makes compute_portfolio() DB-free."""

    ltp: float
    change: float  # absolute ৳ move today
    change_pct: float
    as_of: dt.datetime | None


def compute_portfolio(
    holdings: list[PortfolioHolding],
    quotes: dict[str, QuoteView],
    names: dict[str, str | None] | None = None,
) -> PortfolioOut:
    out: list[HoldingOut] = []
    total_value = 0.0
    total_cost = 0.0
    day_pnl = 0.0
    priced_cost = 0.0  # cost basis of the rows we could actually value
    any_priced = False
    for h in holdings:
        cost = h.quantity * h.avg_cost
        total_cost += cost
        q = quotes.get(h.code)
        if q is None:
            out.append(
                HoldingOut(
                    code=h.code,
                    name=(names or {}).get(h.code),
                    quantity=h.quantity,
                    avg_cost=h.avg_cost,
                    ltp=None,
                    as_of=None,
                    value=None,
                    day_change_pct=None,
                    pnl=None,
                    pnl_pct=None,
                )
            )
            continue
        any_priced = True
        value = h.quantity * q.ltp
        pnl = value - cost
        total_value += value
        day_pnl += h.quantity * q.change
        priced_cost += cost
        out.append(
            HoldingOut(
                code=h.code,
                name=(names or {}).get(h.code),
                quantity=h.quantity,
                avg_cost=h.avg_cost,
                ltp=q.ltp,
                as_of=q.as_of,
                value=round(value, 2),
                day_change_pct=q.change_pct,
                pnl=round(pnl, 2),
                pnl_pct=round(pnl / cost * 100, 2) if cost else None,
            )
        )
    prev_value = total_value - day_pnl
    return PortfolioOut(
        holdings=out,
        total_value=round(total_value, 2) if any_priced else None,
        total_cost=round(total_cost, 2),
        day_pnl=round(day_pnl, 2) if any_priced else None,
        day_pnl_pct=round(day_pnl / prev_value * 100, 2) if any_priced and prev_value else None,
        total_pnl=round(total_value - priced_cost, 2) if any_priced else None,
        total_pnl_pct=(
            round((total_value - priced_cost) / priced_cost * 100, 2)
            if any_priced and priced_cost
            else None
        ),
    )


@router.get("")
async def get_portfolio(
    user: CurrentUser, tenant: CurrentTenant, session: DbSession
) -> PortfolioOut:
    holdings = (
        await session.scalars(
            select(PortfolioHolding)
            .where(PortfolioHolding.user_id == user.id, PortfolioHolding.market == tenant.market)
            .order_by(PortfolioHolding.created_at)
        )
    ).all()
    codes = [h.code for h in holdings]
    quotes: dict[str, QuoteView] = {}
    names: dict[str, str | None] = {}
    if codes:
        for q in await session.scalars(
            select(QuoteSnapshot).where(
                QuoteSnapshot.market == tenant.market, QuoteSnapshot.code.in_(codes)
            )
        ):
            quotes[q.code] = QuoteView(
                ltp=q.ltp, change=q.change, change_pct=q.change_pct, as_of=q.as_of
            )
        for code, name in await session.execute(
            select(Symbol.code, Symbol.name_en).where(
                Symbol.market == tenant.market, Symbol.code.in_(codes)
            )
        ):
            names[code] = name
    return compute_portfolio(list(holdings), quotes, names)


@router.post("/holdings", status_code=201)
async def upsert_holding(
    body: HoldingIn, user: CurrentUser, tenant: CurrentTenant, session: DbSession
) -> dict[str, str]:
    code = body.code.upper()
    if await session.get(Symbol, (tenant.market, code)) is None:
        raise HTTPException(status_code=404, detail=f"Unknown symbol {code!r}")
    existing = await session.get(PortfolioHolding, (user.id, tenant.market, code))
    if existing is not None:
        existing.quantity = body.quantity
        existing.avg_cost = body.avg_cost
        return {"status": "updated", "code": code}
    count = len(
        (
            await session.scalars(
                select(PortfolioHolding.code).where(PortfolioHolding.user_id == user.id)
            )
        ).all()
    )
    if count >= MAX_HOLDINGS_PER_USER:
        raise HTTPException(status_code=429, detail="Too many holdings")
    session.add(
        PortfolioHolding(
            user_id=user.id,
            market=tenant.market,
            code=code,
            quantity=body.quantity,
            avg_cost=body.avg_cost,
        )
    )
    return {"status": "created", "code": code}


@router.delete("/holdings/{code}", status_code=204)
async def delete_holding(
    code: str, user: CurrentUser, tenant: CurrentTenant, session: DbSession
) -> None:
    h = await session.get(PortfolioHolding, (user.id, tenant.market, code.upper()))
    if h is not None:
        await session.delete(h)
