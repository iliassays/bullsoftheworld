"""Deterministic chart overlays computed from completed daily bars.

These are presentation overlays for research charts, not signals. They live here so the API and
the squeeze evaluator share one implementation and one set of honesty rules:

* ``anchored_vwap`` is built from *daily* typical price x volume. A true VWAP is an intraday,
  session-traded measure and Atlas has no meaningful intraday history, so every surface that
  renders this must label it "anchored VWAP (daily basis)" and never plain "VWAP".
* Overlays return ``None`` for sessions with insufficient lookback rather than seeding a value,
  so a chart never draws an average that had no data behind it.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol


class OhlcvBar(Protocol):
    open: float
    high: float
    low: float
    close: float
    volume: float


def exponential_moving_average(closes: Sequence[float], period: int) -> list[float | None]:
    """EMA seeded with the simple average of the first ``period`` closes.

    The first ``period - 1`` sessions are ``None``: an EMA needs its lookback before it means
    anything, and drawing a line from session one would imply history that does not exist.
    """

    if period <= 0:
        raise ValueError("period must be positive")
    output: list[float | None] = [None] * len(closes)
    if len(closes) < period:
        return output
    multiplier = 2 / (period + 1)
    average = sum(closes[:period]) / period
    output[period - 1] = average
    for index in range(period, len(closes)):
        average = (closes[index] - average) * multiplier + average
        output[index] = average
    return output


def anchored_vwap(bars: Sequence[OhlcvBar], *, anchor_index: int) -> list[float | None]:
    """Cumulative typical-price VWAP anchored at ``anchor_index``.

    Typical price is (high + low + close) / 3, the standard daily proxy. Sessions before the
    anchor are ``None``. Zero-volume sessions contribute nothing but do not reset the anchor.
    """

    output: list[float | None] = [None] * len(bars)
    if not 0 <= anchor_index < len(bars):
        return output
    cumulative_value = 0.0
    cumulative_volume = 0.0
    for index in range(anchor_index, len(bars)):
        bar = bars[index]
        typical = (bar.high + bar.low + bar.close) / 3
        cumulative_value += typical * bar.volume
        cumulative_volume += bar.volume
        output[index] = cumulative_value / cumulative_volume if cumulative_volume > 0 else None
    return output


def average_true_range(bars: Sequence[OhlcvBar], period: int = 14) -> float | None:
    """Simple-average true range over the last ``period`` completed sessions."""

    if len(bars) < period + 1:
        return None
    true_ranges = [
        max(
            current.high - current.low,
            abs(current.high - previous.close),
            abs(current.low - previous.close),
        )
        for previous, current in zip(bars[-period - 1 : -1], bars[-period:], strict=True)
    ]
    return sum(true_ranges) / period


def atr_contraction(
    bars: Sequence[OhlcvBar], *, period: int = 14, lookback: int = 20
) -> tuple[float | None, float | None, float | None]:
    """Return (current ATR, ATR ``lookback`` sessions ago, percentage change).

    This is the measurable form of the compression claim: a negative percentage means range
    has contracted. Returns ``None`` values when either window lacks history.
    """

    current = average_true_range(bars, period)
    prior = average_true_range(bars[:-lookback], period) if len(bars) > lookback + period else None
    if current is None or prior is None or prior <= 0:
        return current, prior, None
    return current, prior, (current / prior - 1) * 100
