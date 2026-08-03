"""Causal daily approximation of the privately named "Oyster" chart setup.

The supplied source deck describes an intraday falling-resistance break followed by a short,
controlled drift/retest before a possible expansion.  Atlas stores complete daily bars for both
markets, not the two/four-hour bars shown in the deck, so this module deliberately implements a
daily research approximation.  It does not predict that a move is coming and it never creates an
order.

The rule is phase-based:

1. a material decline produces at least three coherent lower swing highs;
2. a completed close crosses the fitted resistance line;
3. two to twelve completed sessions retest that break on quieter volume without losing the line;
4. an optional activation requires a later range break with renewed participation.

All calculations use only the prefix ending at ``as_of_index``.  The same function is therefore
safe for point-in-time research and current nightly classification.
"""

from __future__ import annotations

import datetime as dt
import math
import statistics
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal, Protocol

from bulls.analytics.indicators import atr, linreg, swing_high_indices

METHODOLOGY_VERSION = "oyster-daily-v1"


class OysterBarLike(Protocol):
    date: dt.date
    open: float
    high: float
    low: float
    close: float
    volume: float


OysterPhase = Literal["retesting", "activated"]


@dataclass(frozen=True)
class OysterConfig:
    lookback_sessions: int = 120
    pivot_radius: int = 3
    minimum_pivots: int = 3
    maximum_pivots: int = 6
    maximum_cross_age: int = 12
    minimum_retest_sessions: int = 2
    maximum_last_pivot_age: int = 18
    minimum_decline: float = 0.30
    minimum_resistance_decline: float = 0.10
    maximum_fit_residual_atr: float = 1.25
    cross_buffer_atr: float = 0.15
    hold_buffer_atr: float = 0.75
    maximum_cross_return: float = 0.25
    maximum_retest_drawdown: float = 0.30
    maximum_pre_activation_extension: float = 0.25
    maximum_retest_volume_ratio: float = 1.20
    activation_buffer_atr: float = 0.10
    activation_volume_ratio: float = 1.50
    baseline_volume_sessions: int = 20


DEFAULT_OYSTER_CONFIG = OysterConfig()


@dataclass(frozen=True)
class OysterSetup:
    as_of_date: dt.date
    phase: OysterPhase
    trend_start_date: dt.date
    cross_date: dt.date
    activation_date: dt.date | None
    resistance_start: float
    resistance_at_cross: float
    resistance_now: float
    retest_support: float
    activation_level: float
    sessions_since_cross: int
    decline_from_anchor: float
    resistance_decline: float
    fit_residual_atr: float
    retest_drawdown: float
    retest_volume_ratio: float
    activation_volume_ratio: float | None
    distance_to_activation: float
    strength_score: float
    pivot_indices: tuple[int, ...]
    methodology_version: str = METHODOLOGY_VERSION


@dataclass(frozen=True)
class _ResistanceFit:
    slope: float
    intercept: float
    residual: float
    first_index: int
    last_index: int
    pivot_indices: tuple[int, ...]

    def at(self, index: int) -> float:
        return self.slope * index + self.intercept


def _finite_positive_bar(bar: OysterBarLike) -> bool:
    values = (bar.open, bar.high, bar.low, bar.close, bar.volume)
    return all(math.isfinite(float(value)) for value in values) and min(
        bar.open, bar.high, bar.low, bar.close
    ) > 0 and bar.volume >= 0


def _resistance_fit(
    pivot_indices: Sequence[int],
    highs: Sequence[float],
    *,
    config: OysterConfig,
) -> _ResistanceFit | None:
    if len(pivot_indices) < config.minimum_pivots:
        return None
    selected = tuple(pivot_indices[-config.maximum_pivots :])
    xs = [float(index) for index in selected]
    ys = [highs[index] for index in selected]
    result = linreg(xs, ys)
    if result is None:
        return None
    slope, intercept = result
    fitted = [slope * index + intercept for index in xs]
    residual = statistics.fmean(
        abs(actual - estimate) for actual, estimate in zip(ys, fitted, strict=True)
    )
    return _ResistanceFit(
        slope=slope,
        intercept=intercept,
        residual=residual,
        first_index=selected[0],
        last_index=selected[-1],
        pivot_indices=selected,
    )


