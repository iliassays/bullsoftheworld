"""Admin cockpit for the agent model portfolios (admin-token gated, read-only).

The agent accounts trade simulated ৳1-lac portfolios on the 15-min quote cycle
(services/ingestion/agent_trader.py). This router is how the admin reviews them: equity and P&L
per agent, current holdings priced live, and the full trade log with each decision's
plain-language reason. Nothing here mutates state — the engine is the only writer.

Freshness is explicit everywhere (quote `as_of` on valuations, `quote_as_of` on trades): these
are simulated fills against delayed quotes and the cockpit must read that way.
"""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import desc, select

from api.deps import CurrentTenant, DbSession, require_admin
from bulls.analytics import STRATEGIES
from bulls.core.models import (
    AgentLot,
    AgentOpportunity,
    AgentPortfolio,
    AgentTrade,
    PortfolioHolding,
    QuoteSnapshot,
    User,
)
from bulls.market_data.calendar import to_market_tz

router = APIRouter(prefix="/admin/agents", tags=["admin"], dependencies=[Depends(require_admin)])


class HoldingOut(BaseModel):
    code: str
    quantity: int
    sellable_quantity: int  # matured (T+2/T+3 settled) shares — the rest can't be sold yet
    avg_cost: float
    ltp: float | None
    value: float | None
    pnl_pct: float | None
    as_of: dt.datetime | None


class TradeOut(BaseModel):
    id: int
    code: str
    side: str
    quantity: int
    price: float
    fee: float
    net_cash: float
    trade_date: dt.date
    settles_on: dt.date
    settled: bool
    reason: str
    quote_as_of: dt.datetime


class AgentSummary(BaseModel):
    handle: str
    display_name: str
    strategy: str
    description: str
    is_active: bool
    initial_capital: float
    cash_settled: float
    cash_pending: float  # sell proceeds still inside the settlement window
    holdings_value: float | None  # None if any position couldn't be priced (never guess)
    equity: float | None  # cash (settled+pending) + holdings value
    pnl: float | None
    pnl_pct: float | None
    positions: int
    trades_total: int
    last_trade_at: dt.datetime | None
    quotes_as_of: dt.datetime | None  # oldest quote used in the valuation — the honesty stamp


class AgentDetail(AgentSummary):
    holdings: list[HoldingOut]
    trades: list[TradeOut]  # newest first


class OpportunityOut(BaseModel):
    id: int
    code: str
    strategy: str
    status: str
    signal_reason: str
    first_block_reason: str
    last_block_reason: str
    first_seen_at: dt.datetime
    last_seen_at: dt.datetime
    first_quote_as_of: dt.datetime
    last_quote_as_of: dt.datetime
    first_price: float
    last_price: float
    return_pct: float
    best_return_pct: float
    worst_return_pct: float
    first_rank: int
    best_rank: int
    last_rank: int
    target_budget: float
    required_cash: float
    first_available_cash: float
    last_available_cash: float
    first_pending_cash: float
    last_pending_cash: float
    first_free_slots: int
    last_free_slots: int
    blocked_ticks: int
    no_cash_ticks: int
    no_slot_ticks: int
    order_too_small_ticks: int
    resolved_at: dt.datetime | None
    resolved_price: float | None


