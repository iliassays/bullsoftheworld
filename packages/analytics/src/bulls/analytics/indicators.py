"""Pure technical-analysis primitives.

Every function here is a deterministic computation over a sequence of numbers — no I/O, no ORM,
no AI. These are *facts*, which is the whole point: the engine assembles them into a snapshot we
can display and explain without ever issuing a recommendation.

Conventions:
- Inputs are ascending-by-time sequences (oldest first, newest last).
- A function returns `None` when there isn't enough history to compute it, rather than raising —
  a freshly listed stock should still produce a partial snapshot.
"""

from __future__ import annotations

from collections.abc import Sequence


def sma(values: Sequence[float], period: int) -> float | None:
    """Simple moving average of the last `period` values."""
    if period <= 0 or len(values) < period:
        return None
    return sum(values[-period:]) / period


def ema(values: Sequence[float], period: int) -> float | None:
    """Exponential moving average, seeded with the SMA of the first `period` values."""
    if period <= 0 or len(values) < period:
        return None
    k = 2 / (period + 1)
    e = sum(values[:period]) / period
    for v in values[period:]:
        e = v * k + e * (1 - k)
    return e


def rsi(closes: Sequence[float], period: int = 14) -> float | None:
    """Wilder's Relative Strength Index over `period` closes.

    Returns 0..100. A flat series (no moves) is neutral 50; pure up = 100; pure down = 0.
    """
    if period <= 0 or len(closes) < period + 1:
        return None
    gains: list[float] = []
    losses: list[float] = []
    for i in range(1, len(closes)):
        delta = closes[i] - closes[i - 1]
        gains.append(max(delta, 0.0))
        losses.append(max(-delta, 0.0))

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

    if avg_loss == 0:
        return 50.0 if avg_gain == 0 else 100.0
    rs = avg_gain / avg_loss
    return 100 - 100 / (1 + rs)


def _true_ranges(
    highs: Sequence[float], lows: Sequence[float], closes: Sequence[float]
) -> list[float]:
    trs: list[float] = []
    for i in range(1, len(closes)):
        trs.append(
            max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i - 1]),
                abs(lows[i] - closes[i - 1]),
            )
        )
    return trs


def atr(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    period: int = 14,
) -> float | None:
    """Average True Range (Wilder-smoothed) — a volatility measure, not a direction."""
    if period <= 0 or len(closes) < period + 1:
        return None
    trs = _true_ranges(highs, lows, closes)
    value = sum(trs[:period]) / period
    for i in range(period, len(trs)):
        value = (value * (period - 1) + trs[i]) / period
    return value


def swing_high_indices(highs: Sequence[float], k: int = 5) -> list[int]:
    """Indices of confirmed swing highs: a bar whose high is the max of [i-k, i+k].

    A pivot needs `k` bars on each side to confirm, so the last `k` bars can never be pivots.
    """
    out: list[int] = []
    for i in range(k, len(highs) - k):
        if highs[i] == max(highs[i - k : i + k + 1]):
            out.append(i)
    return out


def swing_low_indices(lows: Sequence[float], k: int = 5) -> list[int]:
    """Indices of confirmed swing lows: a bar whose low is the min of [i-k, i+k]."""
    out: list[int] = []
    for i in range(k, len(lows) - k):
        if lows[i] == min(lows[i - k : i + k + 1]):
            out.append(i)
    return out
