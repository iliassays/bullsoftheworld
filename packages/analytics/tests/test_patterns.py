"""Chart-pattern detection on synthetic OHLC series with known, deliberately-constructed shapes.

Each synthetic series uses explicit straight-line "sawtooth" bounces between two boundaries, with
touches spaced far enough apart to confirm as swing pivots (a smooth sine wave doesn't reliably do
this at pivot_k=5 — confirmed while building this: it under-produces confirmed pivots). This is
the same style of check used before shipping: manually verified against real DSE tickers separately
(not encoded here, since real-data behavior isn't deterministic test material).
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from bulls.analytics.patterns import detect_patterns


@dataclass
class B:
    """Minimal BarLike stand-in for tests."""

    date: dt.date
    high: float
    low: float
    close: float


def _sawtooth(resistance_fn, support_fn, n: int = 140, half: int = 10) -> list[B]:
    """Straight-line bounces between resistance_fn(i) and support_fn(i), alternating every `half`
    bars — clean, confirmable touches at both boundaries."""
    start = dt.date(2026, 1, 1)
    idx = list(range(0, n, half))
    closes: list[float] = []
    for k in range(len(idx) - 1):
        i0, i1 = idx[k], idx[k + 1]
        v0 = resistance_fn(i0) if k % 2 == 0 else support_fn(i0)
        v1 = resistance_fn(i1) if k % 2 == 1 else support_fn(i1)
        for i in range(i0, i1):
            frac = (i - i0) / (i1 - i0)
            closes.append(v0 + frac * (v1 - v0))
    closes.append(support_fn(idx[-1]) if (len(idx) - 1) % 2 == 0 else resistance_fn(idx[-1]))
    return [
        B(date=start + dt.timedelta(days=i), high=c + 0.3, low=c - 0.3, close=c)
        for i, c in enumerate(closes)
    ]


def _bars_from_closes(closes: list[float], noise: float = 0.5) -> list[B]:
    start = dt.date(2026, 1, 1)
    return [
        B(date=start + dt.timedelta(days=i), high=c + noise, low=c - noise, close=c)
        for i, c in enumerate(closes)
    ]


def test_ascending_triangle_detected():
    bars = _sawtooth(lambda i: 110.0, lambda i: 90 + i * 0.15)
    matches = detect_patterns(bars)
    assert len(matches) == 1
    assert matches[0].pattern_type == "ascending_triangle"
    assert matches[0].strength_score >= 90


def test_descending_triangle_detected():
    bars = _sawtooth(lambda i: 160 - i * 0.25, lambda i: 100.0)
    matches = detect_patterns(bars)
    assert len(matches) == 1
    assert matches[0].pattern_type == "descending_triangle"


def test_channel_up_detected():
    bars = _sawtooth(lambda i: 120 + i * 0.25, lambda i: 100 + i * 0.25)
    matches = detect_patterns(bars)
    assert len(matches) == 1
    assert matches[0].pattern_type == "channel_up"


def test_channel_down_detected():
    bars = _sawtooth(lambda i: 160 - i * 0.25, lambda i: 140 - i * 0.25)
    matches = detect_patterns(bars)
    assert len(matches) == 1
    assert matches[0].pattern_type == "channel_down"


def test_channel_horizontal_detected():
    bars = _sawtooth(lambda i: 120.0, lambda i: 100.0)
    matches = detect_patterns(bars)
    assert len(matches) == 1
    assert matches[0].pattern_type == "channel_horizontal"


def test_double_top_detected_with_neckline_and_forming_status():
    closes = (
        [80 + i * 0.5 for i in range(30)]
        + [95 + i * 0.8 for i in range(31)]  # ramp to first peak ~120
        + [120 - i * 0.9 for i in range(23)]  # pull back to the neckline ~100
        + [100 + i * 0.9 for i in range(23)]  # ramp to a comparable second peak ~121
        + [121 - i * 1.0 for i in range(10)]  # starts falling, hasn't broken the neckline yet
    )
    matches = detect_patterns(_bars_from_closes(closes))
    assert len(matches) == 1
    m = matches[0]
    assert m.pattern_type == "double_top"
    assert m.status == "forming"
    assert m.key_levels and 95 < m.key_levels[0] < 105


def test_double_bottom_mirrors_double_top():
    closes = (
        [140 - i * 0.5 for i in range(30)]
        + [125 - i * 0.8 for i in range(31)]  # drop to first trough ~100
        + [100 + i * 0.9 for i in range(23)]  # bounce to the neckline ~120
        + [120 - i * 0.9 for i in range(23)]  # drop to a comparable second trough ~99
        + [99 + i * 1.0 for i in range(10)]  # starts rising, hasn't broken the neckline yet
    )
    matches = detect_patterns(_bars_from_closes(closes))
    assert len(matches) == 1
    assert matches[0].pattern_type == "double_bottom"
    assert matches[0].status == "forming"


def test_confirmed_breakout_status_when_close_clears_the_boundary():
    # Same ascending triangle, but the final stretch closes well above the flat resistance.
    bars = _sawtooth(lambda i: 110.0, lambda i: 90 + i * 0.15)
    bars = bars + [
        B(date=bars[-1].date + dt.timedelta(days=i + 1), high=115 + i, low=113 + i, close=114 + i)
        for i in range(5)
    ]
    matches = detect_patterns(bars)
    assert len(matches) == 1
    assert matches[0].status == "confirmed_breakout_up"
    assert matches[0].breakout_date is not None


def test_too_short_history_returns_no_match():
    bars = _sawtooth(lambda i: 110.0, lambda i: 90 + i * 0.15, n=25, half=5)
    assert detect_patterns(bars) == []


def test_single_two_point_line_is_not_enough_evidence():
    """Regression: a 2-point trendline always has zero residual (any two points are perfectly
    collinear), which used to falsely max out the fit-quality score for an arbitrary pair of
    pivots. A series with only 2 confirmed swings per side must not pass the strength gate."""
    bars = _sawtooth(lambda i: 110.0, lambda i: 90 + i * 0.15, n=45, half=10)
    matches = detect_patterns(bars)
    assert matches == []
