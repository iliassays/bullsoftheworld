"""Agent trading engine lifecycle — DB-gated: DB_TESTS=1 uv run pytest -k agent_trader

Uses a synthetic market "TST" so nothing in the dev DB's real DSE data can qualify for entries
and pollute the assertions (run_agents is market-scoped end to end). Walks one position through
the full simulated-broker lifecycle on a known calendar week (Sun 2026-06-21 ... Thu 06-25):

    buy Sun -> shares locked until T+2 (Tue) -> stop-loss can't fill Mon -> sells Tue ->
    proceeds pending -> credited at the sell's own T+2 (Thu)

Every date assertion below is the exchange rule, not an implementation detail.
"""

from __future__ import annotations

import datetime as dt
import os
import uuid

import pytest

pytestmark = [
    pytest.mark.skipif(not os.getenv("DB_TESTS"), reason="set DB_TESTS=1 with Postgres"),
    pytest.mark.asyncio,
]

MARKET = "TST"


def _utc(y: int, mo: int, d: int, h: int, mi: int = 0) -> dt.datetime:
    return dt.datetime(y, mo, d, h, mi, tzinfo=dt.UTC)


async def test_agent_full_lifecycle_with_t2_settlement() -> None:
    from sqlalchemy import delete, select

    from bulls.core.db import dispose_engine, get_sessionmaker
    from bulls.core.models import (
        AgentLot,
        AgentOpportunity,
        AgentPortfolio,
        AgentTrade,
        PortfolioHolding,
        QuoteSnapshot,
        Symbol,
        TickerAnalytics,
        User,
    )
    from bulls.core.security import hash_password
    from ingestion.agent_trader import run_agents

    await dispose_engine()
    sm = get_sessionmaker()
    code = "T" + uuid.uuid4().hex[:8].upper()
    handle = "TestValuePortfolio_" + uuid.uuid4().hex[:6]

    async def set_quote(session, ltp: float, change_pct: float, as_of: dt.datetime) -> None:
        q = await session.get(QuoteSnapshot, (MARKET, code))
        q.ltp, q.change_pct, q.as_of = ltp, change_pct, as_of
        await session.commit()

    async with sm() as session:
        user = User(
            tenant_id="test",
            handle=handle,
            name="Test Value Portfolio",
            password_hash=hash_password(uuid.uuid4().hex),
        )
        session.add(user)
        await session.flush()
        user_id = user.id
        session.add(
            AgentPortfolio(
                user_id=user_id,
                market=MARKET,
                strategy="value",
                initial_capital=100_000.0,
                cash_settled=100_000.0,
            )
        )
        session.add(Symbol(market=MARKET, code=code, name_en=code, category="A", is_active=True))
        # Clearly qualifies for the value strategy; comfortably liquid and large enough.
        session.add(
            TickerAnalytics(
                market=MARKET,
                code=code,
                as_of_date=dt.date(2026, 6, 18),
                last_close=100.0,
                pe_ratio=8.0,
                pb_ratio=0.9,
                pe_vs_sector=0.6,
                roe=12.0,
                avg_volume_20=200_000.0,
                market_cap_mn=2_000.0,
            )
        )
        session.add(
            QuoteSnapshot(
                market=MARKET,
                code=code,
                ltp=100.0,
                change=0.5,
                change_pct=0.5,
                open=99.5,
                high=100.5,
                low=99.0,
                close=100.0,
                prev_close=99.5,
                volume=50_000,
                trades=500,
                as_of=_utc(2026, 6, 21, 4, 50),
                is_delayed=True,
            )
        )
        await session.commit()

    try:
        # --- Sunday 06-21, mid-session: the value setup gets bought -------------------------
        counts = await run_agents(MARKET, tenant_id="test", now=_utc(2026, 6, 21, 5, 0))
        assert counts["buys"] == 1 and counts["sells"] == 0

        async with sm() as session:
            agent = await session.get(AgentPortfolio, user_id)
            holding = await session.get(PortfolioHolding, (user_id, MARKET, code))
            lot = (await session.scalars(select(AgentLot).where(AgentLot.user_id == user_id))).one()
            buy = (
                await session.scalars(select(AgentTrade).where(AgentTrade.user_id == user_id))
            ).one()
            # 15% of 1 lac at ~100/share with 0.4% brokerage -> 149 shares
            assert holding is not None and holding.quantity == 149
            assert holding.avg_cost == pytest.approx(100.0)
            assert buy.side == "buy" and buy.settled  # buy cash left immediately
            assert buy.fee == pytest.approx(149 * 100 * 0.004, abs=0.01)
            assert agent.cash_settled == pytest.approx(100_000 - 149 * 100 * 1.004, abs=0.01)
            # T+2 in trading days from Sunday = Tuesday
            assert lot.sellable_from == dt.date(2026, 6, 23)
            assert "sector" in buy.reason  # the descriptive audit trail exists

        # Same tick again: already held -> no double buy.
        counts = await run_agents(MARKET, tenant_id="test", now=_utc(2026, 6, 21, 5, 15))
        assert counts["buys"] == 0

        # --- Monday 06-22: price craters -15%, stop fires, but the lot is UNSETTLED ---------
        async with sm() as session:
            await set_quote(session, 85.0, -2.0, _utc(2026, 6, 22, 5, 0))
        counts = await run_agents(MARKET, tenant_id="test", now=_utc(2026, 6, 22, 5, 10))
        assert counts["sells"] == 0  # T+2: you cannot sell what hasn't been credited

        # --- Tuesday 06-23: lot matured -> the stop-loss sell executes -----------------------
        async with sm() as session:
            await set_quote(session, 85.0, -1.0, _utc(2026, 6, 23, 5, 0))
        counts = await run_agents(MARKET, tenant_id="test", now=_utc(2026, 6, 23, 5, 10))
        assert counts["sells"] == 1
        async with sm() as session:
            agent = await session.get(AgentPortfolio, user_id)
            cash_after_buy = agent.cash_settled
            sell = (
                await session.scalars(
                    select(AgentTrade).where(
                        AgentTrade.user_id == user_id, AgentTrade.side == "sell"
                    )
                )
            ).one()
            assert not sell.settled  # proceeds pending
            assert sell.quantity == 149 and sell.price == pytest.approx(85.0)
            assert sell.settles_on == dt.date(2026, 6, 25)  # Tue + 2 trading days = Thu
            assert "Stop-loss" in sell.reason
            assert await session.get(PortfolioHolding, (user_id, MARKET, code)) is None
            # Cooldown: the still-qualifying stale analytics row must NOT be rebought.
            buys = (
                await session.scalars(
                    select(AgentTrade).where(
                        AgentTrade.user_id == user_id, AgentTrade.side == "buy"
                    )
                )
            ).all()
            assert len(buys) == 1

        # --- Wednesday 06-24: proceeds still pending ----------------------------------------
        async with sm() as session:
            await set_quote(session, 85.0, 0.0, _utc(2026, 6, 24, 5, 0))
        await run_agents(MARKET, tenant_id="test", now=_utc(2026, 6, 24, 5, 10))
        async with sm() as session:
            agent = await session.get(AgentPortfolio, user_id)
            assert agent.cash_settled == pytest.approx(cash_after_buy)

        # --- Thursday 06-25: the sell settles, cash is finally spendable --------------------
        async with sm() as session:
            await set_quote(session, 85.0, 0.0, _utc(2026, 6, 25, 5, 0))
        counts = await run_agents(MARKET, tenant_id="test", now=_utc(2026, 6, 25, 5, 10))
        assert counts["settled"] == 1
        async with sm() as session:
            agent = await session.get(AgentPortfolio, user_id)
            expected = cash_after_buy + 149 * 85 * (1 - 0.004)
            assert agent.cash_settled == pytest.approx(expected, abs=0.02)
            # Net effect of the round trip: the account took a real, honest loss.
            assert agent.cash_settled < 100_000

        # --- Outside trading hours: a tick is a no-op ----------------------------------------
        assert await run_agents(MARKET, tenant_id="test", now=_utc(2026, 6, 26, 5, 0)) == {
            "skipped": 1
        }  # Friday

        # --- Stale feed: quotes >45 min old mean the engine refuses to act -------------------
        counts = await run_agents(
            MARKET, tenant_id="test", now=_utc(2026, 6, 28, 7, 0)
        )  # quote still from 06-25
        assert counts == {
            "agents": 0,
            "buys": 0,
            "sells": 0,
            "settled": 0,
            "opportunities": 0,
            "opportunities_resolved": 0,
        }
    finally:
        async with sm() as session:
            for model, cond in (
                (AgentTrade, AgentTrade.user_id == user_id),
                (AgentOpportunity, AgentOpportunity.user_id == user_id),
                (AgentLot, AgentLot.user_id == user_id),
                (AgentPortfolio, AgentPortfolio.user_id == user_id),
                (PortfolioHolding, PortfolioHolding.user_id == user_id),
                (QuoteSnapshot, (QuoteSnapshot.market == MARKET) & (QuoteSnapshot.code == code)),
                (
                    TickerAnalytics,
                    (TickerAnalytics.market == MARKET) & (TickerAnalytics.code == code),
                ),
                (Symbol, (Symbol.market == MARKET) & (Symbol.code == code)),
                (User, User.id == user_id),
            ):
                await session.execute(delete(model).where(cond))
            await session.commit()
        await dispose_engine()
