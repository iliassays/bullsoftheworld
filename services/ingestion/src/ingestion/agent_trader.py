"""The agent-portfolio trading engine — one tick per 15-min quote poll during the session.

Runs the configured model portfolios (bulls.analytics.strategies) as simulated broker accounts:

    settle -> exits -> entries, per agent, all in one transaction per tick.

- **Settle**: sale proceeds whose exchange settlement date (T+2 for A/B/G/N, T+3 for Z, in
  trading days) has arrived become spendable cash. Bought lots become sellable the same way.
- **Exits**: every holding is checked against the strategy's stop / target / thesis-exit using
  the LIVE quote. Only settled (matured) lot quantity can be sold — FIFO.
- **Entries**: ranked qualifying setups fill free position slots while settled cash lasts.

Honesty rules, enforced here rather than hoped for:
- A tick with no fresh quote does nothing (stale quotes are skipped per-code; if the whole feed
  is stale the tick is a no-op) — the simulation never trades on prices we don't actually have.
- Fills happen at the last traded price with brokerage charged both ways; a stock pinned at its
  circuit lock is untradable in the relevant direction (see strategies.entry_reason/exit_reason).
- Every trade records the quote's `as_of` and a human-readable reason for the admin cockpit.

Holdings are mirrored into the shared `portfolio_holdings` table so the regular portfolio page
and the EOD snapshot job cover agent accounts with zero changes.

    uv run python -m ingestion.agent_trader   # manual tick (respects session gating)
"""

from __future__ import annotations

import datetime as dt
import logging
import math

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bulls.analytics import STRATEGIES, Snapshot, exit_reason, rank_entries
from bulls.core.db import bind_tenant_context, get_sessionmaker
from bulls.core.models import (
    AgentLot,
    AgentOpportunity,
    AgentPortfolio,
    AgentTrade,
    CompanyProfile,
    PortfolioHolding,
    QuoteSnapshot,
    Symbol,
    TickerAnalytics,
    User,
)
from bulls.market_data.calendar import add_trading_days, is_trading_hours, to_market_tz

log = logging.getLogger(__name__)

FEE_RATE = 0.004  # brokerage per side (~0.4%, typical DSE retail commission incl. charges)
MIN_ORDER_VALUE = 5_000.0  # ৳ — below this, brokerage friction eats the position
QUOTE_MAX_AGE = dt.timedelta(minutes=45)  # a 15-min feed older than 3 ticks is stale
# After exiting a code, don't re-enter it for a week: analytics are EOD, so right after a
# stop-loss the same stale row often still "qualifies" — without this the engine would rebuy
# what it just sold in the very same tick.
REENTRY_COOLDOWN = dt.timedelta(days=7)
_BLOCK_REASONS = {"no_cash", "no_slot", "order_too_small"}


def _calendar_market(market: str) -> str:
    """Synthetic test markets intentionally follow DSE hours; production markets use themselves."""
    return market if market in {"DSE", "US"} else "DSE"


def settle_days(category: str | None) -> int:
    """DSE settlement cycle in trading days: Z-category contracts clear T+3, everything else T+2."""
    return 3 if category == "Z" else 2


def _minimum_executable_cash(price: float) -> float:
    """Smallest cash amount that can buy an integer number of shares with gross value >= floor."""
    quantity = max(1, math.ceil(MIN_ORDER_VALUE / price))
    return round(quantity * price * (1 + FEE_RATE), 2)


def _update_opportunity_price(
    opportunity: AgentOpportunity, snap: Snapshot, observed_at: dt.datetime
) -> None:
    opportunity.last_seen_at = observed_at
    opportunity.last_price = snap.ltp
    opportunity.best_price = max(opportunity.best_price, snap.ltp)
    opportunity.worst_price = min(opportunity.worst_price, snap.ltp)
    if snap.quote_as_of >= opportunity.last_quote_as_of:
        opportunity.last_quote_as_of = snap.quote_as_of


