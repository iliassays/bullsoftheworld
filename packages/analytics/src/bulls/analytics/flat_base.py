"""Point-in-time high-volume flat-base setup detection.

The detector intentionally separates a quiet setup from its confirmation day. Every calculation
uses only bars available on ``as_of``; backtests and production analytics call this same function
so research thresholds cannot silently diverge from the portal implementation.
"""

from __future__ import annotations

import datetime as dt
import statistics
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal, Protocol


class VolumeBarLike(Protocol):
    date: dt.date
    high: float
    low: float
    close: float
    volume: int


FlatBaseStatus = Literal["forming", "confirmed_breakout_up"]


@dataclass(frozen=True)
class FlatBaseConfig:
    base_days: int = 15
    max_depth: float = 0.10
    max_close_cv: float = 0.04
    touch_tolerance: float = 0.03
    min_resistance_touches: int = 2
    max_dry_up_ratio: float = 1.20
    near_resistance: float = 0.05
    breakout_buffer: float = 0.005
    min_breakout_volume_ratio: float = 2.00
    max_breakout_extension: float = 0.08
    min_breakout_close_location: float = 0.65
    min_average_turnover: float = 5_000_000.0
    min_price: float = 5.0
    trend_days: int = 50
    trend_slope_days: int = 10


DEFAULT_FLAT_BASE_CONFIG = FlatBaseConfig()


@dataclass(frozen=True)
class FlatBaseSetup:
    status: FlatBaseStatus
    start_date: dt.date
    as_of_date: dt.date
    resistance: float
    support: float
    depth: float
    close_cv: float
    resistance_touches: int
    dry_up_ratio: float
    volume_ratio: float
    average_turnover: float
    strength_score: float


def _mean(values: Sequence[float]) -> float:
    return statistics.fmean(values) if values else 0.0


def detect_flat_base_at(
    bars: Sequence[VolumeBarLike],
    index: int | None = None,
    *,
    config: FlatBaseConfig = DEFAULT_FLAT_BASE_CONFIG,
) -> FlatBaseSetup | None:
    """Return a forming or confirmed setup at one historical index without future leakage."""
    rows = bars
    i = len(rows) - 1 if index is None else index
    required = max(
        config.base_days,
        config.trend_days + config.trend_slope_days,
    )
    if i < required or i >= len(rows):
        return None

    current = rows[i]
    if current.close < config.min_price or current.high <= 0 or current.low <= 0:
        return None

    base = rows[i - config.base_days : i]
    closes = [float(bar.close) for bar in base]
    highs = [float(bar.high) for bar in base]
    lows = [float(bar.low) for bar in base]
    volumes = [float(bar.volume) for bar in base]
    if not closes or min(closes) <= 0 or min(lows) <= 0 or _mean(volumes) <= 0:
        return None

    resistance = max(highs)
    support = min(lows)
    depth = resistance / support - 1
    close_mean = _mean(closes)
    close_cv = statistics.pstdev(closes) / close_mean if close_mean else float("inf")
    if depth > config.max_depth or close_cv > config.max_close_cv:
        return None

    touch_floor = resistance * (1 - config.touch_tolerance)
    touches = sum(high >= touch_floor for high in highs)
    if touches < config.min_resistance_touches:
        return None

    old_volume = volumes[:-5]
    recent_volume = volumes[-5:]
    dry_up_ratio = _mean(recent_volume) / _mean(old_volume) if _mean(old_volume) else float("inf")
    if dry_up_ratio > config.max_dry_up_ratio:
        return None

    average_turnover = _mean([float(bar.close) * float(bar.volume) for bar in base])
    if average_turnover < config.min_average_turnover:
        return None

    trend_now = _mean([float(bar.close) for bar in rows[i - config.trend_days : i]])
    trend_then = _mean(
        [
            float(bar.close)
            for bar in rows[
                i - config.trend_days - config.trend_slope_days : i - config.trend_slope_days
            ]
        ]
    )
    # The setup must live in a rising intermediate trend, but the last base close may legitimately
    # sit just below the average before the breakout (ITC on 2026-06-23 is a real example). Use the
    # as-of close, which is known when the signal is evaluated, rather than requiring yesterday's
    # close to have already completed the breakout.
    if trend_now <= trend_then or current.close < trend_now:
        return None

    average_volume = _mean(volumes)
    volume_ratio = float(current.volume) / average_volume
    breakout_floor = resistance * (1 + config.breakout_buffer)
    breakout_ceiling = resistance * (1 + config.max_breakout_extension)
    day_range = current.high - current.low
    close_location = (current.close - current.low) / day_range if day_range > 0 else 0.5
    confirmed = (
        breakout_floor < current.close <= breakout_ceiling
        and volume_ratio >= config.min_breakout_volume_ratio
        and close_location >= config.min_breakout_close_location
    )

    if confirmed:
        status: FlatBaseStatus = "confirmed_breakout_up"
    else:
        distance = resistance / current.close - 1
        if current.close > breakout_floor or not 0 <= distance <= config.near_resistance:
            return None
        status = "forming"

    tightness = max(0.0, 1 - depth / config.max_depth)
    compactness = max(0.0, 1 - close_cv / config.max_close_cv)
    dryness = max(0.0, 1 - dry_up_ratio / config.max_dry_up_ratio)
    touch_quality = min(1.0, (touches - config.min_resistance_touches + 1) / 4)
    proximity = max(0.0, 1 - max(resistance / current.close - 1, 0) / config.near_resistance)
    strength = 45 + 12 * tightness + 10 * compactness + 8 * dryness + 8 * touch_quality
    if confirmed:
        volume_quality = min(1.0, volume_ratio / (2 * config.min_breakout_volume_ratio))
        strength += 10 + 7 * volume_quality
    else:
        strength += 7 * proximity

    return FlatBaseSetup(
        status=status,
        start_date=base[0].date,
        as_of_date=current.date,
        resistance=round(resistance, 4),
        support=round(support, 4),
        depth=round(depth, 6),
        close_cv=round(close_cv, 6),
        resistance_touches=touches,
        dry_up_ratio=round(dry_up_ratio, 6),
        volume_ratio=round(volume_ratio, 6),
        average_turnover=round(average_turnover, 2),
        strength_score=round(min(strength, 100.0), 1),
    )
