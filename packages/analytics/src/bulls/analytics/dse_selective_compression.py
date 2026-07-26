"""Selective DSE compression-breakout experiment.

The broad compression taxonomy is a discovery surface, not an alpha ranking. This module adds a
frozen, point-in-time quality gate and ranking layer for a separate strategy trial. Features use
only completed bars through the signal session and the independently stored DSEX close series.
"""

from __future__ import annotations

import bisect
import datetime as dt
import statistics
from dataclasses import dataclass
from itertools import pairwise
from typing import Any, Literal

from pydantic import BaseModel, Field

from bulls.analytics.dse_compression_breakout import (
    SOURCE_METHODOLOGY_VERSION,
    CompressionBreakoutObservation,
    CompressionBreakoutPolicy,
    ScheduleRejection,
)
from bulls.analytics.research_strategy import EquityPoint, StrategyBar

METHODOLOGY_VERSION = "dse-selective-compression-v1"


class SelectiveCompressionFeatures(BaseModel):
    """Signal-session features whose timestamps are no later than the archived confirmation."""

    relative_strength_63: float
    relative_volume_20: float = Field(ge=0)
    base_volume_contraction: float = Field(ge=0)
    cmf_20: float = Field(ge=-1, le=1)
    obv_flow_20: float = Field(ge=-1, le=1)
    close_location: float = Field(ge=0, le=1)
    extension_from_trigger_pct: float
    extension_atr: float
    stop_distance_pct: float = Field(gt=0)
    stock_above_sma_50: bool
    benchmark_above_sma_50: bool


class SelectiveCompressionObservation(CompressionBreakoutObservation):
    features: SelectiveCompressionFeatures | None = None


class SelectiveCompressionPolicy(CompressionBreakoutPolicy):
    """Preregistered selectivity and portfolio-capacity constraints."""

    holding_sessions: int = 20
    maximum_positions: int = 3
    maximum_gross_weight: float = 0.30
    maximum_position_weight: float = 0.10
    risk_budget_per_position: float = 0.005
    minimum_position_weight: float = 0.02
    minimum_average_daily_value_mn: float = 5.0
    minimum_stop_distance_pct: float = 0.025
    maximum_stop_distance_pct: float = 0.10
    minimum_relative_strength_63: float = 0.0
    minimum_relative_volume_20: float = 1.5
    maximum_relative_volume_20: float = 4.0
    maximum_base_volume_contraction: float = 0.90
    minimum_cmf_20: float = 0.0
    minimum_obv_flow_20: float = 0.0
    minimum_close_location: float = 0.60
    maximum_extension_from_trigger_pct: float = 0.03
    maximum_extension_atr: float = 1.0
    require_stock_above_sma_50: bool = True
    require_benchmark_above_sma_50: bool = True


@dataclass(frozen=True, slots=True)
class SelectiveCompressionSchedule:
    target_weights: dict[dt.date, dict[str, float]]
    confirmations: int
    quality_qualified: int
    accepted_entries: int
    exits: int
    rejections: tuple[ScheduleRejection, ...] = ()


class ChronologicalRelativeSlice(BaseModel):
    """Net and benchmark performance in one untouched chronological partition."""

    label: Literal["full", "validation", "test"]
    start_date: dt.date | None
    end_date: dt.date | None
    sessions: int
    net_return_pct: float | None
    benchmark_return_pct: float | None
    excess_return_pct: float | None


class SelectiveCompressionAdmission(BaseModel):
    """Fail-closed decision for starting a diagnostic forward observation."""

    passed: bool
    checks: dict[str, bool]
    failed_checks: list[str]
    chronological_slices: list[ChronologicalRelativeSlice]
    accepted_entries: int
    buy_executions: int
    stress_30bps_return_pct: float | None
    deflated_sharpe_confidence: float | None


@dataclass(slots=True)
class _Holding:
    signal_index: int
    target_weight: float


def _atr(bars: list[StrategyBar], period: int = 14) -> float | None:
    if len(bars) < period + 1:
        return None
    ranges = []
    for index in range(len(bars) - period, len(bars)):
        bar = bars[index]
        previous_close = bars[index - 1].close
        ranges.append(
            max(
                bar.high - bar.low,
                abs(bar.high - previous_close),
                abs(bar.low - previous_close),
            )
        )
    return statistics.fmean(ranges)


def _cmf(bars: list[StrategyBar]) -> float | None:
    total_volume = sum(bar.volume for bar in bars)
    if total_volume <= 0:
        return None
    money_flow = 0.0
    for bar in bars:
        spread = bar.high - bar.low
        multiplier = ((bar.close - bar.low) - (bar.high - bar.close)) / spread if spread > 0 else 0
        money_flow += multiplier * bar.volume
    return money_flow / total_volume


