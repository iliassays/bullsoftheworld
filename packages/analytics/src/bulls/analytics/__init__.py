"""bulls.analytics — deterministic technical-analysis engine.

Computes descriptive facts (trend, momentum, levels, volume) over daily bars. No AI, no I/O.
"""

from bulls.analytics.engine import AnalyticsResult, BarLike, Level, compute
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
from bulls.analytics.plain_read import PlainRead, ReadPoint, build_plain_read
from bulls.analytics.scenarios import LevelsInsight, build_levels
from bulls.analytics.valuation import ValuationResult, compute_valuation

__all__ = [
    "AnalyticsResult",
    "BarLike",
    "Level",
    "LevelsInsight",
    "PlainRead",
    "ReadPoint",
    "ValuationResult",
    "atr",
    "build_levels",
    "build_plain_read",
    "chaikin_money_flow",
    "compute",
    "compute_valuation",
    "ema",
    "momentum_12_1",
    "realized_volatility",
    "rsi",
    "sma",
    "swing_high_indices",
    "swing_low_indices",
]
