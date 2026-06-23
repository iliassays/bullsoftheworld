"""Structured 'key levels & what to watch' facts derived from an analytics snapshot.

This produces the *facts and conditions* a trader can watch (resistance/support, whether volume
would confirm a breakout, the RSI zone, recent price action) — never a prediction or an action.
The API renders these into localized, templated sentences; keeping the rendering templated (not an
LLM) guarantees the prose can't drift into a forecast.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal

from pydantic import BaseModel

from bulls.analytics.engine import AnalyticsResult

Direction = Literal["rising", "falling", "flat"]
RsiZone = Literal["overbought", "oversold", "neutral"]


class LevelsInsight(BaseModel):
    """Descriptive facts for the 'what to watch' section. No predictions, no advice."""

    last_close: float
    # recent price action
    pa_direction: Direction
    pa_sessions: int
    pa_change_pct: float | None = None
    recent_swing_high: float | None = None
    recent_swing_low: float | None = None
    # levels to watch
    resistance: float | None = None
    support: float | None = None
    volume_confirms: bool | None = None  # is the latest volume >= its 20-day average?
    relative_volume: float | None = None
    rsi: float | None = None
    rsi_zone: RsiZone | None = None


def build_levels(
    result: AnalyticsResult, recent_closes: Sequence[float], *, lookback: int = 5
) -> LevelsInsight:
    """Derive the watch-list facts from the analytics snapshot + recent closes."""
    closes = list(recent_closes)
    change: float | None = None
    direction: Direction = "flat"
    if len(closes) > lookback:
        prev = closes[-1 - lookback]
        if prev:
            change = (closes[-1] - prev) / prev * 100
            direction = "rising" if change > 1 else "falling" if change < -1 else "flat"

    rsi = result.rsi_14
    rsi_zone: RsiZone | None = None
    if rsi is not None:
        # zone from the rounded value shown, so "70" never reads as "neutral"
        r = round(rsi)
        rsi_zone = "overbought" if r >= 70 else "oversold" if r <= 30 else "neutral"

    return LevelsInsight(
        last_close=result.last_close,
        pa_direction=direction,
        pa_sessions=lookback,
        pa_change_pct=round(change, 2) if change is not None else None,
        recent_swing_high=result.recent_swing_high.value if result.recent_swing_high else None,
        recent_swing_low=result.recent_swing_low.value if result.recent_swing_low else None,
        resistance=result.nearest_resistance,
        support=result.nearest_support,
        volume_confirms=(
            result.relative_volume >= 1.0 if result.relative_volume is not None else None
        ),
        relative_volume=result.relative_volume,
        rsi=rsi,
        rsi_zone=rsi_zone,
    )