def _observe_blocked_opportunity(
    opportunity: AgentOpportunity | None,
    *,
    tenant_id: str,
    agent: AgentPortfolio,
    snap: Snapshot,
    observed_at: dt.datetime,
    signal_reason: str,
    block_reason: str,
    rank: int,
    target_budget: float,
    available_cash: float,
    pending_cash: float,
    free_slots: int,
) -> AgentOpportunity:
    """Create or update one continuous blocked-setup episode."""
    if block_reason not in _BLOCK_REASONS:
        raise ValueError(f"Unknown opportunity block reason: {block_reason!r}")
    required_cash = _minimum_executable_cash(snap.ltp)
    if opportunity is None:
        opportunity = AgentOpportunity(
            tenant_id=tenant_id,
            user_id=agent.user_id,
            market=agent.market,
            strategy=agent.strategy,
            code=snap.code,
            status="open",
            signal_reason=signal_reason,
            first_block_reason=block_reason,
            last_block_reason=block_reason,
            first_seen_at=observed_at,
            last_seen_at=observed_at,
            first_quote_as_of=snap.quote_as_of,
            last_quote_as_of=snap.quote_as_of,
            first_price=snap.ltp,
            last_price=snap.ltp,
            best_price=snap.ltp,
            worst_price=snap.ltp,
            first_rank=rank,
            best_rank=rank,
            last_rank=rank,
            target_budget=target_budget,
            required_cash=required_cash,
            first_available_cash=available_cash,
            last_available_cash=available_cash,
            first_pending_cash=pending_cash,
            last_pending_cash=pending_cash,
            first_free_slots=free_slots,
            last_free_slots=free_slots,
            blocked_ticks=0,
            no_cash_ticks=0,
            no_slot_ticks=0,
            order_too_small_ticks=0,
        )
    else:
        _update_opportunity_price(opportunity, snap, observed_at)
        opportunity.signal_reason = signal_reason
        opportunity.last_block_reason = block_reason
        opportunity.best_rank = min(opportunity.best_rank, rank)
        opportunity.last_rank = rank
        opportunity.target_budget = target_budget
        opportunity.required_cash = required_cash
        opportunity.last_available_cash = available_cash
        opportunity.last_pending_cash = pending_cash
        opportunity.last_free_slots = free_slots

    opportunity.blocked_ticks += 1
    if block_reason == "no_cash":
        opportunity.no_cash_ticks += 1
    elif block_reason == "no_slot":
        opportunity.no_slot_ticks += 1
    else:
        opportunity.order_too_small_ticks += 1
    return opportunity


def _resolve_opportunity(
    opportunity: AgentOpportunity,
    *,
    status: str,
    observed_at: dt.datetime,
    snap: Snapshot,
) -> None:
    if status not in {"entered", "expired"}:
        raise ValueError(f"Unknown opportunity resolution: {status!r}")
    _update_opportunity_price(opportunity, snap, observed_at)
    opportunity.status = status
    opportunity.resolved_at = observed_at
    opportunity.resolved_price = snap.ltp


async def _load_snapshots(
    session: AsyncSession, market: str, now: dt.datetime
) -> dict[str, Snapshot]:
    """One Snapshot per visible symbol with a FRESH quote + an analytics row. A code missing
    either simply isn't tradable this tick — omit, never guess."""
    quotes = {
        q.code: q
        for q in await session.scalars(select(QuoteSnapshot).where(QuoteSnapshot.market == market))
    }
    symbols = {
        s.code: s
        for s in await session.scalars(
            select(Symbol).where(
                Symbol.market == market, Symbol.is_active.is_(True), Symbol.is_hidden.is_(False)
            )
        )
    }
    paidup = {
        code: mn
        for code, mn in await session.execute(
            select(CompanyProfile.code, CompanyProfile.paid_up_capital_mn).where(
                CompanyProfile.market == market
            )
        )
    }
    out: dict[str, Snapshot] = {}
    for code, a in [
        (a.code, a)
        for a in await session.scalars(
            select(TickerAnalytics).where(TickerAnalytics.market == market)
        )
    ]:
        q = quotes.get(code)
        sym = symbols.get(code)
        if q is None or sym is None or q.ltp is None or q.ltp <= 0:
            continue
        as_of = q.as_of if q.as_of.tzinfo else q.as_of.replace(tzinfo=dt.UTC)
        if now - as_of > QUOTE_MAX_AGE:
            continue  # stale quote: this code doesn't exist for this tick
        out[code] = Snapshot(
            code=code,
            sector=sym.sector,
            category=sym.category,
            ltp=q.ltp,
            change_pct=q.change_pct,
            quote_as_of=as_of,
            last_close=a.last_close,
            rsi_14=a.rsi_14,
            pct_from_52w_high=a.pct_from_52w_high,
            pct_from_52w_low=a.pct_from_52w_low,
            pe_ratio=a.pe_ratio,
            pb_ratio=a.pb_ratio,
            pe_vs_sector=a.pe_vs_sector,
            roe=a.roe,
            eps_growth_yoy=a.eps_growth_yoy,
            dividend_yield=a.dividend_yield,
            volatility=a.volatility,
            cmf_20=a.cmf_20,
            obv_slope=a.obv_slope,
            institute_delta=a.institute_delta,
            foreign_delta=a.foreign_delta,
            rel_volume_5d=a.rel_volume_5d,
            relative_volume=a.relative_volume,
            avg_volume_20=a.avg_volume_20,
            market_cap_mn=a.market_cap_mn,
            above_sma_200=a.above_sma_200,
            paid_up_capital_mn=paidup.get(code),
        )
    return out


