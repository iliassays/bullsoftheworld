"""bulls.analytics — deterministic technical-analysis engine.

Computes descriptive facts (trend, momentum, levels, volume) over daily bars. No AI, no I/O.
"""

from bulls.analytics.adjustments import AdjustedBar, adjust_bars
from bulls.analytics.agent_performance import AgentPerformance, calculate_agent_performance
from bulls.analytics.circuit import AT_LIMIT_TOLERANCE_PP, at_circuit, circuit_band
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
from bulls.analytics.investor_lens import (
    InvestorLens,
    InvestorLensResponse,
    buffett_quality_score,
    build_investor_lens,
    dividend_score,
    graham_score,
    risk_score,
    smart_money_score,
    technical_score,
)
from bulls.analytics.mood import MoodComponent, MoodIndex, build_mood
from bulls.analytics.patterns import PatternMatch, PatternType, detect_patterns
from bulls.analytics.plain_read import PlainRead, ReadPoint, build_plain_read
from bulls.analytics.scenarios import LevelsInsight, build_levels
from bulls.analytics.scorecard import (
    Dimension,
    RedFlag,
    RedFlags,
    Scorecard,
    build_red_flags,
    build_scorecard,
)
from bulls.analytics.strategies import (
    STRATEGIES,
    Snapshot,
    StrategySpec,
    entry_reason,
    exit_reason,
    rank_entries,
    universe_ok,
)
from bulls.analytics.valuation import ValuationResult, compute_valuation

__all__ = [
    "AT_LIMIT_TOLERANCE_PP",
    "STRATEGIES",
    "AdjustedBar",
    "AgentPerformance",
    "AnalyticsResult",
    "BarLike",
    "Dimension",
    "InvestorLens",
    "InvestorLensResponse",
    "Level",
    "LevelsInsight",
    "MoodComponent",
    "MoodIndex",
    "PatternMatch",
    "PatternType",
    "PlainRead",
    "ReadPoint",
    "RedFlag",
    "RedFlags",
    "Scorecard",
    "Snapshot",
    "StrategySpec",
    "ValuationResult",
    "adjust_bars",
    "at_circuit",
    "atr",
    "buffett_quality_score",
    "build_investor_lens",
    "build_levels",
    "build_mood",
    "build_plain_read",
    "build_red_flags",
    "build_scorecard",
    "calculate_agent_performance",
    "chaikin_money_flow",
    "circuit_band",
    "compute",
    "compute_valuation",
    "detect_patterns",
    "dividend_score",
    "ema",
    "entry_reason",
    "exit_reason",
    "graham_score",
    "momentum_12_1",
    "rank_entries",
    "realized_volatility",
    "risk_score",
    "rsi",
    "sma",
    "smart_money_score",
    "swing_high_indices",
    "swing_low_indices",
    "technical_score",
    "universe_ok",
]
