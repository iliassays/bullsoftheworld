"""Versioned, point-in-time research conditions for completed daily bars.

The registry in this module is deliberately small. Conditions are descriptive inputs for an
analyst investigation; they are not strategies, recommendations, targets, or order triggers.
Every evaluation uses only the bar history available on that date, including prior-session
volume for relative-volume baselines.
"""

from __future__ import annotations

import datetime as dt
import statistics
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from itertools import pairwise
from typing import Literal, Protocol

from bulls.analytics.chart_overlays import exponential_moving_average

ConditionState = Literal["observed", "not_observed", "unavailable"]
OutcomeStatus = Literal["matured", "pending"]
RuleOperator = Literal["gt", "gte", "lt", "lte", "between"]

METHODOLOGY_VERSION = "research-conditions-v1"
DEFAULT_OUTCOME_HORIZONS: tuple[int, ...] = (1, 5, 20, 60)


class ResearchBar(Protocol):
    date: dt.date
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True, slots=True)
class OverlayPoint:
    date: dt.date
    value: float


@dataclass(frozen=True, slots=True)
class OverlaySeries:
    key: str
    label: str
    points: tuple[OverlayPoint, ...]


@dataclass(frozen=True, slots=True)
class ConditionCheck:
    fact_key: str
    label: str
    observed: float | None
    expected: str
    unit: Literal["percent", "multiple"]
    passed: bool | None


@dataclass(frozen=True, slots=True)
class ConditionTransition:
    date: dt.date
    close: float
    sequence: int


@dataclass(frozen=True, slots=True)
class ConditionStateChange:
    """Point-in-time condition classification change at a completed close."""

    date: dt.date
    close: float
    previous_state: ConditionState | None
    state: ConditionState
    checks: tuple[ConditionCheck, ...]


@dataclass(frozen=True, slots=True)
class ConditionTimeline:
    key: str
    version: str
    state_changes: tuple[ConditionStateChange, ...]


@dataclass(frozen=True, slots=True)
class ConditionOutcome:
    """Close-path diagnostic after a condition first becomes observed.

    This is intentionally not an executable trade result. The reference is the observation
    session's completed close; the first measurable horizon is the next completed session.
    """

    condition_key: str
    condition_version: str
    observed_date: dt.date
    reference_close: float
    horizon_sessions: int
    status: OutcomeStatus
    outcome_date: dt.date | None
    close_return_pct: float | None
    max_favorable_pct: float | None
    max_adverse_pct: float | None
    benchmark_return_pct: float | None
    excess_return_pct: float | None


@dataclass(frozen=True, slots=True)
class ConditionCalibration:
    condition_key: str
    condition_version: str
    horizon_sessions: int
    observations: int
    matured: int
    pending: int
    average_return_pct: float | None
    median_return_pct: float | None
    positive_rate_pct: float | None
    average_benchmark_return_pct: float | None
    median_excess_return_pct: float | None
    benchmark_observations: int
    average_max_favorable_pct: float | None
    average_max_adverse_pct: float | None


@dataclass(frozen=True, slots=True)
class ConditionEvaluation:
    key: str
    version: str
    title: str
    short_label: str
    category: str
    state: ConditionState
    summary: str
    why_it_matters: str
    limitation: str
    checks: tuple[ConditionCheck, ...]
    transitions: tuple[ConditionTransition, ...]


@dataclass(frozen=True, slots=True)
class ConditionWorkbench:
    methodology_version: str
    timeframe: Literal["1d"]
    as_of_date: dt.date | None
    history_start_date: dt.date | None
    disclaimer: str
    overlays: tuple[OverlaySeries, ...]
    conditions: tuple[ConditionEvaluation, ...]


@dataclass(frozen=True, slots=True)
class _RuleSpec:
    fact_key: str
    label: str
    operator: RuleOperator
    lower: float
    upper: float | None
    expected: str
    unit: Literal["percent", "multiple"]


@dataclass(frozen=True, slots=True)
class _ConditionSpec:
    key: str
    version: str
    title: str
    short_label: str
    category: str
    why_it_matters: str
    limitation: str
    rules: tuple[_RuleSpec, ...]


