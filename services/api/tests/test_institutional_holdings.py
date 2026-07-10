from __future__ import annotations

import datetime as dt
from types import SimpleNamespace

from api.routers.regulatory import _holding_horizons, _period_return
from bulls.core.models import DailyBar


def _bar(day: int, close: float) -> DailyBar:
    return DailyBar(
        market="US",
        code="TEST",
        date=dt.date(2026, 1, day),
        open=close,
        high=close,
        low=close,
        close=close,
        adjusted_close=close,
        volume=1,
        source="test",
    )


def test_period_return_starts_when_disclosure_is_public() -> None:
    bars = [_bar(day, 100 + day) for day in range(1, 31)]

    result = _period_return(bars, dt.date(2026, 1, 2), 20)

    assert result == (121 / 102 - 1) * 100
    assert _period_return(bars, dt.date(2026, 1, 20), 20) is None


def test_holding_horizons_compare_reported_snapshots_without_inventing_trade_dates() -> None:
    summaries = [
        SimpleNamespace(report_date=dt.date(2026, 3, 31), total_shares=120),
        SimpleNamespace(report_date=dt.date(2025, 12, 31), total_shares=100),
        SimpleNamespace(report_date=dt.date(2025, 9, 30), total_shares=90),
        SimpleNamespace(report_date=dt.date(2025, 6, 30), total_shares=80),
    ]

    horizons = _holding_horizons(summaries)  # type: ignore[arg-type]

    assert [(row.quarters, row.reported_share_change_pct) for row in horizons] == [
        (2, 20.0),
        (4, 50.0),
    ]
