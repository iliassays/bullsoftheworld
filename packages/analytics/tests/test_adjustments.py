from __future__ import annotations

import datetime as dt
from types import SimpleNamespace

from bulls.analytics import adjust_bars
from bulls.analytics.adjustments import adjustment_factor


def test_adjust_bars_scales_ohlc_but_preserves_volume() -> None:
    raw = SimpleNamespace(
        market="US",
        code="TEST",
        date=dt.date(2026, 1, 2),
        open=100.0,
        high=110.0,
        low=90.0,
        close=100.0,
        adjusted_close=50.0,
        volume=1_000,
    )

    adjusted = adjust_bars([raw])[0]

    assert adjusted.market == "US"
    assert adjusted.code == "TEST"
    assert adjusted.open == 50.0
    assert adjusted.high == 55.0
    assert adjusted.low == 45.0
    assert adjusted.close == 50.0
    assert adjusted.volume == 1_000


def test_rejects_nonpositive_or_nonfinite_adjustments() -> None:
    assert adjustment_factor(10.0, 0.0) is None
    assert adjustment_factor(10.0, -1.0) is None
    assert adjustment_factor(10.0, float("nan")) is None
    assert adjustment_factor(0.0, 10.0) is None


def test_adjust_bars_quarantines_invalid_adjusted_close() -> None:
    raw = SimpleNamespace(
        market="US",
        code="TEST",
        date=dt.date(2026, 1, 2),
        open=10.0,
        high=11.0,
        low=9.0,
        close=10.0,
        adjusted_close=-2.0,
        volume=1_000,
    )

    assert adjust_bars([raw]) == []
