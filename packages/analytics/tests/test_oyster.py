from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass

from bulls.analytics.oyster import METHODOLOGY_VERSION, detect_oyster_at


@dataclass(frozen=True)
class B:
    date: dt.date
    open: float
    high: float
    low: float
    close: float
    volume: float


def _decline_then_retest(*, activate: bool = False, break_support: bool = False) -> list[B]:
    start = dt.date(2025, 1, 1)
    bars: list[B] = []
    for index in range(84):
        center = 105.0 - 0.55 * index
        close = center + 4.0 * math.cos(2.0 * math.pi * index / 12.0)
        bars.append(
            B(
                date=start + dt.timedelta(days=index),
                open=close - 0.2,
                high=close + 0.8,
                low=close - 0.8,
                close=close,
                volume=1_000_000,
            )
        )

    closes = [64.0, 62.5, 61.8, 62.4, 62.8]
    volumes = [1_100_000, 650_000, 600_000, 550_000, 600_000]
    if break_support:
        closes[-1] = 50.0
    if activate:
        closes.append(68.0)
        volumes.append(2_000_000)
    for offset, (close, volume) in enumerate(zip(closes, volumes, strict=True), start=len(bars)):
        bars.append(
            B(
                date=start + dt.timedelta(days=offset),
                open=close - 0.2,
                high=close + 0.7,
                low=close - 0.7,
                close=close,
                volume=volume,
            )
        )
    return bars


def test_detects_controlled_retest_after_falling_resistance_break():
    setup = detect_oyster_at(_decline_then_retest())

    assert setup is not None
    assert setup.phase == "retesting"
    assert setup.sessions_since_cross == 4
    assert setup.decline_from_anchor >= 0.30
    assert setup.retest_volume_ratio < 1.0
    assert setup.distance_to_activation > 0
    assert setup.methodology_version == METHODOLOGY_VERSION


def test_activation_requires_later_range_break_with_volume():
    setup = detect_oyster_at(_decline_then_retest(activate=True))

    assert setup is not None
    assert setup.phase == "activated"
    assert setup.activation_date == setup.as_of_date
    assert setup.activation_volume_ratio is not None
    assert setup.activation_volume_ratio >= 1.5


def test_broken_retest_is_rejected():
    assert detect_oyster_at(_decline_then_retest(break_support=True)) is None


def test_prefix_result_does_not_use_future_bars():
    prefix = _decline_then_retest()
    expected = detect_oyster_at(prefix)
    future = prefix + [
        B(
            date=prefix[-1].date + dt.timedelta(days=index + 1),
            open=80 + index,
            high=82 + index,
            low=79 + index,
            close=81 + index,
            volume=4_000_000,
        )
        for index in range(5)
    ]

    actual = detect_oyster_at(future, as_of_index=len(prefix) - 1)

    assert actual == expected


def test_short_or_invalid_history_is_rejected():
    bars = _decline_then_retest()
    assert detect_oyster_at(bars[:30]) is None
    invalid = [*bars]
    invalid[10] = B(
        date=invalid[10].date,
        open=0,
        high=1,
        low=0,
        close=0,
        volume=1,
    )
    assert detect_oyster_at(invalid) is None
