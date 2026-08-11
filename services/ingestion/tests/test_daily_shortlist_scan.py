from __future__ import annotations

import datetime as dt
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from ingestion.daily_shortlist_scan import (
    _history_counts,
    _range_position_pct,
    _validated_market,
)


def test_shortlist_scan_is_explicitly_dse_only() -> None:
    assert _validated_market("dse") == "DSE"
    with pytest.raises(ValueError, match="validated only"):
        _validated_market("US")


def test_range_position_refuses_missing_or_degenerate_ranges() -> None:
    assert _range_position_pct(50.0, 100.0, 0.0) == pytest.approx(50.0)
    assert _range_position_pct(50.0, None, 0.0) is None
    assert _range_position_pct(50.0, 10.0, 10.0) is None


@pytest.mark.asyncio
async def test_history_counts_are_point_in_time_and_symbol_scoped() -> None:
    session = SimpleNamespace(
        execute=AsyncMock(
            return_value=SimpleNamespace(all=lambda: [("AAA", 260), ("BBB", 259)])
        )
    )

    counts = await _history_counts(
        session,
        "DSE",
        dt.date(2026, 8, 10),
        codes={"BBB", "AAA"},
    )

    assert counts == {"AAA": 260, "BBB": 259}
    statement = str(session.execute.await_args.args[0])
    assert "daily_bars.market" in statement
    assert "daily_bars.date" in statement
    assert "daily_bars.code IN" in statement


@pytest.mark.asyncio
async def test_history_counts_skip_database_for_empty_universe() -> None:
    session = SimpleNamespace(execute=AsyncMock())

    assert await _history_counts(
        session,
        "DSE",
        dt.date(2026, 8, 10),
        codes=set(),
    ) == {}
    session.execute.assert_not_awaited()
