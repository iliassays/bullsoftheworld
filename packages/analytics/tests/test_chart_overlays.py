from __future__ import annotations

from dataclasses import dataclass

import pytest

from bulls.analytics.chart_overlays import (
    anchored_vwap,
    atr_contraction,
    average_true_range,
    exponential_moving_average,
)


@dataclass
class Bar:
    open: float
    high: float
    low: float
    close: float
    volume: float


def bar(price: float, *, spread: float = 1.0, volume: float = 100.0) -> Bar:
    return Bar(
        open=price,
        high=price + spread,
        low=price - spread,
        close=price,
        volume=volume,
    )


def test_ema_is_none_until_its_lookback_exists() -> None:
    values = exponential_moving_average([10, 11, 12, 13], period=3)

    assert values[0] is None
    assert values[1] is None
    assert values[2] == pytest.approx(11.0)  # seed = mean(10, 11, 12)
    assert values[3] == pytest.approx(12.0)  # (13 - 11) * 0.5 + 11


def test_ema_returns_all_none_when_history_is_shorter_than_the_period() -> None:
    assert exponential_moving_average([10, 11], period=5) == [None, None]


def test_anchored_vwap_starts_at_the_anchor_and_weights_by_volume() -> None:
    bars = [bar(10), bar(20, volume=300), bar(30, volume=100)]

    values = anchored_vwap(bars, anchor_index=1)

    assert values[0] is None
    # Typical price equals close for a symmetric bar, so anchor session is its own average.
    assert values[1] == pytest.approx(20.0)
    # (20*300 + 30*100) / 400
    assert values[2] == pytest.approx(22.5)


def test_anchored_vwap_ignores_zero_volume_sessions_without_resetting() -> None:
    bars = [bar(10, volume=100), bar(50, volume=0), bar(10, volume=100)]

    values = anchored_vwap(bars, anchor_index=0)

    assert values[1] == pytest.approx(10.0)
    assert values[2] == pytest.approx(10.0)


def test_anchored_vwap_out_of_range_anchor_yields_no_line() -> None:
    assert anchored_vwap([bar(10)], anchor_index=5) == [None]


def test_average_true_range_needs_a_prior_close() -> None:
    assert average_true_range([bar(10)], period=14) is None
    # Constant 2.0-wide bars at a flat price give a true range of exactly 2.0.
    assert average_true_range([bar(10) for _ in range(20)], period=14) == pytest.approx(2.0)


def test_atr_contraction_reports_a_negative_percentage_when_range_narrows() -> None:
    wide = [bar(10, spread=2.0) for _ in range(40)]
    narrow = [bar(10, spread=1.0) for _ in range(20)]

    current, prior, change = atr_contraction(wide + narrow, lookback=20)

    assert current == pytest.approx(2.0)
    assert prior == pytest.approx(4.0)
    assert change == pytest.approx(-50.0)


def test_atr_contraction_fails_closed_without_enough_history() -> None:
    assert atr_contraction([bar(10) for _ in range(5)]) == (None, None, None)
