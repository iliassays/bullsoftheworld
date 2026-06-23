"""bulls.analytics — deterministic technical-analysis engine.

Computes descriptive facts (trend, momentum, levels, volume) over daily bars. No AI, no I/O.
"""

from bulls.analytics.engine import AnalyticsResult, BarLike, Level, compute
from bulls.analytics.indicators import (
    atr,
    chaikin_money_flow,
    ema,
    rsi,
    sma,
    swing_high_indices,
    swing_low_indices,
)
from bulls.analytics.scenarios import LevelsInsight, build_levels

__all__ = [
    "AnalyticsResult",
    "BarLike",
    "Level",
    "LevelsInsight",
    "atr",
    "build_levels",
    "chaikin_money_flow",
    "compute",
    "ema",
    "rsi",
    "sma",
    "swing_high_indices",
    "swing_low_indices",
]
