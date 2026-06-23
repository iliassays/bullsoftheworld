"""Unit tests for the TA primitives — hand-computable, deterministic, no I/O."""

from __future__ import annotations

from bulls.analytics.indicators import (
    atr,
    chaikin_money_flow,
    ema,
    rsi,
    sma,
    swing_high_indices,
    swing_low_indices,
)


def test_sma_basic():
    values = [float(i) for i in range(1, 11)]  # 1..10
    assert sma(values, 5) == 8.0  # (6+7+8+9+10)/5
    assert sma(values, 10) == 5.5
    assert sma(values, 11) is None  # not enough history


def test_ema_constant_series_is_constant():
    assert ema([5.0] * 20, 10) == 5.0
    assert ema([5.0] * 5, 10) is None


def test_rsi_extremes_and_flat():
    assert rsi([float(i) for i in range(1, 21)], 14) == 100.0  # strictly up
    assert rsi([float(i) for i in range(20, 0, -1)], 14) == 0.0  # strictly down
    assert rsi([10.0] * 20, 14) == 50.0  # flat -> neutral
    assert rsi([1.0, 2.0], 14) is None  # not enough history


def test_atr_constant_range():
    # Every bar: high-low = 2, close flat -> true range = 2 each -> ATR = 2.
    highs = [11.0] * 20
    lows = [9.0] * 20
    closes = [10.0] * 20
    assert atr(highs, lows, closes, 14) == 2.0


def test_chaikin_money_flow_extremes():
    n = 20
    # close always at the high -> money flow multiplier +1 -> CMF = +1 (pure accumulation)
    assert chaikin_money_flow([11.0] * n, [9.0] * n, [11.0] * n, [100.0] * n, n) == 1.0
    # close always at the low -> CMF = -1 (pure distribution)
    assert chaikin_money_flow([11.0] * n, [9.0] * n, [9.0] * n, [100.0] * n, n) == -1.0
    # not enough history
    assert chaikin_money_flow([11.0] * 5, [9.0] * 5, [10.0] * 5, [100.0] * 5, 20) is None


def test_swing_high_indices():
    highs = [1.0, 2.0, 3.0, 2.0, 1.0, 2.0, 5.0, 2.0, 1.0]
    # k=2: peak at index 2 (value 3) and index 6 (value 5); last 2 bars can't confirm.
    assert swing_high_indices(highs, k=2) == [2, 6]


def test_swing_low_indices():
    lows = [5.0, 4.0, 1.0, 4.0, 5.0, 4.0, 0.0, 4.0, 5.0]
    assert swing_low_indices(lows, k=2) == [2, 6]
