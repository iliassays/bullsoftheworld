"""Watchdog data-quality checks — second line of defense behind the parser-level invariants
in packages/market_data. DB-gated: DB_TESTS=1 uv run pytest -k watchdog_data_quality

One test function (not several) — the module-level async engine from get_sessionmaker() caches
a connection bound to whichever event loop ran first, so splitting this across multiple async
test functions cross-loop-fails on the second one. Single loop, sequential scenarios.
"""

from __future__ import annotations

import datetime as dt
import os

import pytest
from sqlalchemy import delete

TEST_CODE = "ZWATCHDOGTEST"


@pytest.mark.skipif(not os.getenv("DB_TESTS"), reason="set DB_TESTS=1 with Postgres")
@pytest.mark.asyncio
async def test_data_quality_checks_catch_confirmed_incident_shapes() -> None:
    from bulls.core.db import get_sessionmaker
    from bulls.core.models import DailyBar, ShareholdingSnapshot
    from ingestion.watchdog import _data_quality_problems

    sm = get_sessionmaker()

    # Baseline: a clean database (no planted violations) must be silent — real edge cases like
    # a >1000% dividend (RECKITTBEN) or a real Z-category negative NAV must never trip these.
    problems = await _data_quality_problems()
    assert not any(TEST_CODE in p for p in problems)

    try:
        # high < low is never real — the confirmed SALVOCHEM shape (fake all-zero bars from a
        # suspended-stock '0.00' render that used to sail past a 'close is None' check).
        async with sm() as session:
            session.add(
                DailyBar(
                    market="DSE",
                    code=TEST_CODE,
                    date=dt.date(2020, 1, 1),
                    open=10,
                    high=5,
                    low=20,
                    close=8,
                    volume=100,
                )
            )
            await session.commit()
        problems = await _data_quality_problems()
        assert any("impossible OHLC" in p for p in problems)
    finally:
        async with sm() as session:
            await session.execute(delete(DailyBar).where(DailyBar.code == TEST_CODE))
            await session.commit()

    try:
        # 0/0/0/0/0 — the confirmed CNATEX/APOLOISPAT shape. No real disclosure sums to 0%.
        async with sm() as session:
            session.add(
                ShareholdingSnapshot(
                    market="DSE",
                    code=TEST_CODE,
                    as_of_date=dt.date(2020, 1, 1),
                    sponsor_director=0,
                    govt=0,
                    institute=0,
                    foreign_pct=0,
                    public=0,
                )
            )
            await session.commit()
        problems = await _data_quality_problems()
        assert any("not summing to ~100%" in p for p in problems)
    finally:
        async with sm() as session:
            await session.execute(
                delete(ShareholdingSnapshot).where(ShareholdingSnapshot.code == TEST_CODE)
            )
            await session.commit()

    # Cleanup verified: back to silent.
    problems = await _data_quality_problems()
    assert not any(TEST_CODE in p for p in problems)
