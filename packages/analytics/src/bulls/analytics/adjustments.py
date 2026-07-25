"""Corporate-action-safe bar views for analytics.

Providers may retain raw OHLC while supplying an adjusted close. Scaling the full candle by the
same factor preserves its shape and prevents splits/distributions from becoming false signals.
"""

from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass
from typing import Protocol


class AdjustableBar(Protocol):
    market: str
    code: str
    date: dt.date
    open: float
    high: float
    low: float
    close: float
    volume: int
    adjusted_close: float | None


@dataclass(frozen=True)
class AdjustedBar:
    market: str
    code: str
    date: dt.date
    open: float
    high: float
    low: float
    close: float
    volume: int


def adjustment_factor(close: float, adjusted_close: float | None) -> float | None:
    """Return a usable corporate-action factor, or ``None`` for a quarantined observation."""

    if not math.isfinite(close) or close <= 0:
        return None
    if adjusted_close is None:
        return 1.0
    if not math.isfinite(adjusted_close) or adjusted_close <= 0:
        return None
    factor = adjusted_close / close
    return factor if math.isfinite(factor) and factor > 0 else None


def adjust_bars(bars: list[AdjustableBar]) -> list[AdjustedBar]:
    out: list[AdjustedBar] = []
    for bar in bars:
        adjusted_close = getattr(bar, "adjusted_close", None)
        factor = adjustment_factor(bar.close, adjusted_close)
        if factor is None:
            continue
        out.append(
            AdjustedBar(
                market=bar.market,
                code=bar.code,
                date=bar.date,
                open=bar.open * factor,
                high=bar.high * factor,
                low=bar.low * factor,
                close=bar.close * factor,
                volume=bar.volume,
            )
        )
    return out
