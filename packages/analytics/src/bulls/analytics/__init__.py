"""bulls.analytics — deterministic technical-analysis engine.

Computes descriptive facts (trend, momentum, levels, volume) over daily bars. No AI, no I/O.
"""

from bulls.analytics.engine import AnalyticsResult, BarLike, Level, compute
from bulls.analytics.indicators import (
    atr,
    ema,
    rsi,
    sma,
    swing_high_indices,
    swing_low_indices,
)

__all__ = [
    "AnalyticsResult",
    "BarLike",
    "Level",
    "atr",
    "compute",
    "ema",
    "rsi",
    "sma",
    "swing_high_indices",
    "swing_low_indices",
]
