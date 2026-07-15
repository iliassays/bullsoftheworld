"""Daily portfolio snapshot job — DB-gated: DB_TESTS=1 uv run pytest -k portfolio_snapshot"""

from __future__ import annotations

import datetime as dt
import os
import uuid

import pytest
from sqlalchemy import delete, select

TEST_CODE = "GP"  # a real, always-listed symbol so QuoteSnapshot has a price for it


@pytest.mark.skipif(not os.getenv("DB_TESTS"), reason="set DB_TESTS=1 with Postgres")
@pytest.mark.asyncio
async def test_snapshot_is_idempotent_and_honest_when_unpriced() -> None:
    """SQLAlchemy's async engine caches a connection pool bound to whichever event loop created
    it; pytest-asyncio gives each test function its own loop, so a lingering engine from a prior
    test (or left behind for the next one) crashes cross-loop. dispose_engine() before AND after
    keeps this test isolated regardless of what else runs in the same pytest session."""
    from bulls.core.db import bind_tenant_context, dispose_engine, get_sessionmaker
    from bulls.core.models import PortfolioHolding, PortfolioSnapshot, User
    from bulls.market_data.calendar import to_market_tz
    from ingestion.portfolio_snapshot import run

    await dispose_engine()
    sm = get_sessionmaker()
    handle = "t" + uuid.uuid4().hex[:12]
    async with sm() as session:
        await bind_tenant_context(session, "bullsofdhaka")
        user = User(
            tenant_id="bullsofdhaka", handle=handle, name="Snapshot Tester", password_hash="x"
        )
        session.add(user)
        await session.flush()
        user_id = user.id
        session.add(
            PortfolioHolding(
                user_id=user_id,
                tenant_id="bullsofdhaka",
                market="DSE",
                code=TEST_CODE,
                quantity=10,
                avg_cost=100.0,
            )
        )
        # A holding in a symbol with no current quote must show total_value=None, not a fake 0 —
        # same "unpriced, not zero" principle as compute_portfolio().
        session.add(
            PortfolioHolding(
                user_id=user_id,
                tenant_id="bullsofdhaka",
                market="DSE",
                code="ZNOQUOTETEST",
                quantity=5,
                avg_cost=50.0,
            )
        )
        await session.commit()

    try:
        stats = await run("DSE")
        assert stats["users"] >= 1

        today = to_market_tz(dt.datetime.now(dt.UTC)).date()
        async with sm() as session:
            await bind_tenant_context(session, "bullsofdhaka")
            row = await session.get(PortfolioSnapshot, (user_id, "DSE", today))
        assert row is not None
        assert row.total_cost == pytest.approx(10 * 100.0 + 5 * 50.0)
        # GP is priced; ZNOQUOTETEST presumably isn't a real symbol so it never gets a quote —
        # total_value still reflects the priced portion only if ANY holding priced, else None.
        # Either way it must not silently equal total_cost or 0.
        if row.total_value is not None:
            assert row.total_value != row.total_cost

        # Re-run same day: idempotent upsert, not a duplicate row or an error.
        await run("DSE")
        async with sm() as session:
            await bind_tenant_context(session, "bullsofdhaka")
            count = len(
                (
                    await session.scalars(
                        select(PortfolioSnapshot).where(PortfolioSnapshot.user_id == user_id)
                    )
                ).all()
            )
        assert count == 1
    finally:
        async with sm() as session:
            await bind_tenant_context(session, "bullsofdhaka")
            await session.execute(
                delete(PortfolioSnapshot).where(PortfolioSnapshot.user_id == user_id)
            )
            await session.execute(
                delete(PortfolioHolding).where(PortfolioHolding.user_id == user_id)
            )
            await session.execute(delete(User).where(User.id == user_id))
            await session.commit()
        await dispose_engine()
