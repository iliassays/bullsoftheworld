"""Tests for the cost observatory (Corwin-Schultz spread measurement, Phase 13.2)."""

from __future__ import annotations

import pytest

from bulls.analytics.cost_observatory import (
    corwin_schultz_spread,
    cost_tiers,
    estimate_spread,
)


def _flat_bars(n: int, price: float = 100.0) -> tuple[list[float], list[float]]:
    return [price] * n, [price] * n


def _ranged_bars(n: int, *, half_range: float, price: float = 100.0):
    # Every session spans [price - half_range, price + half_range]; wider range => wider spread.
    return [price + half_range] * n, [price - half_range] * n


# --- core estimator ------------------------------------------------------------------------


def test_spread_needs_two_sessions() -> None:
    assert corwin_schultz_spread([100.0], [99.0]) is None


def test_mismatched_lengths_raise() -> None:
    with pytest.raises(ValueError):
        corwin_schultz_spread([100.0, 101.0], [99.0])


def test_flat_prices_give_zero_spread() -> None:
    highs, lows = _flat_bars(30)
    assert corwin_schultz_spread(highs, lows) == 0.0


def test_wider_range_gives_wider_spread() -> None:
    narrow = corwin_schultz_spread(*_ranged_bars(30, half_range=0.2))
    wide = corwin_schultz_spread(*_ranged_bars(30, half_range=1.0))
    assert narrow is not None and wide is not None
    assert wide > narrow > 0.0


def test_spread_is_never_negative() -> None:
    # Alternating ranges produce noisy per-pair estimates; the floor keeps the average >= 0.
    highs = [101.0, 100.5, 102.0, 100.2, 101.5, 100.1] * 5
    lows = [99.0, 99.5, 98.0, 99.8, 98.5, 99.9] * 5
    spread = corwin_schultz_spread(highs, lows)
    assert spread is not None and spread >= 0.0


def test_inverted_or_nonpositive_bars_are_skipped_not_crashed() -> None:
    highs = [100.0, 101.0, 0.0, 102.0, 103.0]
    lows = [99.0, 100.0, 5.0, 101.0, 102.0]  # third pair inverted (low > high) and zero high
    # Should still return a number from the valid pairs rather than raising.
    assert corwin_schultz_spread(highs, lows) is not None


# --- per-name estimate wrapper -------------------------------------------------------------


def test_estimate_spread_reports_half_spread_and_support() -> None:
    highs, lows = _ranged_bars(60, half_range=0.5)
    estimate = estimate_spread("NVDA", highs, lows, minimum_observations=20)
    assert estimate is not None
    assert estimate.code == "NVDA"
    assert estimate.observations == 59  # 60 sessions -> 59 consecutive pairs
    assert estimate.half_spread_bps == pytest.approx(estimate.proportional_spread / 2 * 10_000)
    assert estimate.half_spread_bps > 0


def test_estimate_spread_refuses_thin_history() -> None:
    highs, lows = _ranged_bars(10, half_range=0.5)
    assert estimate_spread("THIN", highs, lows, minimum_observations=20) is None


# --- cost tiers ----------------------------------------------------------------------------


def test_cost_tiers_include_measured_plus_stress_floors() -> None:
    tiers = cost_tiers(measured_half_spread_bps=12.0, fee_bps=5.0)
    labels = [t.label for t in tiers]
    assert labels == ["measured", "stress_10bps", "stress_30bps", "stress_50bps"]
    measured = tiers[0]
    assert measured.measured is True
    assert measured.one_way_bps == pytest.approx(17.0)  # 12 half-spread + 5 fee
    assert [t.one_way_bps for t in tiers[1:]] == [10.0, 30.0, 50.0]
    assert all(t.measured is False for t in tiers[1:])


def test_cost_tiers_omit_measured_when_unmeasurable() -> None:
    tiers = cost_tiers(measured_half_spread_bps=None, fee_bps=5.0)
    assert [t.label for t in tiers] == ["stress_10bps", "stress_30bps", "stress_50bps"]
    assert all(t.measured is False for t in tiers)
