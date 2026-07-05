"""Agent portfolios — simulated model portfolios managed by deterministic strategy rules.

Each agent is a normal `User` (handle ending in "Portfolio") whose holdings live in the shared
`portfolio_holdings` table so the regular portfolio page and EOD snapshot job work unchanged.
These tables add what a *simulated broker account* needs on top of that:

- `AgentPortfolio` — the account: which strategy runs it, starting capital, and settled cash.
- `AgentTrade` — every simulated execution, with the exchange settlement date and a plain-language
  `reason` string so the admin can audit each decision from the cockpit.
- `AgentLot` — per-buy share lots. DSE credits bought shares on T+2 (A/B/G/N category) or T+3 (Z),
  counted in *trading days*; a lot is sellable only from `sellable_from`. Sale proceeds settle on
  the same cycle, so cash from a sell is spendable only after `settles_on`.

Simulation honesty rules (mirrors "never fake data freshness"): every trade records the `as_of`
of the quote it filled against, fills happen at the last traded price with brokerage charged —
never at prices we didn't observe. This is paper trading for the platform's own model portfolios,
never advice; the agent users stay `portfolio_public=false` unless explicitly flipped.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from bulls.core.db import Base


class AgentPortfolio(Base):
    __tablename__ = "agent_portfolios"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    market: Mapped[str] = mapped_column(String(8))
    strategy: Mapped[str] = mapped_column(String(24))  # see bulls.analytics.strategies.STRATEGIES
    initial_capital: Mapped[float] = mapped_column(Float)
    # Spendable cash right now. Buys debit it immediately (a broker requires funds to order);
    # sell proceeds are credited only when the trade's settles_on arrives — until then they're
    # visible as pending on unsettled sell trades, deliberately NOT in this number.
    cash_settled: Mapped[float] = mapped_column(Float)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class AgentTrade(Base):
    __tablename__ = "agent_trades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    market: Mapped[str] = mapped_column(String(8))
    code: Mapped[str] = mapped_column(String(16))
    side: Mapped[str] = mapped_column(String(4))  # "buy" | "sell"
    quantity: Mapped[int] = mapped_column(Integer)
    price: Mapped[float] = mapped_column(Float)  # fill price = last traded price at the tick
    fee: Mapped[float] = mapped_column(Float)  # brokerage on the gross value
    net_cash: Mapped[float] = mapped_column(Float)  # signed: buy -(gross+fee), sell +(gross-fee)
    trade_date: Mapped[dt.date] = mapped_column(Date)
    settles_on: Mapped[dt.date] = mapped_column(Date)  # T+2 (A/B/G/N) or T+3 (Z), trading days
    # Buys are born settled (cash left immediately). A sell stays unsettled until the engine
    # credits its proceeds on/after settles_on.
    settled: Mapped[bool] = mapped_column(Boolean, default=False)
    reason: Mapped[str] = mapped_column(String(300))  # descriptive audit trail for the cockpit
    quote_as_of: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class AgentLot(Base):
    """One buy execution's shares, consumed FIFO by later sells. `quantity_left` reaching 0 keeps
    the row (it documents history); sellable quantity for a code = sum of quantity_left over lots
    with sellable_from <= today."""

    __tablename__ = "agent_lots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    market: Mapped[str] = mapped_column(String(8))
    code: Mapped[str] = mapped_column(String(16))
    quantity: Mapped[int] = mapped_column(Integer)
    quantity_left: Mapped[int] = mapped_column(Integer)
    buy_price: Mapped[float] = mapped_column(Float)
    trade_date: Mapped[dt.date] = mapped_column(Date)
    sellable_from: Mapped[dt.date] = mapped_column(Date)  # the lot's settlement date
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
