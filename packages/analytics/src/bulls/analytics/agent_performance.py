"""Auditable FIFO performance attribution for simulated agent portfolios.

The trading engine remains the source of truth for cash and holdings. This module independently
reconstructs realized and unrealized P&L from executions, which lets the UI expose whether a gain
has actually been closed or is only a current mark.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Protocol


class TradeLike(Protocol):
    code: str
    side: str
    quantity: int
    price: float
    fee: float


@dataclass(frozen=True)
class AgentPerformance:
    realized_pnl: float
    unrealized_pnl: float | None
    fees: float
    closed_trades: int
    winning_trades: int
    win_rate: float | None
    open_cost: float


def calculate_agent_performance(
    trades: list[TradeLike], prices: dict[str, float]
) -> AgentPerformance:
    """Rebuild FIFO cost basis from ordered executions.

    Buy and sell fees are allocated per share. An absent current price makes unrealized P&L
    unknown rather than silently valuing the position at cost.
    """
    lots: dict[str, deque[list[float]]] = defaultdict(deque)
    realized = 0.0
    closed = 0
    wins = 0
    fees = 0.0

    for trade in trades:
        qty = int(trade.quantity)
        if qty <= 0:
            continue
        fees += float(trade.fee)
        if trade.side == "buy":
            unit_cost = float(trade.price) + float(trade.fee) / qty
            lots[trade.code].append([float(qty), unit_cost])
            continue
        if trade.side != "sell":
            raise ValueError(f"Unknown agent trade side: {trade.side!r}")

        remaining = float(qty)
        unit_proceeds = float(trade.price) - float(trade.fee) / qty
        trade_pnl = 0.0
        while remaining > 0 and lots[trade.code]:
            lot = lots[trade.code][0]
            matched = min(remaining, lot[0])
            trade_pnl += matched * (unit_proceeds - lot[1])
            lot[0] -= matched
            remaining -= matched
            if lot[0] <= 1e-9:
                lots[trade.code].popleft()
        if remaining > 1e-9:
            raise ValueError(f"Sell quantity exceeds FIFO inventory for {trade.code}")
        realized += trade_pnl
        closed += 1
        wins += int(trade_pnl > 0)

    open_cost = 0.0
    unrealized = 0.0
    prices_complete = True
    for code, code_lots in lots.items():
        for quantity, unit_cost in code_lots:
            open_cost += quantity * unit_cost
            price = prices.get(code)
            if price is None:
                prices_complete = False
            else:
                unrealized += quantity * (price - unit_cost)

    return AgentPerformance(
        realized_pnl=round(realized, 2),
        unrealized_pnl=round(unrealized, 2) if prices_complete else None,
        fees=round(fees, 2),
        closed_trades=closed,
        winning_trades=wins,
        win_rate=round(wins / closed * 100, 1) if closed else None,
        open_cost=round(open_cost, 2),
    )
