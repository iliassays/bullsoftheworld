"""_ownership() direction-aware key/title — DB-gated: DB_TESTS=1 uv run pytest -k ownership_selling

2026-07-05: a user asked why Sponsor Selling had its own headline board while institutional
distribution had none, even though the same underlying function already supported
direction="sell". The bug this uncovered: _ownership() always returned key="..._buying" and the
buy-side title regardless of direction, so a sell-direction call would have silently mislabeled
itself as a buying board. Fixed by making key/title direction-aware; this test locks that in and
checks the new institutional_selling board actually surfaces a real distribution row.
"""

from __future__ import annotations

import datetime as dt
import os
import uuid

import pytest


@pytest.mark.skipif(not os.getenv("DB_TESTS"), reason="set DB_TESTS=1 with Postgres")
@pytest.mark.asyncio
async def test_institutional_selling_has_its_own_key_title_and_surfaces_a_real_drop() -> None:
    from api.routers.screener import _ownership
    from bulls.core.db import dispose_engine, get_sessionmaker
    from bulls.core.models import ShareholdingSnapshot, Symbol, TickerAnalytics

    await dispose_engine()
    sm = get_sessionmaker()
    code = "T" + uuid.uuid4().hex[:8].upper()
    async with sm() as session:
        session.add(
            Symbol(market="DSE", code=code, name_en=code, category="A", is_active=True, is_hidden=False)
        )
        session.add(
            TickerAnalytics(
                market="DSE",
                code=code,
                as_of_date=dt.date(2026, 7, 2),
                last_close=100.0,
                avg_volume_20=100_000.0,  # 100k * 100 / 1e6 = 10mn ADTV, above the 5mn floor
                market_cap_mn=1000.0,
                free_float_cap_mn=500.0,
                institute_delta=-5.0,  # a real drop, above the 0.05pp noise floor
            )
        )
        session.add_all(
            [
                ShareholdingSnapshot(
                    market="DSE", code=code, as_of_date=dt.date(2026, 4, 30), institute=20.0
                ),
                ShareholdingSnapshot(
                    market="DSE", code=code, as_of_date=dt.date(2026, 7, 1), institute=15.0
                ),
            ]
        )
        await session.commit()

        screen = await _ownership(session, "DSE", kind="institute", direction="sell")

    assert screen.key == "institutional_selling"
    assert screen.title == "Institutional Selling"
    row = next((it for it in screen.items if it.code == code), None)
    assert row is not None, "the disclosed drop should surface on the selling board"
    assert row.value == pytest.approx(-5.0)


@pytest.mark.skipif(not os.getenv("DB_TESTS"), reason="set DB_TESTS=1 with Postgres")
@pytest.mark.asyncio
async def test_institutional_buying_keeps_its_original_key_and_title() -> None:
    """Regression guard: the direction-aware key/title change must not touch the buy side, which
    is already relied on by _build_screen_by_key, _SCREEN_EVIDENCE, FOCUS_KEYS, etc."""
    from api.routers.screener import _ownership
    from bulls.core.db import dispose_engine, get_sessionmaker

    await dispose_engine()
    sm = get_sessionmaker()
    async with sm() as session:
        screen = await _ownership(session, "DSE", kind="institute", direction="buy")

    assert screen.key == "institutional_buying"
    assert screen.title == "Institutions"