CONDITION_REGISTRY: tuple[_ConditionSpec, ...] = (
    _ConditionSpec(
        key="trend_alignment",
        version="1.0.0",
        title="Trend alignment",
        short_label="T",
        category="trend",
        why_it_matters=(
            "A rising 20-session trend above a rising 50-session trend describes persistent "
            "direction rather than a one-session price jump."
        ),
        limitation=(
            "Moving averages react after price. This condition can remain present late in a move "
            "and says nothing about valuation, liquidity, or future return."
        ),
        rules=(
            _RuleSpec(
                "close_vs_ema20_pct",
                "Close above EMA20",
                "gt",
                0.0,
                None,
                "> 0%",
                "percent",
            ),
            _RuleSpec(
                "ema20_vs_ema50_pct",
                "EMA20 above EMA50",
                "gt",
                0.0,
                None,
                "> 0%",
                "percent",
            ),
            _RuleSpec(
                "ema20_slope_5_pct",
                "EMA20 rising over 5 sessions",
                "gt",
                0.0,
                None,
                "> 0%",
                "percent",
            ),
            _RuleSpec(
                "ema50_slope_10_pct",
                "EMA50 rising over 10 sessions",
                "gt",
                0.0,
                None,
                "> 0%",
                "percent",
            ),
        ),
    ),
    _ConditionSpec(
        key="participation_expansion",
        version="1.0.0",
        title="Participation expansion",
        short_label="V",
        category="volume",
        why_it_matters=(
            "Price strength accompanied by volume materially above the prior 20-session pace "
            "is broader evidence than price movement alone."
        ),
        limitation=(
            "Large volume can reflect distribution, news, rebalancing, or forced activity. It "
            "does not identify an institution or prove accumulation."
        ),
        rules=(
            _RuleSpec(
                "relative_volume_20",
                "Volume versus prior 20 sessions",
                "gte",
                1.5,
                None,
                ">= 1.50x",
                "multiple",
            ),
            _RuleSpec(
                "daily_return_pct",
                "Completed-session price change",
                "gt",
                0.0,
                None,
                "> 0%",
                "percent",
            ),
            _RuleSpec(
                "close_vs_ema20_pct",
                "Close relative to EMA20",
                "gte",
                0.0,
                None,
                ">= 0%",
                "percent",
            ),
        ),
    ),
    _ConditionSpec(
        key="controlled_pullback_context",
        version="1.0.0",
        title="Controlled pullback context",
        short_label="P",
        category="trend context",
        why_it_matters=(
            "A quiet return toward the 20-session trend while the broader 50-session trend stays "
            "intact can focus follow-up research on orderly consolidation."
        ),
        limitation=(
            "This is a daily-bar context proxy, not an intraday pullback strategy or entry rule. "
            "It requires separate liquidity, catalyst, risk, and strategy validation."
        ),
        rules=(
            _RuleSpec(
                "ema20_vs_ema50_pct",
                "EMA20 above EMA50",
                "gt",
                0.0,
                None,
                "> 0%",
                "percent",
            ),
            _RuleSpec(
                "ema20_slope_5_pct",
                "EMA20 rising over 5 sessions",
                "gt",
                0.0,
                None,
                "> 0%",
                "percent",
            ),
            _RuleSpec(
                "close_vs_ema20_pct",
                "Close near EMA20",
                "between",
                -3.0,
                2.0,
                "-3.00% to +2.00%",
                "percent",
            ),
            _RuleSpec(
                "close_vs_ema50_pct",
                "Close above EMA50",
                "gt",
                0.0,
                None,
                "> 0%",
                "percent",
            ),
            _RuleSpec(
                "relative_volume_20",
                "Volume remains controlled",
                "lte",
                1.2,
                None,
                "<= 1.20x",
                "multiple",
            ),
        ),
    ),
)


def _percentage(current: float | None, reference: float | None) -> float | None:
    if current is None or reference is None or reference == 0:
        return None
    return (current / reference - 1.0) * 100.0


