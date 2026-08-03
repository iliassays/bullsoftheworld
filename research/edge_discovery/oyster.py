"""Point-in-time outcome harness for the daily Oyster approximation.

This is an event study, not a trading strategy.  The first observable retest state in each
falling-resistance-break episode is archived once.  Outcomes describe subsequent completed bars;
they do not assume that the signal close or an intraday high was executable.
"""

from __future__ import annotations

import datetime as dt
import math
import statistics
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field

from bulls.analytics.oyster import OysterConfig, OysterSetup, detect_oyster_at


@dataclass(frozen=True)
class OysterResearchSpec:
    key: str
    analysis_start: dt.date
    minimum_price: float
    maximum_price: float | None
    minimum_average_turnover: float
    maximum_absolute_close_return: float | None
    episode_cooldown_sessions: int = 30
    outcome_sessions: tuple[int, ...] = (1, 3, 5, 10, 20)
    opportunity_thresholds: tuple[float, ...] = (0.10, 0.20)
    detector: OysterConfig = field(default_factory=OysterConfig)

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class OysterResearchBar:
    date: dt.date
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True)
class OysterResearchEvent:
    code: str
    signal_date: dt.date
    cross_date: dt.date
    phase: str
    signal_close: float
    signal_high: float
    average_turnover: float
    decline_from_anchor: float
    retest_drawdown: float
    retest_volume_ratio: float
    strength_score: float
    close_returns: dict[int, float | None]
    maximum_high_returns: dict[int, float | None]
    minimum_low_returns: dict[int, float | None]
    opportunities: dict[str, bool | None]


def _ordered_bars(bars: Iterable[OysterResearchBar]) -> list[OysterResearchBar]:
    rows = sorted(bars, key=lambda bar: bar.date)
    if len({bar.date for bar in rows}) != len(rows):
        raise ValueError("Oyster research requires one bar per completed session")
    if any(
        min(bar.open, bar.high, bar.low, bar.close) <= 0
        or bar.volume < 0
        or not all(
            math.isfinite(value)
            for value in (bar.open, bar.high, bar.low, bar.close, bar.volume)
        )
        for bar in rows
    ):
        raise ValueError("Oyster research bars require finite positive OHLC and non-negative volume")
    return rows


def _average_turnover(rows: list[OysterResearchBar], index: int, sessions: int = 20) -> float | None:
    if index + 1 < sessions:
        return None
    sample = rows[index - sessions + 1 : index + 1]
    return statistics.fmean(bar.close * bar.volume for bar in sample)


def _has_contaminating_jump(
    rows: list[OysterResearchBar],
    index: int,
    threshold: float | None,
    lookback: int,
) -> bool:
    if threshold is None:
        return False
    start = max(1, index - lookback + 1)
    return any(
        abs(rows[cursor].close / rows[cursor - 1].close - 1.0) > threshold
        for cursor in range(start, index + 1)
    )


def _eligible(
    rows: list[OysterResearchBar],
    index: int,
    spec: OysterResearchSpec,
) -> tuple[bool, float | None]:
    close = rows[index].close
    turnover = _average_turnover(rows, index)
    return (
        close >= spec.minimum_price
        and (spec.maximum_price is None or close <= spec.maximum_price)
        and turnover is not None
        and turnover >= spec.minimum_average_turnover
        and not _has_contaminating_jump(
            rows,
            index,
            spec.maximum_absolute_close_return,
            spec.detector.lookback_sessions,
        ),
        turnover,
    )


def _outcomes(
    rows: list[OysterResearchBar],
    index: int,
    horizons: tuple[int, ...],
    thresholds: tuple[float, ...],
) -> tuple[
    dict[int, float | None],
    dict[int, float | None],
    dict[int, float | None],
    dict[str, bool | None],
]:
    reference_close = rows[index].close
    reference_high = rows[index].high
    close_returns: dict[int, float | None] = {}
    maximum_high_returns: dict[int, float | None] = {}
    minimum_low_returns: dict[int, float | None] = {}
    for horizon in horizons:
        future = rows[index + 1 : index + horizon + 1]
        complete = len(future) == horizon
        close_returns[horizon] = future[-1].close / reference_close - 1.0 if complete else None
        maximum_high_returns[horizon] = (
            max(bar.high for bar in future) / reference_high - 1.0 if complete else None
        )
        minimum_low_returns[horizon] = (
            min(bar.low for bar in future) / reference_close - 1.0 if complete else None
        )
    maximum_horizon = max(horizons)
    opportunity_return = maximum_high_returns[maximum_horizon]
    opportunities = {
        f"{maximum_horizon}s_{round(threshold * 100):d}pct": (
            opportunity_return >= threshold if opportunity_return is not None else None
        )
        for threshold in thresholds
    }
    return close_returns, maximum_high_returns, minimum_low_returns, opportunities


def _event(
    code: str,
    rows: list[OysterResearchBar],
    index: int,
    turnover: float,
    setup: OysterSetup,
    spec: OysterResearchSpec,
) -> OysterResearchEvent:
    close_returns, maximum_high_returns, minimum_low_returns, opportunities = _outcomes(
        rows,
        index,
        spec.outcome_sessions,
        spec.opportunity_thresholds,
    )
    return OysterResearchEvent(
        code=code,
        signal_date=rows[index].date,
        cross_date=setup.cross_date,
        phase=setup.phase,
        signal_close=rows[index].close,
        signal_high=rows[index].high,
        average_turnover=turnover,
        decline_from_anchor=setup.decline_from_anchor,
        retest_drawdown=setup.retest_drawdown,
        retest_volume_ratio=setup.retest_volume_ratio,
        strength_score=setup.strength_score,
        close_returns=close_returns,
        maximum_high_returns=maximum_high_returns,
        minimum_low_returns=minimum_low_returns,
        opportunities=opportunities,
    )


def scan_oyster_events(
    code: str,
    bars: Iterable[OysterResearchBar],
    spec: OysterResearchSpec,
) -> list[OysterResearchEvent]:
    """Archive the first eligible retest state for each distinct resistance-cross episode."""
    rows = _ordered_bars(bars)
    events: list[OysterResearchEvent] = []
    archived_cross_dates: set[dt.date] = set()
    last_signal_index: int | None = None
    context = spec.detector.lookback_sessions + spec.detector.maximum_cross_age + 10
    start = max(
        spec.detector.lookback_sessions // 2,
        spec.detector.baseline_volume_sessions
        + 2 * spec.detector.pivot_radius
        + spec.detector.minimum_retest_sessions,
    )
    for index in range(start, len(rows)):
        if rows[index].date < spec.analysis_start:
            continue
        eligible, turnover = _eligible(rows, index, spec)
        if not eligible or turnover is None:
            continue
        prefix = rows[max(0, index - context) : index + 1]
        setup = detect_oyster_at(prefix, config=spec.detector)
        if (
            setup is None
            or setup.cross_date in archived_cross_dates
            or (
                last_signal_index is not None
                and index - last_signal_index < spec.episode_cooldown_sessions
            )
        ):
            continue
        events.append(_event(code, rows, index, turnover, setup, spec))
        archived_cross_dates.add(setup.cross_date)
        last_signal_index = index
    return events