async def _summarize(
    session, agent: AgentPortfolio, user: User
) -> tuple[AgentSummary, list[HoldingOut]]:
    spec = STRATEGIES[agent.strategy]
    holdings = (
        await session.scalars(
            select(PortfolioHolding).where(
                PortfolioHolding.user_id == agent.user_id,
                PortfolioHolding.tenant_id == user.tenant_id,
                PortfolioHolding.market == agent.market,
            )
        )
    ).all()
    quotes = {
        q.code: q
        for q in await session.scalars(
            select(QuoteSnapshot).where(
                QuoteSnapshot.market == agent.market,
                QuoteSnapshot.code.in_([h.code for h in holdings] or [""]),
            )
        )
    }
    today = to_market_tz(dt.datetime.now(dt.UTC), market=agent.market).date()
    matured: dict[str, int] = {}
    for lot in await session.scalars(
        select(AgentLot).where(
            AgentLot.user_id == agent.user_id,
            AgentLot.market == agent.market,
            AgentLot.quantity_left > 0,
        )
    ):
        if lot.sellable_from <= today:
            matured[lot.code] = matured.get(lot.code, 0) + lot.quantity_left

    hout: list[HoldingOut] = []
    total_value: float | None = 0.0
    oldest_as_of: dt.datetime | None = None
    for h in holdings:
        q = quotes.get(h.code)
        value = h.quantity * q.ltp if q else None
        if value is None:
            total_value = None  # one unpriceable position poisons the total — omit over mislead
        elif total_value is not None:
            total_value += value
        if q and (oldest_as_of is None or q.as_of < oldest_as_of):
            oldest_as_of = q.as_of
        hout.append(
            HoldingOut(
                code=h.code,
                quantity=h.quantity,
                sellable_quantity=min(matured.get(h.code, 0), h.quantity),
                avg_cost=h.avg_cost,
                ltp=q.ltp if q else None,
                value=round(value, 2) if value is not None else None,
                pnl_pct=(
                    round((q.ltp - h.avg_cost) / h.avg_cost * 100, 2)
                    if q and h.avg_cost > 0
                    else None
                ),
                as_of=q.as_of if q else None,
            )
        )

    pending = 0.0
    for t in await session.scalars(
        select(AgentTrade).where(
            AgentTrade.user_id == agent.user_id,
            AgentTrade.market == agent.market,
            AgentTrade.side == "sell",
            AgentTrade.settled.is_(False),
        )
    ):
        pending += t.net_cash
    trades_total = len(
        (
            await session.scalars(
                select(AgentTrade.id).where(
                    AgentTrade.user_id == agent.user_id,
                    AgentTrade.market == agent.market,
                )
            )
        ).all()
    )
    last_trade_at = await session.scalar(
        select(AgentTrade.created_at)
        .where(
            AgentTrade.user_id == agent.user_id,
            AgentTrade.market == agent.market,
        )
        .order_by(desc(AgentTrade.id))
        .limit(1)
    )

    equity = None if total_value is None else agent.cash_settled + pending + total_value
    return (
        AgentSummary(
            handle=user.handle,
            display_name=spec.display_name,
            strategy=agent.strategy,
            description=spec.description,
            is_active=agent.is_active,
            initial_capital=agent.initial_capital,
            cash_settled=round(agent.cash_settled, 2),
            cash_pending=round(pending, 2),
            holdings_value=round(total_value, 2) if total_value is not None else None,
            equity=round(equity, 2) if equity is not None else None,
            pnl=round(equity - agent.initial_capital, 2) if equity is not None else None,
            pnl_pct=(
                round((equity - agent.initial_capital) / agent.initial_capital * 100, 2)
                if equity is not None and agent.initial_capital > 0
                else None
            ),
            positions=len(holdings),
            trades_total=trades_total,
            last_trade_at=last_trade_at,
            quotes_as_of=oldest_as_of,
        ),
        hout,
    )


@router.get("")
async def list_agents(tenant: CurrentTenant, session: DbSession) -> list[AgentSummary]:
    """All agent portfolios with live-priced equity — the cockpit's overview table."""
    rows = (
        await session.execute(
            select(AgentPortfolio, User)
            .join(User, User.id == AgentPortfolio.user_id)
            .where(
                AgentPortfolio.market == tenant.market,
                User.tenant_id == tenant.name,
            )
        )
    ).all()
    out = []
    for agent, user in rows:
        summary, _ = await _summarize(session, agent, user)
        out.append(summary)
    out.sort(key=lambda a: a.handle)
    return out