def _passes(rule: _RuleSpec, value: float) -> bool:
    if rule.operator == "gt":
        return value > rule.lower
    if rule.operator == "gte":
        return value >= rule.lower
    if rule.operator == "lt":
        return value < rule.lower
    if rule.operator == "lte":
        return value <= rule.lower
    if rule.upper is None:
        raise ValueError(f"between rule {rule.fact_key} requires an upper bound")
    return rule.lower <= value <= rule.upper


def _checks(
    rules: Sequence[_RuleSpec], facts: dict[str, float | None]
) -> tuple[ConditionCheck, ...]:
    output: list[ConditionCheck] = []
    for rule in rules:
        value = facts.get(rule.fact_key)
        output.append(
            ConditionCheck(
                fact_key=rule.fact_key,
                label=rule.label,
                observed=round(value, 4) if value is not None else None,
                expected=rule.expected,
                unit=rule.unit,
                passed=_passes(rule, value) if value is not None else None,
            )
        )
    return tuple(output)


def _state(checks: Sequence[ConditionCheck]) -> ConditionState:
    if any(check.passed is None for check in checks):
        return "unavailable"
    return "observed" if all(check.passed for check in checks) else "not_observed"


def _summary(state: ConditionState, checks: Sequence[ConditionCheck]) -> str:
    passed = sum(check.passed is True for check in checks)
    if state == "unavailable":
        available = sum(check.passed is not None for check in checks)
        return f"Only {available} of {len(checks)} checks have enough completed-session history."
    if state == "observed":
        return f"All {len(checks)} completed-session checks are present at this cutoff."
    return f"{passed} of {len(checks)} checks are present; the full condition is not observed."


def _fact_history(
    bars: Sequence[ResearchBar],
) -> tuple[list[dict[str, float | None]], list[float | None], list[float | None]]:
    closes = [float(bar.close) for bar in bars]
    volumes = [float(bar.volume) for bar in bars]
    ema20 = exponential_moving_average(closes, 20)
    ema50 = exponential_moving_average(closes, 50)
    facts: list[dict[str, float | None]] = []
    for index, close in enumerate(closes):
        baseline = statistics.fmean(volumes[index - 20 : index]) if index >= 20 else None
        relative_volume = (
            volumes[index] / baseline if baseline is not None and baseline > 0 else None
        )
        facts.append(
            {
                "close_vs_ema20_pct": _percentage(close, ema20[index]),
                "close_vs_ema50_pct": _percentage(close, ema50[index]),
                "ema20_vs_ema50_pct": _percentage(ema20[index], ema50[index]),
                "ema20_slope_5_pct": (
                    _percentage(ema20[index], ema20[index - 5]) if index >= 5 else None
                ),
                "ema50_slope_10_pct": (
                    _percentage(ema50[index], ema50[index - 10]) if index >= 10 else None
                ),
                "relative_volume_20": relative_volume,
                "daily_return_pct": (_percentage(close, closes[index - 1]) if index >= 1 else None),
            }
        )
    return facts, ema20, ema50


def _overlay(
    key: str,
    label: str,
    bars: Sequence[ResearchBar],
    values: Sequence[float | None],
) -> OverlaySeries:
    return OverlaySeries(
        key=key,
        label=label,
        points=tuple(
            OverlayPoint(date=bar.date, value=round(value, 6))
            for bar, value in zip(bars, values, strict=True)
            if value is not None
        ),
    )


def build_condition_timelines(bars: Sequence[ResearchBar]) -> tuple[ConditionTimeline, ...]:
    """Return every state change using only information available at each completed bar."""

    if any(left.date >= right.date for left, right in pairwise(bars)):
        raise ValueError("research bars must be strictly increasing by date")

    facts_by_date, _, _ = _fact_history(bars)
    timelines: list[ConditionTimeline] = []
    for spec in CONDITION_REGISTRY:
        previous_state: ConditionState | None = None
        state_changes: list[ConditionStateChange] = []
        for bar, facts in zip(bars, facts_by_date, strict=True):
            checks = _checks(spec.rules, facts)
            state = _state(checks)
            if state != previous_state:
                state_changes.append(
                    ConditionStateChange(
                        date=bar.date,
                        close=round(float(bar.close), 6),
                        previous_state=previous_state,
                        state=state,
                        checks=checks,
                    )
                )
            previous_state = state
        timelines.append(
            ConditionTimeline(
                key=spec.key,
                version=spec.version,
                state_changes=tuple(state_changes),
            )
        )
    return tuple(timelines)


