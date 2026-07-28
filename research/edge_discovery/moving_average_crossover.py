"""Causal daily moving-average crossover research.

The scanner observes a crossover only after a completed close, enters at the next session open,
and exits at the open after an observable close below the slow average. It is research-only and
cannot create Atlas decisions, targets, or paper orders.
"""

from __future__ import annotations

import datetime as dt
import math
import statistics
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from typing import Literal

ExitReason = Literal["slow_average_break", "timeout"]


@dataclass(frozen=True)
class MovingAverageCrossoverSpec:
    key: str
    fast_period: int = 20
    slow_period: int = 50
    regime_period: int = 200
    slope_lookback: int = 5
    atr_period: int = 14
    maximum_extension_atr: float = 1.5
    maximum_holding_sessions: int = 63
    turnover_period: int = 20
    minimum_price: float = 1.0
    minimum_average_turnover: float = 1_000_000.0
    contamination_lookback_sessions: int = 60
    maximum_close_jump: float | None = None

    def __post_init__(self) -> None:
        periods = (
            self.fast_period,
            self.slow_period,
            self.regime_period,
            self.slope_lookback,
            self.atr_period,
            self.maximum_holding_sessions,
            self.turnover_period,
            self.contamination_lookback_sessions,
        )
        if min(periods) <= 0:
            raise ValueError("Moving-average crossover periods must be positive")
        if not self.fast_period < self.slow_period < self.regime_period:
            raise ValueError("Expected fast_period < slow_period < regime_period")
        if self.maximum_extension_atr <= 0:
            raise ValueError("maximum_extension_atr must be positive")
        if min(self.minimum_price, self.minimum_average_turnover) < 0:
            raise ValueError("Eligibility floors cannot be negative")

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class MovingAverageBar:
    date: dt.date
    open: float
    high: float
    low: float
    close: float
    volume: float
    raw_close: float


@dataclass(frozen=True)
class MovingAverageSeries:
    fast: tuple[float | None, ...]
    slow: tuple[float | None, ...]
    regime: tuple[float | None, ...]
    atr: tuple[float | None, ...]


@dataclass(frozen=True)
class MovingAverageCrossoverTrade:
    code: str
    signal_date: dt.date
    entry_date: dt.date
    exit_signal_date: dt.date
    exit_date: dt.date
    signal_close: float
    entry_open: float
    exit_open: float
    fast_at_signal: float
    slow_at_signal: float
    regime_at_signal: float
    atr_at_signal: float
    extension_atr: float
    average_turnover: float
    holding_sessions: int
    exit_reason: ExitReason
    gross_return: float
    normal_return: float
    stressed_return: float
    maximum_favorable_excursion: float
    maximum_adverse_excursion: float
    entry_gap: float


def moving_average_bar_issue(bar: MovingAverageBar) -> str | None:
    values = (bar.open, bar.high, bar.low, bar.close, bar.volume, bar.raw_close)
    if not all(math.isfinite(value) for value in values):
        return "non_finite"
    if min(bar.open, bar.high, bar.low, bar.close, bar.raw_close) <= 0 or bar.volume < 0:
        return "non_positive"
    if bar.high < max(bar.open, bar.close) or bar.low > min(bar.open, bar.close):
        return "invalid_ohlc_range"
    return None


def _validated_bars(bars: Iterable[MovingAverageBar]) -> list[MovingAverageBar]:
    ordered = sorted(bars, key=lambda item: item.date)
    if len({item.date for item in ordered}) != len(ordered):
        raise ValueError("Moving-average bars must contain one row per session")
    for bar in ordered:
        issue = moving_average_bar_issue(bar)
        if issue is not None:
            raise ValueError(f"Moving-average bar is invalid: {issue}")
    return ordered


def _sma(values: list[float], period: int) -> list[float | None]:
    result: list[float | None] = [None] * len(values)
    if len(values) < period:
        return result
    rolling_sum = sum(values[:period])
    result[period - 1] = rolling_sum / period
    for index in range(period, len(values)):
        rolling_sum += values[index] - values[index - period]
        result[index] = rolling_sum / period
    return result


def _wilder_atr(bars: list[MovingAverageBar], period: int) -> list[float | None]:
    result: list[float | None] = [None] * len(bars)
    if len(bars) < period:
        return result
    true_ranges: list[float] = []
    for index, bar in enumerate(bars):
        if index == 0:
            true_ranges.append(bar.high - bar.low)
            continue
        previous_close = bars[index - 1].close
        true_ranges.append(
            max(
                bar.high - bar.low,
                abs(bar.high - previous_close),
                abs(bar.low - previous_close),
            )
        )
    seed_index = period - 1
    result[seed_index] = statistics.fmean(true_ranges[:period])
    for index in range(seed_index + 1, len(bars)):
        previous = result[index - 1]
        assert previous is not None
        result[index] = (previous * (period - 1) + true_ranges[index]) / period
    return result


def moving_average_series(
    bars: Iterable[MovingAverageBar],
    spec: MovingAverageCrossoverSpec,
) -> MovingAverageSeries:
    ordered = _validated_bars(bars)
    closes = [bar.close for bar in ordered]
    return MovingAverageSeries(
        fast=tuple(_sma(closes, spec.fast_period)),
        slow=tuple(_sma(closes, spec.slow_period)),
        regime=tuple(_sma(closes, spec.regime_period)),
        atr=tuple(_wilder_atr(ordered, spec.atr_period)),
    )


def _average_turnover(
    bars: list[MovingAverageBar],
    signal_index: int,
    window: int,
) -> float | None:
    start = signal_index - window + 1
    if start < 0:
        return None
    return statistics.fmean(bar.raw_close * bar.volume for bar in bars[start : signal_index + 1])


