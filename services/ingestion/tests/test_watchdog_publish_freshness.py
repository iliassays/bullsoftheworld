"""Watchdog publish-freshness checks — catches a stalled arq cron loop that the EOD bars/trending
check can't see (confirmed live 2026-07-06: the loop stalled ~30 min with the worker unit still
"active", dropping run_trending/run_signals/pull_news/run_factor_signals with no error logged).
DB-gated: DB_TESTS=1 uv run pytest -k watchdog_publish_freshness

One test function: the module-level async engine caches a connection bound to whichever event
loop ran first, so splitting this across multiple async test functions cross-loop-fails (see
test_watchdog_data_quality.py for the same note).
"""

from __future__ import annotations

import datetime as dt
import os
import uuid

import pytest
import redis.asyncio as aioredis
from sqlalchemy import delete

from bulls.core.config import get_settings

# 2026-07-02 is a real Thursday (DSE trading day, confirmed elsewhere this session) with no
# holiday override — safe, deterministic "is_trading_day" input for this test.
_TRADING_DAY = dt.date(2026, 7, 2)
_NOW_MORNING = dt.datetime(2026, 7, 2, 6, 0, tzinfo=dt.UTC)  # past the 05:00 morning-watch check
_NOW_EOD = dt.datetime(2026, 7, 2, 15, 0, tzinfo=dt.UTC)  # inside the 14:00-18:00 EOD window


@pytest.mark.skipif(not os.getenv("DB_TESTS"), reason="set DB_TESTS=1 with Postgres")
@pytest.mark.asyncio
async def test_publish_freshness_catches_missing_morning_watch_and_missing_signals() -> None:
    from bulls.core.db import dispose_engine, get_sessionmaker
    from bulls.core.models import SignalEvent
    from ingestion.watchdog import _publish_freshness_problems

    await dispose_engine()
    sm = get_sessionmaker()
    code = "T" + uuid.uuid4().hex[:8].upper()

    try:
        # Nothing posted, nothing fired: both checks should complain. Relies on the local dev DB
        # genuinely having no non-Volume signal_events dated 2026-07-02 (confirmed before writing
        # this test: the seeded range is 2026-06-25/26 only) — deliberately NOT deleting anything
        # broad here, only ever cleaning up this test's own scoped rows in the `finally` below.
        problems = await _publish_freshness_problems(_NOW_MORNING)
        assert any("Morning Watch" in p for p in problems)

        # Setting the same dedup key the real /admin/fb/publish endpoint sets on a successful
        # post must clear the flag — this check reads exactly that key, nothing separate.
        redis_key = f"fb:posted:bullsofdhaka:morning_watch:{_TRADING_DAY}"
        r = aioredis.from_url(get_settings().redis_url)
        await r.set(redis_key, "test-post-id")
        try:
            problems = await _publish_freshness_problems(_NOW_MORNING)
            assert not any("Morning Watch" in p for p in problems)
        finally:
            await r.delete(redis_key)
            await r.aclose()

        problems = await _publish_freshness_problems(_NOW_EOD)
        assert any("signal notes" in p for p in problems)

        # A real signal event (even a single one, from a non-Volume agent) should clear the
        # "implausibly quiet" flag — the check only cares that the cron tick ran at all.
        async with sm() as session:
            session.add(
                SignalEvent(
                    tenant_id="bullsofdhaka",
                    agent="BullsOfDhakaLevels",
                    event_type="breakout",
                    market="DSE",
                    code=code,
                    as_of_date=_TRADING_DAY,
                    occurrence_key=str(_TRADING_DAY),
                    created_at=dt.datetime(2026, 7, 2, 13, 25, tzinfo=dt.UTC),
                )
            )
            await session.commit()
        problems = await _publish_freshness_problems(_NOW_EOD)
        assert not any("signal notes" in p for p in problems)

        # Outside either check window, or on a non-trading day, both checks stay silent.
        assert await _publish_freshness_problems(dt.datetime(2026, 7, 2, 1, 0, tzinfo=dt.UTC)) == []
        assert (
            await _publish_freshness_problems(dt.datetime(2026, 7, 3, 15, 0, tzinfo=dt.UTC)) == []
        )  # 2026-07-03 is a Friday — not a DSE trading day
    finally:
        async with sm() as session:
            await session.execute(delete(SignalEvent).where(SignalEvent.code == code))
            await session.commit()