def build_condition_outcomes(
    bars: Sequence[ResearchBar],
    *,
    benchmark_closes: Mapping[dt.date, float] | None = None,
    horizons: Sequence[int] = DEFAULT_OUTCOME_HORIZONS,
) -> tuple[ConditionOutcome, ...]:
    """Measure later completed-session paths from each observed-state transition.

    Benchmark-relative values are only emitted when both the observation and horizon dates have
    benchmark closes. Missing future bars remain explicitly pending rather than being annualised,
    extrapolated, or silently dropped.
    """

    if any(horizon <= 0 for horizon in horizons):
        raise ValueError("condition outcome horizons must be positive")
    if len(set(horizons)) != len(horizons):
        raise ValueError("condition outcome horizons must be unique")

    timelines = build_condition_timelines(bars)
    indexes = {bar.date: index for index, bar in enumerate(bars)}
    benchmark = benchmark_closes or {}
    outcomes: list[ConditionOutcome] = []
    for timeline in timelines:
        observations = [change for change in timeline.state_changes if change.state == "observed"]
        for observation in observations:
            observed_index = indexes[observation.date]
            reference_close = float(observation.close)
            for horizon in horizons:
                outcome_index = observed_index + horizon
                if outcome_index >= len(bars):
                    outcomes.append(
                        ConditionOutcome(
                            condition_key=timeline.key,
                            condition_version=timeline.version,
                            observed_date=observation.date,
                            reference_close=reference_close,
                            horizon_sessions=horizon,
                            status="pending",
                            outcome_date=None,
                            close_return_pct=None,
                            max_favorable_pct=None,
                            max_adverse_pct=None,
                            benchmark_return_pct=None,
                            excess_return_pct=None,
                        )
                    )
                    continue

                outcome_bar = bars[outcome_index]
                path = bars[observed_index + 1 : outcome_index + 1]
                close_return = _percentage(float(outcome_bar.close), reference_close)
                # Excursion is opportunity/risk relative to the observation close. A path that
                # remains entirely below that close has zero favorable excursion; conversely a
                # path that remains entirely above it has zero adverse excursion.
                max_favorable = max(
                    0.0,
                    *(
                        _percentage(float(path_bar.high), reference_close) or 0.0
                        for path_bar in path
                    ),
                )
                max_adverse = min(
                    0.0,
                    *(
                        _percentage(float(path_bar.low), reference_close) or 0.0
                        for path_bar in path
                    ),
                )
                benchmark_return = _percentage(
                    benchmark.get(outcome_bar.date), benchmark.get(observation.date)
                )
                outcomes.append(
                    ConditionOutcome(
                        condition_key=timeline.key,
                        condition_version=timeline.version,
                        observed_date=observation.date,
                        reference_close=reference_close,
                        horizon_sessions=horizon,
                        status="matured",
                        outcome_date=outcome_bar.date,
                        close_return_pct=_rounded(close_return),
                        max_favorable_pct=_rounded(max_favorable),
                        max_adverse_pct=_rounded(max_adverse),
                        benchmark_return_pct=_rounded(benchmark_return),
                        excess_return_pct=_rounded(
                            close_return - benchmark_return
                            if close_return is not None and benchmark_return is not None
                            else None
                        ),
                    )
                )
    return tuple(outcomes)


def _rounded(value: float | None) -> float | None:
    return round(value, 6) if value is not None else None


def _mean(values: Sequence[float]) -> float | None:
    return _rounded(statistics.fmean(values)) if values else None


