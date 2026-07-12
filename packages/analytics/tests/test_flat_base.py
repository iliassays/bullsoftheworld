from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, replace

from bulls.analytics.flat_base import DEFAULT_FLAT_BASE_CONFIG, detect_flat_base_at
from bulls.analytics.patterns import detect_patterns


@dataclass(frozen=True)
class Bar:
    date: dt.date
    open: float
    high: float
    low: float
    close: float
    volume: int


def _history(current_close: float, current_volume: int) -> list[Bar]:
    start = dt.date(2025, 1, 1)
    rows: list[Bar] = []
    for i in range(60):
        close = 70 + 0.5 * i
        rows.append(
            Bar(start + dt.timedelta(days=i), close, close + 0.8, close - 0.8, close, 900_000)
        )
    base_closes = [
        100.0,
        101.5,
        102.5,
        101.0,
        103.0,
        102.0,
        100.5,
        101.8,
        102.8,
        101.2,
        102.2,
        101.6,
        102.7,
        101.9,
        102.4,
    ]
    for offset, close in enumerate(base_closes, start=60):
        volume = 900_000 if offset < 70 else 650_000
        rows.append(
            Bar(
                start + dt.timedelta(days=offset),
                close,
                close + 0.5,
                close - 0.5,
                close,
                volume,
            )
        )
    i = len(rows)
    rows.append(
        Bar(
            start + dt.timedelta(days=i),
            current_close - 1,
            current_close + 0.5,
            current_close - 2,
            current_close,
            current_volume,
        )
    )
    return rows


def test_flat_base_surfaces_before_breakout_without_future_data() -> None:
    forming = detect_flat_base_at(_history(102.5, 600_000))

    assert forming is not None
    assert forming.status == "forming"
    assert forming.resistance == 103.5
    assert forming.depth < 0.10
    assert forming.volume_ratio < 1


def test_two_times_volume_confirms_flat_base_breakout() -> None:
    breakout = detect_flat_base_at(_history(105.0, 2_500_000))

    assert breakout is not None
    assert breakout.status == "confirmed_breakout_up"
    assert breakout.volume_ratio >= 2
    assert breakout.strength_score > 70


def test_price_break_without_volume_confirmation_is_not_promoted() -> None:
    weak = detect_flat_base_at(_history(105.0, 900_000))

    assert weak is None


def test_shared_pattern_engine_emits_flat_base_payload() -> None:
    matches = detect_patterns(_history(105.0, 2_500_000))

    assert len(matches) == 1
    assert matches[0].pattern_type == "high_volume_flat_base"
    assert matches[0].metrics["volume_ratio"] >= 2
    assert matches[0].resistance_line is not None


def test_detector_thresholds_are_configurable_for_research_only() -> None:
    too_strict = replace(DEFAULT_FLAT_BASE_CONFIG, max_depth=0.01)

    assert detect_flat_base_at(_history(105.0, 2_500_000), config=too_strict) is None