async def _settle_due(session: AsyncSession, agent: AgentPortfolio, today: dt.date) -> int:
    """Credit matured sell proceeds into spendable cash."""
    due = (
        await session.scalars(
            select(AgentTrade).where(
                AgentTrade.user_id == agent.user_id,
                AgentTrade.market == agent.market,
                AgentTrade.side == "sell",
                AgentTrade.settled.is_(False),
                AgentTrade.settles_on <= today,
            )
        )
    ).all()
    for t in due:
        agent.cash_settled += t.net_cash
        t.settled = True
    return len(due)


async def _sell(
    session: AsyncSession,
    agent: AgentPortfolio,
    holding: PortfolioHolding,
    lots: list[AgentLot],
    snap: Snapshot,
    today: dt.date,
    reason: str,
    category: str | None,
) -> bool:
    """Sell every matured share of this holding at the live price. Proceeds settle T+2/T+3."""
    matured = [lot for lot in lots if lot.sellable_from <= today and lot.quantity_left > 0]
    qty = sum(lot.quantity_left for lot in matured)
    if qty <= 0:
        return False  # everything still inside the settlement window — retry a later tick
    gross = qty * snap.ltp
    fee = round(gross * FEE_RATE, 2)
    session.add(
        AgentTrade(
            user_id=agent.user_id,
            market=agent.market,
            code=snap.code,
            side="sell",
            quantity=qty,
            price=snap.ltp,
            fee=fee,
            net_cash=round(gross - fee, 2),
            trade_date=today,
            settles_on=add_trading_days(
                today, settle_days(category), market=_calendar_market(agent.market)
            ),
            settled=False,  # proceeds credited by _settle_due when the date arrives
            reason=reason,
            quote_as_of=snap.quote_as_of,
        )
    )
    for lot in matured:  # FIFO by construction: lots come back ordered by id
        lot.quantity_left = 0
    holding.quantity -= qty
    if holding.quantity <= 0:
        await session.delete(holding)
    return True


async def _buy(
    session: AsyncSession,
    agent: AgentPortfolio,
    tenant_id: str,
    holdings: dict[str, PortfolioHolding],
    snap: Snapshot,
    today: dt.date,
    budget: float,
    reason: str,
    category: str | None,
) -> float:
    """Buy as many shares as `budget` covers (price + brokerage). Returns cash actually spent
    (0.0 = order too small to bother). Cash leaves the account immediately; the shares sit in a
    lot that matures at settlement."""
    qty = math.floor(budget / (snap.ltp * (1 + FEE_RATE)))
    if qty <= 0 or qty * snap.ltp < MIN_ORDER_VALUE:
        return 0.0
    gross = qty * snap.ltp
    fee = round(gross * FEE_RATE, 2)
    cost = round(gross + fee, 2)
    settles = add_trading_days(today, settle_days(category), market=_calendar_market(agent.market))
    session.add(
        AgentTrade(
            user_id=agent.user_id,
            market=agent.market,
            code=snap.code,
            side="buy",
            quantity=qty,
            price=snap.ltp,
            fee=fee,
            net_cash=-cost,
            trade_date=today,
            settles_on=settles,
            settled=True,  # the cash impact of a buy is immediate
            reason=reason,
            quote_as_of=snap.quote_as_of,
        )
    )
    session.add(
        AgentLot(
            user_id=agent.user_id,
            market=agent.market,
            code=snap.code,
            quantity=qty,
            quantity_left=qty,
            buy_price=snap.ltp,
            trade_date=today,
            sellable_from=settles,
        )
    )
    held = holdings.get(snap.code)
    if held is None:
        session.add(
            PortfolioHolding(
                user_id=agent.user_id,
                tenant_id=tenant_id,
                market=agent.market,
                code=snap.code,
                quantity=qty,
                avg_cost=snap.ltp,
            )
        )
    else:  # average in (cost basis includes only price, matching the manual-portfolio convention)
        total = held.quantity + qty
        held.avg_cost = round((held.avg_cost * held.quantity + snap.ltp * qty) / total, 4)
        held.quantity = total
    agent.cash_settled = round(agent.cash_settled - cost, 2)
    return cost


