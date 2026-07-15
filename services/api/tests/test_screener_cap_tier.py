"""Cap-tier enrichment + size filter on screens — DB-gated: DB_TESTS=1 uv run pytest -k cap_tier

The tier shown on a screen row must be the denormalized ticker_analytics.cap_tier (written by the
same analytics run that produced the row's other numbers), and the `size` refinement must filter
rows without re-scoring them. Tier vocabularies are per market: `mega` exists for US only, so
requesting it on DSE must be a 422, not an empty list that looks like "no matches today".
"""

from __future__ import annotations

import datetime as dt
import os
import uuid

import pytest

from bulls.core.markets import get_market_profile


def test_size_param_vocabulary_is_market_scoped() -> None:
    dse = {tier for tier, _ in get_market_profile("DSE").cap_tiers}
    us = {tier for tier, _ in get_market_profile("US").cap_tiers}
    assert "mega" not in dse and "mega" in us
    assert {"large", "mid", "small", "micro"} <= dse <= us


@pytest.mark.skipif(not os.getenv("DB_TESTS"), reason="set DB_TESTS=1 with Postgres")
@pytest.mark.asyncio
async def test_enrich_sets_cap_tier_from_analytics_row() -> None:
    from sqlalchemy import delete

    from api.routers.screener import ScreenItem, ScreenOut, _enrich
    from bulls.core.db import dispose_engine, get_sessionmaker
    from bulls.core.models import TickerAnalytics

    await dispose_engine()
    sm = get_sessionmaker()
    code = "T" + uuid.uuid4().hex[:8].upper()
    try:
        async with sm() as session:
            session.add(
                TickerAnalytics(
                    market="DSE",
                    code=code,
                    as_of_date=dt.date(2026, 7, 14),
                    last_close=100.0,
                    market_cap_mn=12_000.0,
                    cap_tier="large",
                )
            )
            await session.commit()

            screen = ScreenOut(
                key="value_vs_sector",
                title="t",
                description="d",
                value_label="v",
                items=[ScreenItem(code=code, last_close=100.0, value=1.0)],
            )
            await _enrich(session, "DSE", [screen])
            assert screen.items[0].cap_tier == "large"
            assert screen.items[0].market_cap_mn == 12_000.0
    finally:
        # A leftover fake row becomes the freshest as_of_date and empties every screen for the
        # whole database (screenable codes require the max date) — always clean up.
        async with sm() as session:
            await session.execute(
                delete(TickerAnalytics).where(
                    TickerAnalytics.market == "DSE", TickerAnalytics.code == code
                )
            )
            await session.commit()
