"""US former-runner reactivation research.

The setup is a sequence, not a high-volume screen:

1. a recent extreme runner establishes attention and a reusable price memory;
2. price retraces deeply without immediately collapsing again;
3. two quiet sessions retain unusually high turnover versus the *pre-spike* baseline;
4. the row becomes an overnight watch state, not an order.

Daily bars can test whether that watch state precedes another expansion. They cannot test the
proposed one-minute-volume, previous-day-high and session-VWAP ignition entry because event order
inside a daily candle is unknown. Nothing in this module creates a strategy or paper target.
"""

from __future__ import annotations

import datetime as dt
import math
from collections.abc import Iterable
from dataclasses import asdict, dataclass

import numpy as np


@dataclass(frozen=True)
class FormerRunnerSpec:
    key: str = "us_former_runner_reactivation_v1"
    baseline_sessions: int = 20
    runner_lookback_sessions: int = 10
    minimum_pullback_sessions: int = 2
    runner_close_return: float = 0.40
    runner_high_return: float = 0.50
    runner_volume_multiple: float = 5.0
    minimum_pullback: float = 0.40
    maximum_pullback: float = 0.75
    probe_sessions: int = 2
    probe_volume_multiple: float = 3.0
    quiet_absolute_return: float = 0.12
    stabilization_floor: float = -0.05
    minimum_price: float = 0.50
    maximum_price: float = 5.00
    minimum_watch_turnover: float = 500_000.0
    outcome_sessions: int = 3
    primary_expansion: float = 0.20
    secondary_expansion: float = 0.50

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class RunnerBar:
    date: dt.date
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True)
class FormerRunnerEvent:
    code: str
    watch_date: dt.date
    runner_date: dt.date
    watch_close: float
    trigger_reference: float
    runner_close_return: float
    runner_volume_multiple: float
    pullback_from_runner_high: float
    first_probe_multiple: float
    second_probe_multiple: float
    liquidity_band: int
    volatility_band: int
    outcome_complete: bool
    primary_success: bool | None
    secondary_success: bool | None
    maximum_expansion: float | None
    maximum_close_expansion: float | None
    minimum_excursion: float | None


@dataclass(frozen=True)
class ControlObservation:
    code: str
    date: dt.date
    liquidity_band: int
    volatility_band: int
    primary_success: bool
    maximum_expansion: float


def _validate_bars(bars: Iterable[RunnerBar]) -> list[RunnerBar]:
    ordered = sorted(bars, key=lambda bar: bar.date)
    if any(
        min(bar.open, bar.high, bar.low, bar.close) <= 0
        or bar.volume < 0
        or not all(
            math.isfinite(value)
            for value in (bar.open, bar.high, bar.low, bar.close, bar.volume)
        )
        for bar in ordered
    ):
        raise ValueError("Former-runner bars require finite positive OHLC and non-negative volume")
    if len({bar.date for bar in ordered}) != len(ordered):
        raise ValueError("Former-runner bars must contain one row per session")
    return ordered


@dataclass(frozen=True)
class _Series:
    bars: list[RunnerBar]
    close_returns: np.ndarray
    prior_average_volume: np.ndarray
    average_dollar_volume: np.ndarray
    volatility: np.ndarray


def _series(bars: Iterable[RunnerBar], spec: FormerRunnerSpec) -> _Series:
    ordered = _validate_bars(bars)
    close = np.asarray([bar.close for bar in ordered], dtype=float)
    volume = np.asarray([bar.volume for bar in ordered], dtype=float)
    turnover = close * volume
    returns = np.full(len(ordered), np.nan)
    returns[1:] = close[1:] / close[:-1] - 1.0
    prior_volume = np.full(len(ordered), np.nan)
    average_turnover = np.full(len(ordered), np.nan)
    volatility = np.full(len(ordered), np.nan)
    window = spec.baseline_sessions
    for index in range(window, len(ordered)):
        prior_volume[index] = float(volume[index - window : index].mean())
        average_turnover[index] = float(turnover[index - window + 1 : index + 1].mean())
        sample = returns[index - window + 1 : index + 1]
        if np.isfinite(sample).sum() >= window - 1:
            volatility[index] = float(np.nanstd(sample, ddof=1))
    return _Series(
        bars=ordered,
        close_returns=returns,
        prior_average_volume=prior_volume,
        average_dollar_volume=average_turnover,
        volatility=volatility,
    )


def _liquidity_band(average_dollar_volume: float) -> int:
    if average_dollar_volume < 1_000_000:
        return 0
    if average_dollar_volume < 5_000_000:
        return 1
    if average_dollar_volume < 20_000_000:
        return 2
    return 3


def _volatility_band(volatility: float) -> int:
    if volatility < 0.05:
        return 0
    if volatility < 0.10:
        return 1
    return 2


def _eligible_watch(series: _Series, index: int, spec: FormerRunnerSpec) -> bool:
    bar = series.bars[index]
    return bool(
        spec.minimum_price <= bar.close <= spec.maximum_price
        and bar.close * bar.volume >= spec.minimum_watch_turnover
        and np.isfinite(series.average_dollar_volume[index])
        and np.isfinite(series.volatility[index])
    )