def _candidate_at(
    rows: Sequence[OysterBarLike],
    cross_index: int,
    *,
    config: OysterConfig,
) -> OysterSetup | None:
    current_index = len(rows) - 1
    sessions_since_cross = current_index - cross_index
    if sessions_since_cross < config.minimum_retest_sessions:
        return None

    highs = [float(bar.high) for bar in rows]
    lows = [float(bar.low) for bar in rows]
    closes = [float(bar.close) for bar in rows]
    volumes = [float(bar.volume) for bar in rows]
    atr14 = atr(highs[: cross_index + 1], lows[: cross_index + 1], closes[: cross_index + 1], 14)
    if atr14 is None or not math.isfinite(atr14) or atr14 <= 0:
        return None

    pivot_indices = [
        index
        for index in swing_high_indices(highs[:cross_index], config.pivot_radius)
        if index >= max(0, cross_index - config.lookback_sessions)
    ]
    fit = _resistance_fit(pivot_indices, highs, config=config)
    if fit is None or fit.slope >= 0:
        return None
    if cross_index - fit.last_index > config.maximum_last_pivot_age:
        return None

    resistance_start = fit.at(fit.first_index)
    resistance_cross = fit.at(cross_index)
    resistance_now = fit.at(current_index)
    if min(resistance_start, resistance_cross, resistance_now) <= 0:
        return None
    resistance_decline = 1.0 - resistance_cross / resistance_start
    if resistance_decline < config.minimum_resistance_decline:
        return None
    fit_residual_atr = fit.residual / atr14
    if fit_residual_atr > config.maximum_fit_residual_atr:
        return None

    previous_resistance = fit.at(cross_index - 1)
    if closes[cross_index - 1] > previous_resistance + config.cross_buffer_atr * atr14:
        return None
    if closes[cross_index] <= resistance_cross + config.cross_buffer_atr * atr14:
        return None
    cross_return = closes[cross_index] / closes[cross_index - 1] - 1.0
    if cross_return > config.maximum_cross_return:
        return None

    anchor_high = max(highs[fit.first_index : cross_index + 1])
    pre_cross_low = min(lows[max(fit.first_index, cross_index - 10) : cross_index + 1])
    decline_from_anchor = 1.0 - pre_cross_low / anchor_high
    if decline_from_anchor < config.minimum_decline:
        return None

    post_cross_closes = closes[cross_index : current_index + 1]
    post_cross_lows = lows[cross_index : current_index + 1]
    retest_drawdown = min(post_cross_lows) / closes[cross_index] - 1.0
    if retest_drawdown < -config.maximum_retest_drawdown:
        return None
    if any(
        closes[index] < fit.at(index) - config.hold_buffer_atr * atr14
        for index in range(cross_index, current_index + 1)
    ):
        return None

    baseline_start = max(0, cross_index - config.baseline_volume_sessions)
    baseline = volumes[baseline_start:cross_index]
    if len(baseline) < config.baseline_volume_sessions or statistics.fmean(baseline) <= 0:
        return None
    baseline_volume = statistics.fmean(baseline)

    retest_indices = range(cross_index + 1, current_index)
    completed_retest_volumes = [volumes[index] for index in retest_indices]
    retest_volume_ratio = (
        statistics.fmean(completed_retest_volumes) / baseline_volume
        if completed_retest_volumes
        else volumes[cross_index] / baseline_volume
    )
    if retest_volume_ratio > config.maximum_retest_volume_ratio:
        return None

    prior_retest_high = max(highs[cross_index:current_index])
    activation_level = prior_retest_high + config.activation_buffer_atr * atr14
    activation_volume_ratio = volumes[current_index] / baseline_volume
    activated = bool(
        closes[current_index] > activation_level
        and activation_volume_ratio >= config.activation_volume_ratio
    )
    if not activated:
        extension = max(post_cross_closes) / closes[cross_index] - 1.0
        if extension > config.maximum_pre_activation_extension:
            return None

    retest_support = min(post_cross_lows)
    distance_to_activation = max(activation_level / closes[current_index] - 1.0, 0.0)
    fit_quality = max(0.0, 1.0 - fit_residual_atr / config.maximum_fit_residual_atr)
    decline_quality = min(1.0, decline_from_anchor / 0.60)
    hold_quality = max(
        0.0,
        1.0 - abs(min(retest_drawdown, 0.0)) / config.maximum_retest_drawdown,
    )
    volume_quality = max(0.0, 1.0 - retest_volume_ratio / config.maximum_retest_volume_ratio)
    duration_quality = min(1.0, sessions_since_cross / 5.0)
    strength = (
        35.0
        + 15.0 * fit_quality
        + 15.0 * decline_quality
        + 10.0 * hold_quality
        + 10.0 * volume_quality
        + 10.0 * duration_quality
        + (5.0 if activated else 0.0)
    )
    return OysterSetup(
        as_of_date=rows[current_index].date,
        phase="activated" if activated else "retesting",
        trend_start_date=rows[fit.first_index].date,
        cross_date=rows[cross_index].date,
        activation_date=rows[current_index].date if activated else None,
        resistance_start=resistance_start,
        resistance_at_cross=resistance_cross,
        resistance_now=resistance_now,
        retest_support=retest_support,
        activation_level=activation_level,
        sessions_since_cross=sessions_since_cross,
        decline_from_anchor=decline_from_anchor,
        resistance_decline=resistance_decline,
        fit_residual_atr=fit_residual_atr,
        retest_drawdown=retest_drawdown,
        retest_volume_ratio=retest_volume_ratio,
        activation_volume_ratio=activation_volume_ratio if activated else None,
        distance_to_activation=distance_to_activation,
        strength_score=round(min(max(strength, 0.0), 100.0), 1),
        pivot_indices=fit.pivot_indices,
    )


def detect_oyster_at(
    bars: Sequence[OysterBarLike],
    as_of_index: int | None = None,
    *,
    config: OysterConfig = DEFAULT_OYSTER_CONFIG,
) -> OysterSetup | None:
    """Return an active daily Oyster approximation using only data known at ``as_of_index``."""
    ordered = sorted(bars, key=lambda bar: bar.date)
    if as_of_index is None:
        as_of_index = len(ordered) - 1
    if as_of_index < 0 or as_of_index >= len(ordered):
        return None
    rows = ordered[: as_of_index + 1]
    minimum_history = max(
        config.lookback_sessions // 2,
        config.baseline_volume_sessions + 2 * config.pivot_radius + config.minimum_retest_sessions,
    )
    if len(rows) < minimum_history or any(not _finite_positive_bar(bar) for bar in rows):
        return None

    latest_cross = len(rows) - 1 - config.minimum_retest_sessions
    earliest_cross = max(1, len(rows) - 1 - config.maximum_cross_age)
    for cross_index in range(latest_cross, earliest_cross - 1, -1):
        candidate = _candidate_at(rows, cross_index, config=config)
        if candidate is not None:
            return candidate
    return None
