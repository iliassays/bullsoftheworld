from __future__ import annotations

import datetime as dt
from types import SimpleNamespace

from bulls.analytics import adjust_bars


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
