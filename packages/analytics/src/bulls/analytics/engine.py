"""Assemble the per-ticker analytics snapshot from daily bars.

`compute()` takes an ascending series of daily bars and returns an `AnalyticsResult` — a bundle of
computed, descriptive facts (trend, momentum, levels, volume). It states *what is*, never *what to
do*. The plain-Bangla explainer (Phase 2) phrases these numbers; the buy/sell decision is never
ours to make.

Input bars are duck-typed (`BarLike`): both `bulls.market_data.Bar` and the `DailyBar` ORM row
satisfy it, so this package depends on neither.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence
from typing import Protocol

from pydantic import BaseModel

from bulls.analytics.indicators import (
    atr,
    chaikin_money_flow,
    ema,
    momentum_12_1,
    realized_volatility,
    rsi,
    sma,
    swing_high_indices,
    swing_low_indices,
)

# Default lookback windows (trading days).
WEEK_52 = 252
PIVOT_K = 5


class BarLike(Protocol):
    market: str
    code: str
    date: dt.date
    high: float
    low: float
    close: float
    volume: int


class Level(BaseModel):
    """A price level with the date it was set on."""

    value: float
    date: dt.date


class AnalyticsResult(BaseModel):
    """Computed facts for one symbol, as of its latest bar. Descriptive only."""

    market: str
    code: str
    as_of_date: dt.date
    bars_used: int
    last_close: float

    # Trend
    sma_20: float | None = None
    sma_50: float | None = None
    sma_200: float | None = None
    ema_20: float | None = None
    above_sma_50: bool | None = None
    above_sma_200: bool | None = None

    # Momentum / volatility
    rsi_14: float | None = None
    atr_14: float | None = None
    mom_3_1: float | None = None  # 3-minus-1-month price momentum, %
    mom_6_1: float | None = None  # 6-minus-1-month price momentum, %
    mom_12_1: float | None = None  # 12-minus-1-month price momentum, %
    volatility: float | None = None  # annualised volatility of daily returns, %

    # Structure
    recent_swing_high: Level | None = None
    recent_swing_low: Level | None = None
    nearest_support: float | None = None
    nearest_resistance: float | None = None

    # Range
    week52_high: float | None = None
    week52_low: float | None = None
    pct_from_52w_high: float | None = None
    pct_from_52w_low: float | None = None

    # Volume
    last_volume: int
    avg_volume_20: float | None = None
    relative_volume: float | None = None
    cmf_20: float | None = None  # Chaikin Money Flow: >0 accumulation, <0 distribution


def _r(x: float | None, n: int = 2) -> float | None:
    return None if x is None else round(x, n)


def compute(
    bars: Sequence[BarLike], *, pivot_k: int = PIVOT_K, week52: int = WEEK_52
) -> AnalyticsResult:
    """Compute the analytics snapshot for one symbol from its daily bars (any order)."""
    if not bars:
        raise ValueError("compute() needs at least one bar")

    rows = sorted(bars, key=lambda b: b.date)
    closes = [b.close for b in rows]
    highs = [b.high for b in rows]
    lows = [b.low for b in rows]
    last = rows[-1]
    last_close = last.close

    sma_50 = sma(closes, 50)
    sma_200 = sma(closes, 200)

    # Support / resistance from confirmed pivots, relative to the latest close.
    sh_idx = swing_high_indices(highs, pivot_k)
    sl_idx = swing_low_indices(lows, pivot_k)
    resistances = sorted(highs[i] for i in sh_idx if highs[i] > last_close)
    supports = sorted((lows[i] for i in sl_idx if lows[i] < last_close), reverse=True)

    window = rows[-week52:]
    w_high = max(b.high for b in window)
    w_low = min(b.low for b in window)

    volumes = [float(b.volume) for b in rows]
    avg_vol_20 = sma(volumes, 20)

    return AnalyticsResult(
        market=last.market,
        code=last.code,
        as_of_date=last.date,
        bars_used=len(rows),
        last_close=_r(last_close),
        sma_20=_r(sma(closes, 20)),
        sma_50=_r(sma_50),
        sma_200=_r(sma_200),
        ema_20=_r(ema(closes, 20)),
        above_sma_50=None if sma_50 is None else last_close > sma_50,
        above_sma_200=None if sma_200 is None else last_close > sma_200,
        rsi_14=_r(rsi(closes, 14)),
        atr_14=_r(atr(highs, lows, closes, 14)),
        mom_3_1=_r(momentum_12_1(closes, lookback=63, skip=21)),
        mom_6_1=_r(momentum_12_1(closes, lookback=126, skip=21)),
        mom_12_1=_r(momentum_12_1(closes)),
        volatility=_r(realized_volatility(closes)),
        recent_swing_high=(
            Level(value=_r(highs[sh_idx[-1]]), date=rows[sh_idx[-1]].date) if sh_idx else None
        ),
        recent_swing_low=(
            Level(value=_r(lows[sl_idx[-1]]), date=rows[sl_idx[-1]].date) if sl_idx else None
        ),
        nearest_support=_r(supports[0]) if supports else None,
        nearest_resistance=_r(resistances[0]) if resistances else None,
        week52_high=_r(w_high),
        week52_low=_r(w_low),
        pct_from_52w_high=_r((last_close - w_high) / w_high * 100) if w_high else None,
        pct_from_52w_low=_r((last_close - w_low) / w_low * 100) if w_low else None,
        last_volume=last.volume,
        avg_volume_20=_r(avg_vol_20),
        relative_volume=_r(last.volume / avg_vol_20) if avg_vol_20 else None,
        cmf_20=_r(chaikin_money_flow(highs, lows, closes, volumes, 20), 3),
    )