def _median(values: Sequence[float]) -> float | None:
    return _rounded(statistics.median(values)) if values else None


def calibrate_condition_outcomes(
    outcomes: Sequence[ConditionOutcome],
) -> tuple[ConditionCalibration, ...]:
    """Aggregate comparable outcomes without mixing condition versions or horizons."""

    groups: dict[tuple[str, str, int], list[ConditionOutcome]] = {}
    for outcome in outcomes:
        groups.setdefault(
            (outcome.condition_key, outcome.condition_version, outcome.horizon_sessions), []
        ).append(outcome)

    calibrations: list[ConditionCalibration] = []
    for (condition_key, condition_version, horizon), group in sorted(groups.items()):
        matured = [outcome for outcome in group if outcome.status == "matured"]
        returns = [
            outcome.close_return_pct for outcome in matured if outcome.close_return_pct is not None
        ]
        benchmark_returns = [
            outcome.benchmark_return_pct
            for outcome in matured
            if outcome.benchmark_return_pct is not None
        ]
        excess_returns = [
            outcome.excess_return_pct
            for outcome in matured
            if outcome.excess_return_pct is not None
        ]
        favorable = [
            outcome.max_favorable_pct
            for outcome in matured
            if outcome.max_favorable_pct is not None
        ]
        adverse = [
            outcome.max_adverse_pct for outcome in matured if outcome.max_adverse_pct is not None
        ]
        calibrations.append(
            ConditionCalibration(
                condition_key=condition_key,
                condition_version=condition_version,
                horizon_sessions=horizon,
                observations=len(group),
                matured=len(matured),
                pending=len(group) - len(matured),
                average_return_pct=_mean(returns),
                median_return_pct=_median(returns),
                positive_rate_pct=(
                    _rounded(sum(value > 0 for value in returns) / len(returns) * 100.0)
                    if returns
                    else None
                ),
                average_benchmark_return_pct=_mean(benchmark_returns),
                median_excess_return_pct=_median(excess_returns),
                benchmark_observations=len(excess_returns),
                average_max_favorable_pct=_mean(favorable),
                average_max_adverse_pct=_mean(adverse),
            )
        )
    return tuple(calibrations)


def build_condition_workbench(bars: Sequence[ResearchBar]) -> ConditionWorkbench:
    """Evaluate the registered conditions at every available point in time."""

    if any(left.date >= right.date for left, right in pairwise(bars)):
        raise ValueError("research bars must be strictly increasing by date")

    facts_by_date, ema20, ema50 = _fact_history(bars)
    timelines = {timeline.key: timeline for timeline in build_condition_timelines(bars)}
    evaluations: list[ConditionEvaluation] = []
    for spec in CONDITION_REGISTRY:
        transitions = [
            ConditionTransition(date=change.date, close=change.close, sequence=index + 1)
            for index, change in enumerate(
                change for change in timelines[spec.key].state_changes if change.state == "observed"
            )
        ]

        latest_checks = (
            _checks(spec.rules, facts_by_date[-1]) if facts_by_date else _checks(spec.rules, {})
        )
        latest_state = _state(latest_checks)
        evaluations.append(
            ConditionEvaluation(
                key=spec.key,
                version=spec.version,
                title=spec.title,
                short_label=spec.short_label,
                category=spec.category,
                state=latest_state,
                summary=_summary(latest_state, latest_checks),
                why_it_matters=spec.why_it_matters,
                limitation=spec.limitation,
                checks=latest_checks,
                transitions=tuple(transitions),
            )
        )

    return ConditionWorkbench(
        methodology_version=METHODOLOGY_VERSION,
        timeframe="1d",
        as_of_date=bars[-1].date if bars else None,
        history_start_date=bars[0].date if bars else None,
        disclaimer=(
            "Completed-session research conditions only. An observation is not a recommendation, "
            "probability estimate, strategy qualification, target, or order."
        ),
        overlays=(
            _overlay("ema20", "EMA20", bars, ema20),
            _overlay("ema50", "EMA50", bars, ema50),
        ),
        conditions=tuple(evaluations),
    )