@router.get("/{handle}")
async def agent_detail(
    handle: str, tenant: CurrentTenant, session: DbSession
) -> AgentDetail:
    """One agent's full book: holdings (with sellable vs settling split) + every trade with its
    reason, newest first."""
    row = (
        await session.execute(
            select(AgentPortfolio, User)
            .join(User, User.id == AgentPortfolio.user_id)
            .where(
                User.handle == handle,
                User.tenant_id == tenant.name,
                AgentPortfolio.market == tenant.market,
            )
        )
    ).one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail=f"No agent portfolio for @{handle}")
    agent, user = row
    summary, holdings = await _summarize(session, agent, user)
    trades = (
        await session.scalars(
            select(AgentTrade)
            .where(
                AgentTrade.user_id == agent.user_id,
                AgentTrade.market == agent.market,
            )
            .order_by(desc(AgentTrade.id))
            .limit(500)
        )
    ).all()
    return AgentDetail(
        **summary.model_dump(),
        holdings=holdings,
        trades=[
            TradeOut(
                id=t.id,
                code=t.code,
                side=t.side,
                quantity=t.quantity,
                price=t.price,
                fee=t.fee,
                net_cash=t.net_cash,
                trade_date=t.trade_date,
                settles_on=t.settles_on,
                settled=t.settled,
                reason=t.reason,
                quote_as_of=t.quote_as_of,
            )
            for t in trades
        ],
    )


@router.get("/{handle}/opportunities")
async def agent_opportunities(
    handle: str,
    tenant: CurrentTenant,
    session: DbSession,
    limit: int = 200,
) -> list[OpportunityOut]:
    """Capital-constrained setup episodes for counterfactual strategy evaluation."""
    limit = min(max(limit, 1), 1_000)
    user_id = await session.scalar(
        select(User.id)
        .join(AgentPortfolio, AgentPortfolio.user_id == User.id)
        .where(
            User.handle == handle,
            User.tenant_id == tenant.name,
            AgentPortfolio.market == tenant.market,
        )
    )
    if user_id is None:
        raise HTTPException(status_code=404, detail=f"No user @{handle}")
    rows = (
        await session.scalars(
            select(AgentOpportunity)
            .where(
                AgentOpportunity.tenant_id == tenant.name,
                AgentOpportunity.user_id == user_id,
                AgentOpportunity.market == tenant.market,
            )
            .order_by(desc(AgentOpportunity.id))
            .limit(limit)
        )
    ).all()
    return [
        OpportunityOut(
            id=row.id,
            code=row.code,
            strategy=row.strategy,
            status=row.status,
            signal_reason=row.signal_reason,
            first_block_reason=row.first_block_reason,
            last_block_reason=row.last_block_reason,
            first_seen_at=row.first_seen_at,
            last_seen_at=row.last_seen_at,
            first_quote_as_of=row.first_quote_as_of,
            last_quote_as_of=row.last_quote_as_of,
            first_price=row.first_price,
            last_price=row.last_price,
            return_pct=round((row.last_price / row.first_price - 1) * 100, 2),
            best_return_pct=round((row.best_price / row.first_price - 1) * 100, 2),
            worst_return_pct=round((row.worst_price / row.first_price - 1) * 100, 2),
            first_rank=row.first_rank,
            best_rank=row.best_rank,
            last_rank=row.last_rank,
            target_budget=row.target_budget,
            required_cash=row.required_cash,
            first_available_cash=row.first_available_cash,
            last_available_cash=row.last_available_cash,
            first_pending_cash=row.first_pending_cash,
            last_pending_cash=row.last_pending_cash,
            first_free_slots=row.first_free_slots,
            last_free_slots=row.last_free_slots,
            blocked_ticks=row.blocked_ticks,
            no_cash_ticks=row.no_cash_ticks,
            no_slot_ticks=row.no_slot_ticks,
            order_too_small_ticks=row.order_too_small_ticks,
            resolved_at=row.resolved_at,
            resolved_price=row.resolved_price,
        )
        for row in rows
    ]
