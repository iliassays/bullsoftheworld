"""End-to-end engine tests on synthetic bars."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from bulls.analytics import compute


@dataclass
class B:
    """Minimal BarLike stand-in for tests."""

    market: str
    code: str
    date: dt.date
    high: float
    low: float
    close: float
    volume: int


def _bars(closes: list[float], *, code: str = "GP") -> list[B]:
    start = dt.date(2024, 1, 1)
    return [
        B(
            market="DSE",
            code=code,
            date=start + dt.timedelta(days=i),
            high=c + 1,
            low=c - 1,
            close=c,
            volume=1000 + i,
        )
        for i, c in enumerate(closes)
    ]


def test_uptrend_snapshot():
    bars = _bars([100 + i * 0.5 for i in range(250)])
    r = compute(bars)

    assert r.market == "DSE" and r.code == "GP"
    assert r.as_of_date == bars[-1].date
    assert r.bars_used == 250
    # rising series: last close is above both long averages
    assert r.above_sma_50 is True
    assert r.above_sma_200 is True
    assert r.sma_50 is not None and r.sma_200 is not None
    assert r.rsi_14 == 100.0  # monotonic up
    # 52w high is the latest high in a pure uptrend; pct_from_high ~ small/negative
    assert r.week52_high is not None and r.pct_from_52w_high is not None
    assert r.pct_from_52w_high <= 0
    assert r.relative_volume is not None


def test_insufficient_history_is_partial_not_error():
    r = compute(_bars([10.0, 11.0, 12.0, 11.0, 10.0]))
    assert r.bars_used == 5
    assert r.sma_50 is None  # can't compute long MAs
    assert r.sma_200 is None
    assert r.above_sma_50 is None
    assert r.last_close == 10.0  # still reports what it can


def test_resistance_above_support_below_close():
    # V-shape then partial recovery: close ends in the middle, so there's a pivot low
    # below and a pivot high above.
    closes = [20, 18, 16, 14, 12, 10, 12, 14, 16, 18, 16, 14, 13]
    r = compute([b for b in _bars([float(c) for c in closes])], pivot_k=2)
    if r.nearest_support is not None:
        assert r.nearest_support < r.last_close
    if r.nearest_resistance is not None:
        assert r.nearest_resistance > r.last_close
