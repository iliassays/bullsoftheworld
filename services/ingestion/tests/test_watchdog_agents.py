"""Watchdog agent-portfolio invariants — DB-gated: DB_TESTS=1 uv run pytest -k watchdog_agents

One test function, sequential scenarios (same reason as test_watchdog_data_quality.py: the
module-level async engine binds to the first event loop; multiple async tests cross-loop-fail).
Each planted violation is impossible for a correct engine, so the check must fire on it and be
silent on the clean baseline.
"""

from __future__ import annotations

import datetime as dt
import os
import uuid

import pytest
from sqlalchemy import delete


@pytest.mark.skipif(not os.getenv("DB_TESTS"), reason="set DB_TESTS=1 with Postgres")
@pytest.mark.asyncio
async def test_agent_invariant_checks_fire_on_planted_violations() -> None:
    from bulls.core.db import dispose_engine, get_sessionmaker
    from bulls.core.models import AgentLot, AgentPortfolio, AgentTrade, PortfolioHolding, User
    from bulls.core.security import hash_password
    from ingestion.watchdog import _agent_problems

    await dispose_engine()
    sm = get_sessionmaker()
    handle = "WatchdogTestPortfolio_" + uuid.uuid4().hex[:6]
    now = dt.datetime.now(dt.UTC)

    async with sm() as session:
        user = User(
            tenant_id="test",
            handle=handle,
            name="Watchdog Test Portfolio",
            password_hash=hash_password(uuid.uuid4().hex),
        )
        session.add(user)
        await session.flush()
        user_id = user.id
        session.add(
            AgentPortfolio(
                user_id=user_id,
                market="TST",
                strategy="value",
                initial_capital=100_000.0,
                cash_settled=100_000.0,
            )
        )
        await session.commit()

    try:
        # Clean baseline: silent for this agent.
        problems = await _agent_problems(now, market="TST", tenant_id="test")
        assert not any(handle in p for p in problems)

        # 1. Negative settled cash.
        async with sm() as session:
            agent = await session.get(AgentPortfolio, user_id)
            agent.cash_settled = -12.5
            await session.commit()
        problems = await _agent_problems(now, market="TST", tenant_id="test")
        assert any(handle in p and "NEGATIVE settled cash" in p for p in problems)
        async with sm() as session:
            agent = await session.get(AgentPortfolio, user_id)
            agent.cash_settled = 100_000.0
            await session.commit()

        # 2. A sell past its settlement date, never credited.
        async with sm() as session:
            session.add(
                AgentTrade(
                    user_id=user_id,
                    market="TST",
                    code="WDTEST",
                    side="sell",
                    quantity=10,
                    price=100.0,
                    fee=4.0,
                    net_cash=996.0,
                    trade_date=dt.date(2026, 1, 4),
                    settles_on=dt.date(2026, 1, 6),
                    settled=False,
                    reason="planted for watchdog test",
                    quote_as_of=now,
                )
            )
            await session.commit()
        problems = await _agent_problems(now, market="TST", tenant_id="test")
        assert any(handle in p and "past settlement" in p for p in problems)
        async with sm() as session:
            await session.execute(delete(AgentTrade).where(AgentTrade.user_id == user_id))
            await session.commit()

        # 3. Books disagree: a holding with no lots behind it.
        async with sm() as session:
            session.add(
                PortfolioHolding(
                    user_id=user_id,
                    tenant_id="test",
                    market="TST",
                    code="WDTEST",
                    quantity=10,
                    avg_cost=100.0,
                )
            )
            await session.commit()
        problems = await _agent_problems(now, market="TST", tenant_id="test")
        assert any(handle in p and "books disagree" in p for p in problems)
        # ...and the mirror image: an open lot with no holding row.
        async with sm() as session:
            await session.execute(
                delete(PortfolioHolding).where(PortfolioHolding.user_id == user_id)
            )
            session.add(
                AgentLot(
                    user_id=user_id,
                    market="TST",
                    code="WDTEST",
                    quantity=10,
                    quantity_left=10,
                    buy_price=100.0,
                    trade_date=dt.date(2026, 1, 4),
                    sellable_from=dt.date(2026, 1, 6),
                )
            )
            await session.commit()
        problems = await _agent_problems(now, market="TST", tenant_id="test")
        assert any(handle in p and "books disagree" in p for p in problems)
    finally:
        async with sm() as session:
            for model, cond in (
                (AgentTrade, AgentTrade.user_id == user_id),
                (AgentLot, AgentLot.user_id == user_id),
                (PortfolioHolding, PortfolioHolding.user_id == user_id),
                (AgentPortfolio, AgentPortfolio.user_id == user_id),
                (User, User.id == user_id),
            ):
                await session.execute(delete(model).where(cond))
            await session.commit()
        await dispose_engine()
