"""compute_all() chart-pattern hook — DB-gated: DB_TESTS=1 uv run pytest -k analytics_patterns

This exercises the WHOLE-market compute_all() job (it has no per-code entry point), so it
recomputes ticker_analytics/ticker_patterns for every symbol in the dev DB, not just the one this
test cares about — the same cost every real run of this job already pays. The test only asserts on
its own seeded code, and cleans up after itself either way.
"""

from __future__ import annotations

import datetime as dt
import os
import uuid

import pytest


@pytest.mark.skipif(not os.getenv("DB_TESTS"), reason="set DB_TESTS=1 with Postgres")
@pytest.mark.asyncio
async def test_compute_all_stores_a_detected_pattern_for_a_clear_shape() -> None:
    """dispose_engine() before/after: see test_portfolio_snapshot.py for why (SQLAlchemy's async
    engine is bound to whichever event loop created it; pytest-asyncio gives each test its own)."""
    from sqlalchemy import delete

    from bulls.core.db import dispose_engine, get_sessionmaker
    from bulls.core.models import DailyBar, Symbol, TickerAnalytics, TickerPattern
    from ingestion.analytics import compute_all

    await dispose_engine()
    sm = get_sessionmaker()
    code = "T" + uuid.uuid4().hex[:8].upper()

    # An explicit ascending triangle: flat resistance ~110, support rising from 90 — same shape as
    # packages/analytics/tests/test_patterns.py's synthetic case, seeded as real DailyBar rows.
    start = dt.date(2026, 1, 1)
    idx = list(range(0, 140, 10))
    closes: list[float] = []
    for k in range(len(idx) - 1):
        i0, i1 = idx[k], idx[k + 1]
        v0 = 110.0 if k % 2 == 0 else 90 + i0 * 0.15
        v1 = 90 + i1 * 0.15 if k % 2 == 1 else 110.0
        for i in range(i0, i1):
            frac = (i - i0) / (i1 - i0)
            closes.append(v0 + frac * (v1 - v0))
    closes.append(90 + idx[-1] * 0.15)

    async with sm() as session:
        session.add(Symbol(market="DSE", code=code, name_en=code, category="A", is_active=True))
        session.add_all(
            DailyBar(
                market="DSE",
                code=code,
                date=start + dt.timedelta(days=i),
                open=c,
                high=c + 0.3,
                low=c - 0.3,
                close=c,
                volume=10_000,
            )
            for i, c in enumerate(closes)
        )
        await session.commit()

    try:
        stats = await compute_all("DSE")
        assert stats["patterns"] >= 1

        async with sm() as session:
            row = await session.get(TickerPattern, ("DSE", code))
            assert row is not None
            assert row.pattern_type == "ascending_triangle"
            assert row.strength_score >= 60
            assert row.payload["resistance_line"] is not None
    finally:
        async with sm() as session:
            await session.execute(
                delete(TickerPattern).where(
                    TickerPattern.market == "DSE", TickerPattern.code == code
                )
            )
            await session.execute(
                delete(TickerAnalytics).where(
                    TickerAnalytics.market == "DSE", TickerAnalytics.code == code
                )
            )
            await session.execute(
                delete(DailyBar).where(DailyBar.market == "DSE", DailyBar.code == code)
            )
            await session.execute(delete(Symbol).where(Symbol.market == "DSE", Symbol.code == code))
            await session.commit()
