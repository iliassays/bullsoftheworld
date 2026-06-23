"""Tests for the 'key levels & what to watch' fact builder."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from bulls.analytics import build_levels, compute


@dataclass
class B:
    market: str
    code: str
    date: dt.date
    high: float
    low: float
    close: float
    volume: int


def _bars(closes: list[float]) -> list[B]:
    start = dt.date(2024, 1, 1)
    return [
        B("DSE", "GP", start + dt.timedelta(days=i), c + 1, c - 1, c, 1000)
        for i, c in enumerate(closes)
    ]


def test_rising_and_overbought():
    closes = [100 + i * 0.5 for i in range(250)]
    insight = build_levels(compute(_bars(closes)), closes)
    assert insight.pa_direction == "rising"
    assert insight.pa_change_pct is not None and insight.pa_change_pct > 0
    assert insight.rsi_zone == "overbought"  # monotonic up -> RSI 100


def test_flat_is_neutral():
    closes = [100.0] * 250
    insight = build_levels(compute(_bars(closes)), closes)
    assert insight.pa_direction == "flat"
    assert insight.rsi_zone == "neutral"


def test_falling():
    closes = [200 - i * 0.4 for i in range(250)]
    insight = build_levels(compute(_bars(closes)), closes)
    assert insight.pa_direction == "falling"
    assert insight.rsi_zone == "oversold"
