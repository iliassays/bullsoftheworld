"""Corporate-action-safe bar views for analytics.

Providers may retain raw OHLC while supplying an adjusted close. Scaling the full candle by the
same factor preserves its shape and prevents splits/distributions from becoming false signals.
"""

from __future__ import annotations

import datetime as dt
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


def adjust_bars(bars: list[AdjustableBar]) -> list[AdjustedBar]:
    out: list[AdjustedBar] = []
    for bar in bars:
        adjusted_close = getattr(bar, "adjusted_close", None)
        factor = adjusted_close / bar.close if adjusted_close is not None and bar.close > 0 else 1.0
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