def scan_former_runner(
    code: str,
    bars: Iterable[RunnerBar],
    spec: FormerRunnerSpec | None = None,
) -> list[FormerRunnerEvent]:
    """Return the first qualifying watch state for each distinct runner episode."""
    spec = spec or FormerRunnerSpec()
    series = _series(bars, spec)
    values = series.bars
    events: list[FormerRunnerEvent] = []
    archived_runner_dates: set[dt.date] = set()
    start = spec.baseline_sessions + spec.minimum_pullback_sessions
    for watch_index in range(start, len(values)):
        watch = values[watch_index]
        if not _eligible_watch(series, watch_index, spec):
            continue
        runner_index = None
        lower = max(spec.baseline_sessions, watch_index - spec.runner_lookback_sessions)
        upper = watch_index - spec.minimum_pullback_sessions
        for candidate in range(upper, lower - 1, -1):
            prior_close = values[candidate - 1].close
            baseline_volume = series.prior_average_volume[candidate]
            if not np.isfinite(baseline_volume) or baseline_volume <= 0:
                continue
            runner_close_return = values[candidate].close / prior_close - 1.0
            runner_high_return = values[candidate].high / prior_close - 1.0
            runner_volume_multiple = values[candidate].volume / baseline_volume
            if (
                runner_close_return >= spec.runner_close_return
                and runner_high_return >= spec.runner_high_return
                and runner_volume_multiple >= spec.runner_volume_multiple
            ):
                runner_index = candidate
                break
        if runner_index is None:
            continue
        runner = values[runner_index]
        if runner.date in archived_runner_dates:
            continue

        pullback = 1.0 - watch.close / runner.high
        if not spec.minimum_pullback <= pullback <= spec.maximum_pullback:
            continue
        if series.close_returns[watch_index] < spec.stabilization_floor:
            continue

        probe_start = watch_index - spec.probe_sessions + 1
        if probe_start <= runner_index:
            continue
        baseline_volume = series.prior_average_volume[runner_index]
        probes = [
            values[index].volume / baseline_volume
            for index in range(probe_start, watch_index + 1)
        ]
        probe_returns = [
            abs(float(series.close_returns[index]))
            for index in range(probe_start, watch_index + 1)
        ]
        if any(value < spec.probe_volume_multiple for value in probes):
            continue
        if any(value > spec.quiet_absolute_return for value in probe_returns):
            continue
        if any(
            values[index].volume >= runner.volume * 0.20
            for index in range(probe_start, watch_index + 1)
        ):
            continue

        future = values[watch_index + 1 : watch_index + spec.outcome_sessions + 1]
        trigger = watch.high
        outcome_complete = len(future) == spec.outcome_sessions
        maximum_expansion = (
            max(bar.high for bar in future) / trigger - 1.0 if future else None
        )
        maximum_close_expansion = (
            max(bar.close for bar in future) / trigger - 1.0 if future else None
        )
        minimum_excursion = (
            min(bar.low for bar in future) / trigger - 1.0 if future else None
        )
        primary_success = (
            True
            if maximum_expansion is not None
            and maximum_expansion >= spec.primary_expansion
            else False if outcome_complete else None
        )
        secondary_success = (
            True
            if maximum_expansion is not None
            and maximum_expansion >= spec.secondary_expansion
            else False if outcome_complete else None
        )
        events.append(
            FormerRunnerEvent(
                code=code,
                watch_date=watch.date,
                runner_date=runner.date,
                watch_close=watch.close,
                trigger_reference=trigger,
                runner_close_return=runner.close / values[runner_index - 1].close - 1.0,
                runner_volume_multiple=runner.volume / baseline_volume,
                pullback_from_runner_high=-pullback,
                first_probe_multiple=probes[-2],
                second_probe_multiple=probes[-1],
                liquidity_band=_liquidity_band(series.average_dollar_volume[watch_index]),
                volatility_band=_volatility_band(series.volatility[watch_index]),
                outcome_complete=outcome_complete,
                primary_success=primary_success,
                secondary_success=secondary_success,
                maximum_expansion=maximum_expansion,
                maximum_close_expansion=maximum_close_expansion,
                minimum_excursion=minimum_excursion,
            )
        )
        archived_runner_dates.add(runner.date)
    return events


def control_observations(
    code: str,
    bars: Iterable[RunnerBar],
    dates: set[dt.date],
    spec: FormerRunnerSpec | None = None,
) -> list[ControlObservation]:
    """Build date/liquidity/volatility matched opportunity controls."""
    spec = spec or FormerRunnerSpec()
    series = _series(bars, spec)
    output: list[ControlObservation] = []
    for index, bar in enumerate(series.bars):
        if (
            bar.date not in dates
            or not _eligible_watch(series, index, spec)
            or index + spec.outcome_sessions >= len(series.bars)
        ):
            continue
        future = series.bars[index + 1 : index + spec.outcome_sessions + 1]
        expansion = max(item.high for item in future) / bar.high - 1.0
        output.append(
            ControlObservation(
                code=code,
                date=bar.date,
                liquidity_band=_liquidity_band(series.average_dollar_volume[index]),
                volatility_band=_volatility_band(series.volatility[index]),
                primary_success=expansion >= spec.primary_expansion,
                maximum_expansion=expansion,
            )
        )
    return output