def _obv_flow(bars: list[StrategyBar]) -> float | None:
    if len(bars) < 2:
        return None
    total_volume = sum(bar.volume for bar in bars[1:])
    if total_volume <= 0:
        return None
    signed_volume = sum(
        (1 if bar.close > previous.close else -1 if bar.close < previous.close else 0) * bar.volume
        for previous, bar in pairwise(bars)
    )
    return signed_volume / total_volume


def build_selective_features(
    *,
    bars: list[StrategyBar],
    benchmark_closes: list[tuple[dt.date, float]],
    as_of: dt.date,
    trigger_price: float | None,
    invalidation_price: float | None,
) -> SelectiveCompressionFeatures | None:
    """Build a causal feature snapshot; insufficient evidence means abstention."""

    bar_index = bisect.bisect_right([bar.date for bar in bars], as_of)
    history = bars[:bar_index]
    benchmark_index = bisect.bisect_right(
        [date for date, _close in benchmark_closes],
        as_of,
    )
    benchmark_history = benchmark_closes[:benchmark_index]
    if (
        len(history) < 64
        or len(benchmark_history) < 64
        or trigger_price is None
        or invalidation_price is None
        or trigger_price <= invalidation_price
    ):
        return None

    signal = history[-1]
    prior_20 = history[-21:-1]
    recent_base = history[-6:-1]
    earlier_base = history[-21:-6]
    average_volume = statistics.fmean(bar.volume for bar in prior_20)
    earlier_volume = statistics.fmean(bar.volume for bar in earlier_base)
    atr = _atr(history)
    if average_volume <= 0 or earlier_volume <= 0 or atr is None or atr <= 0:
        return None

    benchmark_latest = benchmark_history[-1][1]
    stock_reference = history[-64]
    benchmark_reference_index = bisect.bisect_right(
        [date for date, _close in benchmark_history],
        stock_reference.date,
    )
    if benchmark_reference_index == 0:
        return None
    benchmark_prior = benchmark_history[benchmark_reference_index - 1][1]
    if benchmark_prior <= 0:
        return None
    stock_return = signal.close / stock_reference.close - 1
    benchmark_return = benchmark_latest / benchmark_prior - 1
    signal_spread = signal.high - signal.low
    prior_cmf = _cmf(prior_20)
    prior_obv = _obv_flow(prior_20)
    if prior_cmf is None or prior_obv is None:
        return None

    return SelectiveCompressionFeatures(
        relative_strength_63=stock_return - benchmark_return,
        relative_volume_20=signal.volume / average_volume,
        base_volume_contraction=statistics.fmean(bar.volume for bar in recent_base)
        / earlier_volume,
        cmf_20=prior_cmf,
        obv_flow_20=prior_obv,
        close_location=(signal.close - signal.low) / signal_spread if signal_spread > 0 else 0.5,
        extension_from_trigger_pct=signal.close / trigger_price - 1,
        extension_atr=max(0.0, signal.close - trigger_price) / atr,
        stop_distance_pct=(trigger_price - invalidation_price) / trigger_price,
        stock_above_sma_50=signal.close > statistics.fmean(bar.close for bar in history[-50:]),
        benchmark_above_sma_50=benchmark_latest
        > statistics.fmean(close for _date, close in benchmark_history[-50:]),
    )


def _quality_score(
    row: SelectiveCompressionObservation,
    policy: SelectiveCompressionPolicy,
) -> tuple[float | None, str | None]:
    features = row.features
    if (
        row.average_daily_value_mn is None
        or row.average_daily_value_mn < policy.minimum_average_daily_value_mn
    ):
        return None, "average_daily_value_below_selective_floor"
    if features is None:
        return None, "selective_features_unavailable"
    gates = (
        (
            features.stop_distance_pct < policy.minimum_stop_distance_pct,
            "stop_distance_too_tight",
        ),
        (
            features.stop_distance_pct > policy.maximum_stop_distance_pct,
            "stop_distance_too_wide",
        ),
        (
            features.relative_strength_63 < policy.minimum_relative_strength_63,
            "relative_strength_below_dsex",
        ),
        (
            features.relative_volume_20 < policy.minimum_relative_volume_20,
            "breakout_volume_too_low",
        ),
        (
            features.relative_volume_20 > policy.maximum_relative_volume_20,
            "breakout_volume_exhausted",
        ),
        (
            features.base_volume_contraction > policy.maximum_base_volume_contraction,
            "base_volume_not_contracting",
        ),
        (features.cmf_20 < policy.minimum_cmf_20, "cmf_distribution"),
        (features.obv_flow_20 < policy.minimum_obv_flow_20, "obv_distribution"),
        (
            features.close_location < policy.minimum_close_location,
            "weak_breakout_close",
        ),
        (
            features.extension_from_trigger_pct > policy.maximum_extension_from_trigger_pct,
            "price_extended_from_trigger",
        ),
        (
            features.extension_atr > policy.maximum_extension_atr,
            "price_extended_by_atr",
        ),
        (
            policy.require_stock_above_sma_50 and not features.stock_above_sma_50,
            "stock_below_sma_50",
        ),
        (
            policy.require_benchmark_above_sma_50 and not features.benchmark_above_sma_50,
            "dsex_below_sma_50",
        ),
    )
    for rejected, reason in gates:
        if rejected:
            return None, reason

    volume_quality = 1 - abs(features.relative_volume_20 - 2.5) / 1.5
    score = (
        min(features.relative_strength_63 / 0.20, 1.0) * 30
        + min(features.cmf_20 / 0.25, 1.0) * 15
        + min(features.obv_flow_20 / 0.50, 1.0) * 15
        + max(0.0, volume_quality) * 15
        + min(max((0.90 - features.base_volume_contraction) / 0.50, 0.0), 1.0) * 10
        + min(max(1 - features.extension_atr, 0.0), 1.0) * 10
        + min(max((features.close_location - 0.60) / 0.40, 0.0), 1.0) * 5
    )
    return round(score, 6), None