def _has_contamination(
    bars: list[MovingAverageBar],
    *,
    start: int,
    end: int,
    maximum_jump: float | None,
) -> bool:
    if maximum_jump is None:
        return False
    start = max(1, start)
    end = min(end, len(bars) - 1)
    return any(
        abs(bars[index].raw_close / bars[index - 1].raw_close - 1.0) > maximum_jump
        for index in range(start, end + 1)
    )


def _net_return(entry_open: float, exit_open: float, one_way_cost: float) -> float:
    entry_fill = entry_open * (1.0 + one_way_cost)
    exit_fill = exit_open * (1.0 - one_way_cost)
    return exit_fill / entry_fill - 1.0


def _excursions(
    entry_open: float,
    bars: list[MovingAverageBar],
    entry_index: int,
    exit_index: int,
) -> tuple[float, float]:
    held = bars[entry_index:exit_index]
    favorable = max([entry_open, *(bar.high for bar in held)]) / entry_open - 1.0
    adverse = min([entry_open, *(bar.low for bar in held)]) / entry_open - 1.0
    return favorable, adverse


def scan_bullish_crossover_trades(
    code: str,
    bars: Iterable[MovingAverageBar],
    *,
    spec: MovingAverageCrossoverSpec,
    normal_one_way_cost: float,
    stressed_one_way_cost: float,
) -> list[MovingAverageCrossoverTrade]:
    """Return completed, non-overlapping bullish-crossover trades for one security."""
    ordered = _validated_bars(bars)
    series = moving_average_series(ordered, spec)
    trades: list[MovingAverageCrossoverTrade] = []
    index = max(
        spec.regime_period - 1,
        spec.slow_period - 1 + spec.slope_lookback,
    )

    while index < len(ordered) - 1:
        fast = series.fast[index]
        slow = series.slow[index]
        regime = series.regime[index]
        atr = series.atr[index]
        previous_fast = series.fast[index - 1]
        previous_slow = series.slow[index - 1]
        slope_fast = series.fast[index - spec.slope_lookback]
        slope_slow = series.slow[index - spec.slope_lookback]
        if any(
            value is None
            for value in (
                fast,
                slow,
                regime,
                atr,
                previous_fast,
                previous_slow,
                slope_fast,
                slope_slow,
            )
        ):
            index += 1
            continue

        assert fast is not None
        assert slow is not None
        assert regime is not None
        assert atr is not None
        assert previous_fast is not None
        assert previous_slow is not None
        assert slope_fast is not None
        assert slope_slow is not None
        close = ordered[index].close
        extension = (close - fast) / atr if atr > 0 else math.inf
        crossed = previous_fast <= previous_slow and fast > slow
        eligible_signal = (
            crossed
            and fast > slope_fast
            and slow > slope_slow
            and close > regime
            and close > fast
            and extension <= spec.maximum_extension_atr
        )
        if not eligible_signal:
            index += 1
            continue

        turnover = _average_turnover(ordered, index, spec.turnover_period)
        contaminated_before_entry = _has_contamination(
            ordered,
            start=index - spec.contamination_lookback_sessions + 1,
            end=index,
            maximum_jump=spec.maximum_close_jump,
        )
        if (
            turnover is None
            or turnover < spec.minimum_average_turnover
            or ordered[index].raw_close < spec.minimum_price
            or contaminated_before_entry
        ):
            index += 1
            continue

        entry_index = index + 1
        final_decision_index = min(
            entry_index + spec.maximum_holding_sessions - 1,
            len(ordered) - 2,
        )
        exit_signal_index: int | None = None
        exit_reason: ExitReason = "timeout"
        for candidate in range(entry_index, final_decision_index + 1):
            candidate_slow = series.slow[candidate]
            if candidate_slow is not None and ordered[candidate].close < candidate_slow:
                exit_signal_index = candidate
                exit_reason = "slow_average_break"
                break
        if exit_signal_index is None:
            requested_timeout = entry_index + spec.maximum_holding_sessions - 1
            if requested_timeout >= len(ordered) - 1:
                break
            exit_signal_index = requested_timeout
        exit_index = exit_signal_index + 1

        if _has_contamination(
            ordered,
            start=index - spec.contamination_lookback_sessions + 1,
            end=exit_signal_index,
            maximum_jump=spec.maximum_close_jump,
        ):
            index = exit_index
            continue

        entry_open = ordered[entry_index].open
        exit_open = ordered[exit_index].open
        favorable, adverse = _excursions(entry_open, ordered, entry_index, exit_index)
        trades.append(
            MovingAverageCrossoverTrade(
                code=code,
                signal_date=ordered[index].date,
                entry_date=ordered[entry_index].date,
                exit_signal_date=ordered[exit_signal_index].date,
                exit_date=ordered[exit_index].date,
                signal_close=close,
                entry_open=entry_open,
                exit_open=exit_open,
                fast_at_signal=fast,
                slow_at_signal=slow,
                regime_at_signal=regime,
                atr_at_signal=atr,
                extension_atr=extension,
                average_turnover=turnover,
                holding_sessions=exit_index - entry_index,
                exit_reason=exit_reason,
                gross_return=exit_open / entry_open - 1.0,
                normal_return=_net_return(entry_open, exit_open, normal_one_way_cost),
                stressed_return=_net_return(entry_open, exit_open, stressed_one_way_cost),
                maximum_favorable_excursion=favorable,
                maximum_adverse_excursion=adverse,
                entry_gap=entry_open / close - 1.0,
            )
        )
        index = exit_index

    return trades
