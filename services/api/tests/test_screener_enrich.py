"""_enrich() cross-screen 1D-change leakage — DB-gated: DB_TESTS=1 uv run pytest -k screener_enrich

Regression for a 2026-07-05 user report: BSC showed no price change at all on the "Cheap vs
sector" board. Root cause: _NO_1D (top_gainers/top_losers, which already show the move as their
headline value) was implemented by excluding those codes from the _change_1d() DB query entirely
via a flat `skip` set of codes — not scoped per screen. BSC was today's top gainer, so it got
excluded from the query and its change_1d came back None on every OTHER board too, including
value_vs_sector, even though that board has nothing to do with top_gainers/top_losers.
"""

from __future__ import annotations

import datetime as dt
import os
import uuid

import pytest


@pytest.mark.skipif(not os.getenv("DB_TESTS"), reason="set DB_TESTS=1 with Postgres")
@pytest.mark.asyncio
async def test_code_on_a_no_1d_screen_still_gets_change_1d_on_other_screens() -> None:
    from api.routers.screener import ScreenItem, ScreenOut, _enrich
    from bulls.core.db import dispose_engine, get_sessionmaker
    from bulls.core.models import DailyBar

    await dispose_engine()
    sm = get_sessionmaker()
    code = "T" + uuid.uuid4().hex[:8].upper()
    today = dt.date(2026, 7, 2)
    prev = dt.date(2026, 6, 30)
    async with sm() as session:
        session.add_all(
            [
                DailyBar(
                    market="DSE",
                    code=code,
                    date=prev,
                    open=100.0,
                    high=101.0,
                    low=99.0,
                    close=100.0,
                    volume=1000,
                ),
                DailyBar(
                    market="DSE",
                    code=code,
                    date=today,
                    open=100.0,
                    high=111.0,
                    low=100.0,
                    close=110.0,
                    volume=1000,
                ),
            ]
        )
        await session.commit()

        # same code appears on a _NO_1D screen (top_gainers) AND an unrelated screen
        # (value_vs_sector) — the latter must still get its 1D change.
        top_gainers = ScreenOut(
            key="top_gainers",
            title="t",
            description="d",
            value_label="v",
            items=[ScreenItem(code=code, last_close=110.0, value=10.0)],
        )
        value_vs_sector = ScreenOut(
            key="value_vs_sector",
            title="t",
            description="d",
            value_label="v",
            items=[ScreenItem(code=code, last_close=110.0, value=0.5)],
        )
        await _enrich(session, "DSE", [top_gainers, value_vs_sector])

    # suppressed on its own headline board...
    assert top_gainers.items[0].change_1d is None
    # ...but present on the unrelated board, where it's the only source of the % move
    assert value_vs_sector.items[0].change_1d == pytest.approx(10.0)