async def run_agents(
    market: str = "DSE",
    *,
    tenant_id: str = "bullsofdhaka",
    now: dt.datetime | None = None,
) -> dict[str, int]:
    """One engine tick. Safe to call any time: outside trading hours it's a no-op, and inside
    the session it only acts on quotes fresh enough to trust."""
    now = now or dt.datetime.now(dt.UTC)
    calendar_market = _calendar_market(market)
    if not is_trading_hours(now, market=calendar_market):
        return {"skipped": 1}
    today = to_market_tz(now, market=calendar_market).date()

    counts = {
        "agents": 0,
        "buys": 0,
        "sells": 0,
        "settled": 0,
        "opportunities": 0,
        "opportunities_resolved": 0,
    }
    sm = get_sessionmaker()
    async with sm() as session:
        await bind_tenant_context(session, tenant_id)
        agents = (
            await session.scalars(
                select(AgentPortfolio)
                .join(User, User.id == AgentPortfolio.user_id)
                .where(
                    AgentPortfolio.market == market,
                    AgentPortfolio.is_active.is_(True),
                    User.tenant_id == tenant_id,
                )
                .with_for_update(of=AgentPortfolio)
            )
        ).all()
        if not agents:
            return counts

        snapshots = await _load_snapshots(session, market, now)
        if not snapshots:
            log.warning("agent tick: no fresh quotes for %s — feed stale, doing nothing", market)
            return counts
        categories = {code: s.category for code, s in snapshots.items()}

        for agent in agents:
            counts["agents"] += 1
            counts["settled"] += await _settle_due(session, agent, today)
            spec = STRATEGIES[agent.strategy]

            holdings = {
                h.code: h
                for h in await session.scalars(
                    select(PortfolioHolding).where(
                        PortfolioHolding.user_id == agent.user_id,
                        PortfolioHolding.tenant_id == tenant_id,
                        PortfolioHolding.market == market,
                    )
                )
            }
            lots_by_code: dict[str, list[AgentLot]] = {}
            for lot in await session.scalars(
                select(AgentLot)
                .where(
                    AgentLot.user_id == agent.user_id,
                    AgentLot.market == market,
                    AgentLot.quantity_left > 0,
                )
                .order_by(AgentLot.id)
            ):
                lots_by_code.setdefault(lot.code, []).append(lot)

            # Exits first — they free slots and (eventually, at settlement) cash.
            for code, holding in list(holdings.items()):
                snap = snapshots.get(code)
                if snap is None:
                    continue  # no fresh quote for this code this tick: hold, don't guess
                reason = exit_reason(agent.strategy, snap, avg_cost=holding.avg_cost)
                if reason and await _sell(
                    session,
                    agent,
                    holding,
                    lots_by_code.get(code, []),
                    snap,
                    today,
                    reason,
                    categories.get(code),
                ):
                    counts["sells"] += 1
                    if holding.quantity <= 0:
                        del holdings[code]

            # Entries into whatever slots and settled cash remain. Queried after exits, so this
            # tick's own sells are included (autoflush) and can't be immediately rebought.
            cooling = set(
                (
                    await session.scalars(
                        select(AgentTrade.code).where(
                            AgentTrade.user_id == agent.user_id,
                            AgentTrade.market == market,
                            AgentTrade.side == "sell",
                            AgentTrade.trade_date >= today - REENTRY_COOLDOWN,
                        )
                    )
                ).all()
            )
            free_slots = spec.max_positions - len(holdings)
            pending_cash = float(
                await session.scalar(
                    select(func.coalesce(func.sum(AgentTrade.net_cash), 0.0)).where(
                        AgentTrade.user_id == agent.user_id,
                        AgentTrade.market == market,
                        AgentTrade.side == "sell",
                        AgentTrade.settled.is_(False),
                    )
                )
                or 0.0
            )
            target_budget = round(agent.initial_capital * spec.position_pct, 2)
            ranked = list(
                rank_entries(
                    agent.strategy,
                    snapshots.values(),
                    held=set(holdings) | cooling,
                )
            )
            candidate_codes = {snap.code for snap, _ in ranked}
            open_opportunities = {
                opportunity.code: opportunity
                for opportunity in await session.scalars(
                    select(AgentOpportunity).where(
                        AgentOpportunity.tenant_id == tenant_id,
                        AgentOpportunity.user_id == agent.user_id,
                        AgentOpportunity.market == market,
                        AgentOpportunity.strategy == agent.strategy,
                        AgentOpportunity.status == "open",
                    )
                )
            }

            # First close old episodes that now have an observable resolution. Missing/stale quotes
            # leave an episode open: absence of evidence is not evidence that the setup expired.
            for code, opportunity in list(open_opportunities.items()):
                snap = snapshots.get(code)
                if snap is None:
                    continue
                if code in holdings:
                    _resolve_opportunity(
                        opportunity, status="entered", observed_at=now, snap=snap
                    )
                elif code not in candidate_codes:
                    _resolve_opportunity(
                        opportunity, status="expired", observed_at=now, snap=snap
                    )
                else:
                    continue
                counts["opportunities_resolved"] += 1
                del open_opportunities[code]

            # Continue through the full ranked list for evidence collection even when the account
            # cannot buy. Trade selection itself is unchanged: no slot/cash means no execution.
            for rank, (snap, reason) in enumerate(ranked, start=1):
                block_reason: str | None = None
                if free_slots <= 0:
                    block_reason = "no_slot"
                elif agent.cash_settled < MIN_ORDER_VALUE:
                    block_reason = "no_cash"
                if block_reason is not None:
                    opportunity = _observe_blocked_opportunity(
                        open_opportunities.get(snap.code),
                        tenant_id=tenant_id,
                        agent=agent,
                        snap=snap,
                        observed_at=now,
                        signal_reason=reason,
                        block_reason=block_reason,
                        rank=rank,
                        target_budget=target_budget,
                        available_cash=agent.cash_settled,
                        pending_cash=pending_cash,
                        free_slots=free_slots,
                    )
                    if opportunity.id is None:
                        session.add(opportunity)
                    open_opportunities[snap.code] = opportunity
                    counts["opportunities"] += 1
                    continue

                budget = min(target_budget, agent.cash_settled)
                spent = await _buy(
                    session,
                    agent,
                    tenant_id,
                    holdings,
                    snap,
                    today,
                    budget,
                    reason,
                    categories.get(snap.code),
                )
                if spent <= 0:
                    opportunity = _observe_blocked_opportunity(
                        open_opportunities.get(snap.code),
                        tenant_id=tenant_id,
                        agent=agent,
                        snap=snap,
                        observed_at=now,
                        signal_reason=reason,
                        block_reason="order_too_small",
                        rank=rank,
                        target_budget=target_budget,
                        available_cash=agent.cash_settled,
                        pending_cash=pending_cash,
                        free_slots=free_slots,
                    )
                    if opportunity.id is None:
                        session.add(opportunity)
                    open_opportunities[snap.code] = opportunity
                    counts["opportunities"] += 1
                    continue

                counts["buys"] += 1
                free_slots -= 1
                opportunity = open_opportunities.pop(snap.code, None)
                if opportunity is not None:
                    _resolve_opportunity(
                        opportunity, status="entered", observed_at=now, snap=snap
                    )
                    counts["opportunities_resolved"] += 1

        await session.commit()
    return counts


async def _run() -> None:
    counts = await run_agents()
    print(f"[agents] {counts}")


def main() -> None:
    import asyncio

    asyncio.run(_run())


if __name__ == "__main__":
    main()