def _risk_weight(
    row: SelectiveCompressionObservation,
    policy: SelectiveCompressionPolicy,
) -> float:
    features = row.features
    if features is None:
        return 0.0
    return min(
        policy.maximum_position_weight,
        policy.risk_budget_per_position / features.stop_distance_pct,
    )


def _relative_slice(
    label: Literal["full", "validation", "test"],
    points: list[EquityPoint],
) -> ChronologicalRelativeSlice:
    if len(points) < 2 or points[0].nav <= 0 or points[0].benchmark <= 0:
        return ChronologicalRelativeSlice(
            label=label,
            start_date=points[0].date if points else None,
            end_date=points[-1].date if points else None,
            sessions=len(points),
            net_return_pct=None,
            benchmark_return_pct=None,
            excess_return_pct=None,
        )
    net = (points[-1].nav / points[0].nav - 1) * 100
    benchmark = (points[-1].benchmark / points[0].benchmark - 1) * 100
    return ChronologicalRelativeSlice(
        label=label,
        start_date=points[0].date,
        end_date=points[-1].date,
        sessions=len(points),
        net_return_pct=round(net, 6),
        benchmark_return_pct=round(benchmark, 6),
        excess_return_pct=round(net - benchmark, 6),
    )


def chronological_relative_slices(
    equity_curve: list[EquityPoint],
) -> list[ChronologicalRelativeSlice]:
    """Return fixed 60/20/20 partitions without fitting thresholds to any partition."""

    points = sorted(equity_curve, key=lambda point: point.date)
    split_1 = max(2, round(len(points) * 0.60))
    split_2 = max(split_1 + 1, round(len(points) * 0.80))
    return [
        _relative_slice("full", points),
        _relative_slice("validation", points[split_1 - 1 : split_2]),
        _relative_slice("test", points[split_2 - 1 :]),
    ]


def evaluate_selective_compression_admission(
    *,
    equity_curve: list[EquityPoint],
    maximum_drawdown_pct: float | None,
    accepted_entries: int,
    buy_executions: int,
    benchmark_valid: bool,
    stress_30bps_return_pct: float | None,
    comparator_summary: dict[str, dict[str, Any]],
    deflated_sharpe_summary: dict[str, Any] | None,
) -> SelectiveCompressionAdmission:
    """Require repeatable, cost-aware evidence before opening even a diagnostic paper book."""

    slices = chronological_relative_slices(equity_curve)
    by_label = {item.label: item for item in slices}
    full = by_label["full"]
    validation = by_label["validation"]
    test = by_label["test"]
    comparator_checks = [
        bool(item.get("strategy_beats_realistic")) and bool(item.get("strategy_beats_stress_30bps"))
        for item in comparator_summary.values()
    ]
    checks = {
        "minimum_12_qualified_entries": accepted_entries >= 12,
        "minimum_10_executed_entries": buy_executions >= 10,
        "independent_benchmark_complete": benchmark_valid,
        "positive_full_net_return": (full.net_return_pct or 0) > 0,
        "positive_full_excess_return": (full.excess_return_pct or 0) > 0,
        "positive_validation_excess_return": (validation.excess_return_pct or 0) > 0,
        "positive_test_excess_return": (test.excess_return_pct or 0) > 0,
        "validation_has_30_sessions": validation.sessions >= 30,
        "test_has_30_sessions": test.sessions >= 30,
        "maximum_drawdown_within_8_pct": (
            maximum_drawdown_pct is not None and maximum_drawdown_pct <= 8.0
        ),
        "positive_after_30bps_cost": (
            stress_30bps_return_pct is not None and stress_30bps_return_pct > 0
        ),
        "beats_all_registered_nulls": bool(comparator_checks) and all(comparator_checks),
        "deflated_sharpe_confidence_at_least_80_pct": (
            deflated_sharpe_summary is not None
            and float(deflated_sharpe_summary.get("deflated_sharpe", 0)) >= 0.80
        ),
    }
    failed = [key for key, passed in checks.items() if not passed]
    deflated_sharpe_confidence = (
        float(deflated_sharpe_summary["deflated_sharpe"])
        if deflated_sharpe_summary is not None
        and deflated_sharpe_summary.get("deflated_sharpe") is not None
        else None
    )
    return SelectiveCompressionAdmission(
        passed=not failed,
        checks=checks,
        failed_checks=failed,
        chronological_slices=slices,
        accepted_entries=accepted_entries,
        buy_executions=buy_executions,
        stress_30bps_return_pct=stress_30bps_return_pct,
        deflated_sharpe_confidence=deflated_sharpe_confidence,
    )


