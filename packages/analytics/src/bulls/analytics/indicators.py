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

import math
import statistics
from collections.abc import Sequence

_TRADING_DAYS = 252  # ~1 year of sessions


def index_change_pct(level: float | None, points: float | None) -> float | None:
    """DSE's market summary reports the index change in POINTS; convert to the day's % change.

    This is THE converter — use it everywhere MarketSummary.dsex_change/ds30_change is shown as
    a percent. Three private copies used to exist and the composers without one printed the raw
    points with a '%' sign (the "DSEX fell 19.0%" incident). Returns None for anything
    implausible for an index in a day (>20%) — better blank than misleading.
    """
    if level is None or points is None:
        return None
    prev = level - points
    if not prev:
        return None
    pct = points / prev * 100
    return pct if abs(pct) <= 20 else None


def momentum_12_1(closes: Sequence[float], *, lookback: int = 252, skip: int = 21) -> float | None:
    """12-minus-1-month price momentum (%): return from `lookback` days ago to `skip` days ago.

    Skipping the most recent ~month deliberately excludes short-term reversal — last month's
    winners tend to mean-revert, so quant momentum is measured 12m..1m, not 12m..today.
    """
    if len(closes) < lookback + 1:
        return None
    old, recent = closes[-1 - lookback], closes[-1 - skip]
    if not old:
        return None
    return (recent / old - 1) * 100


def realized_volatility(closes: Sequence[float], *, period: int = 252) -> float | None:
    """Annualised volatility (%) of daily returns over the last `period` sessions."""
    window = closes[-(period + 1) :] if len(closes) > period + 1 else closes
    rets = [window[i] / window[i - 1] - 1 for i in range(1, len(window)) if window[i - 1]]
    if len(rets) < 2:
        return None
    return statistics.pstdev(rets) * math.sqrt(_TRADING_DAYS) * 100


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


def chaikin_money_flow(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    volumes: Sequence[float],
    period: int = 20,
) -> float | None:
    """Chaikin Money Flow over `period` bars — bounded ~[-1, 1].

    Positive = volume flowing in (accumulation); negative = flowing out (distribution). Bounded
    and volume-normalized, so it's comparable across stocks (good for ranking a screen).
    """
    if period <= 0 or len(closes) < period:
        return None
    mfv_sum = 0.0
    vol_sum = 0.0
    for i in range(len(closes) - period, len(closes)):
        rng = highs[i] - lows[i]
        mfm = 0.0 if rng == 0 else ((closes[i] - lows[i]) - (highs[i] - closes[i])) / rng
        mfv_sum += mfm * volumes[i]
        vol_sum += volumes[i]
    if vol_sum == 0:
        return None
    return mfv_sum / vol_sum


def on_balance_volume(closes: Sequence[float], volumes: Sequence[float]) -> list[float]:
    """On-Balance Volume — a running total that adds the day's volume when price closes up and
    subtracts it when price closes down. Rising OBV = buying pressure (volume leading price)."""
    if len(closes) != len(volumes) or len(closes) < 2:
        return []
    obv = [0.0]
    for i in range(1, len(closes)):
        if closes[i] > closes[i - 1]:
            obv.append(obv[-1] + volumes[i])
        elif closes[i] < closes[i - 1]:
            obv.append(obv[-1] - volumes[i])
        else:
            obv.append(obv[-1])
    return obv


def linreg(xs: Sequence[float], ys: Sequence[float]) -> tuple[float, float] | None:
    """Least-squares line y = slope*x + intercept through (xs, ys).

    None for degenerate input (fewer than 2 points, or all xs identical — a vertical "line" has no
    slope). General-purpose: `obv_slope` uses it with evenly-spaced xs; the chart-pattern trendline
    fit (patterns.py) uses it with actual pivot bar indices, which are NOT evenly spaced.
    """
    n = len(xs)
    if n < 2 or n != len(ys):
        return None
    xbar = statistics.fmean(xs)
    ybar = statistics.fmean(ys)
    den = sum((x - xbar) ** 2 for x in xs)
    if den == 0:
        return None
    num = sum((x - xbar) * (y - ybar) for x, y in zip(xs, ys, strict=True))
    slope = num / den
    return slope, ybar - slope * xbar


def obv_slope(
    closes: Sequence[float], volumes: Sequence[float], *, period: int = 20
) -> float | None:
    """Normalized trend of On-Balance Volume over `period` sessions.

    Returns OBV's average per-session change expressed in multiples of average daily volume, so it
    is comparable across stocks: > 0 means volume is accumulating (buying pressure building, often
    ahead of price); < 0 the reverse. e.g. ~+0.2 ≈ OBV rises by a fifth of a day's volume per day.
    """
    if period < 2 or len(closes) < period + 1:
        return None
    obv = on_balance_volume(closes, volumes)
    window = obv[-period:]
    fit = linreg(range(len(window)), window)
    avg_vol = statistics.fmean(volumes[-period:])
    if fit is None or not avg_vol:
        return None
    slope, _ = fit
    return slope / avg_vol


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