def build_selective_compression_schedule(
    *,
    observations: list[SelectiveCompressionObservation],
    sessions: list[dt.date],
    policy: SelectiveCompressionPolicy | None = None,
    evidence_mode: str | None = None,
    signal_not_before: dt.date | None = None,
) -> SelectiveCompressionSchedule:
    """Select only the strongest qualified confirmations under a frozen three-slot mandate."""

    frozen = policy or SelectiveCompressionPolicy()
    ordered_sessions = sorted(set(sessions))
    session_index = {value: index for index, value in enumerate(ordered_sessions)}
    rows_by_date: dict[dt.date, list[SelectiveCompressionObservation]] = {}
    for row in observations:
        if (
            row.methodology_version == SOURCE_METHODOLOGY_VERSION
            and row.as_of_date in session_index
            and (evidence_mode is None or row.evidence_mode == evidence_mode)
            and (signal_not_before is None or row.as_of_date >= signal_not_before)
        ):
            rows_by_date.setdefault(row.as_of_date, []).append(row)

    active: dict[str, _Holding] = {}
    schedule: dict[dt.date, dict[str, float]] = {}
    rejections: list[ScheduleRejection] = []
    confirmations = 0
    quality_qualified = 0
    accepted_entries = 0
    exits = 0

    for date in ordered_sessions:
        index = session_index[date]
        changed = False
        for code in sorted(
            code
            for code, holding in active.items()
            if index >= holding.signal_index + frozen.holding_sessions
        ):
            active.pop(code)
            exits += 1
            changed = True

        rows = rows_by_date.get(date, [])
        for code in sorted(
            {
                row.code
                for row in rows
                if row.state in {"failed", "exhausted"} and row.code in active
            }
        ):
            active.pop(code)
            exits += 1
            changed = True

        candidates = [
            row for row in rows if row.state == "confirmed" and row.previous_state != "confirmed"
        ]
        confirmations += len(candidates)
        ranked: list[tuple[float, float, str, SelectiveCompressionObservation]] = []
        for row in candidates:
            score, reason = _quality_score(row, frozen)
            if score is None:
                rejections.append(ScheduleRejection(date, row.code, reason or "quality_gate"))
                continue
            quality_qualified += 1
            ranked.append((score, row.average_daily_value_mn or 0.0, row.code, row))
        ranked.sort(key=lambda item: (-item[0], -item[1], item[2]))

        for _score, _liquidity, _code, row in ranked:
            if row.code in active:
                rejections.append(ScheduleRejection(date, row.code, "position_already_active"))
                continue
            if len(active) >= frozen.maximum_positions:
                rejections.append(ScheduleRejection(date, row.code, "position_limit"))
                continue
            weight = _risk_weight(row, frozen)
            remaining = frozen.maximum_gross_weight - sum(
                holding.target_weight for holding in active.values()
            )
            weight = min(weight, remaining)
            if weight < frozen.minimum_position_weight:
                rejections.append(ScheduleRejection(date, row.code, "risk_weight_below_minimum"))
                continue
            active[row.code] = _Holding(index, round(weight, 8))
            accepted_entries += 1
            changed = True

        if changed:
            schedule[date] = {
                code: holding.target_weight for code, holding in sorted(active.items())
            }

    return SelectiveCompressionSchedule(
        target_weights=schedule,
        confirmations=confirmations,
        quality_qualified=quality_qualified,
        accepted_entries=accepted_entries,
        exits=exits,
        rejections=tuple(rejections),
    )
