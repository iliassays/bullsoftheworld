"""Locked DSE compression-breakout experiment.

This module turns versioned ``squeeze-monitor-v3`` confirmation transitions into a causal
target-weight schedule. It owns no persistence and performs no execution. The portfolio engine
still applies the investment mandate, next-session fills, transaction costs, ADV participation,
position stops, and the drawdown ladder.

Historical reconstructions may be supplied for diagnostics. A forward shadow book must pass
``evidence_mode="forward"`` and a registration-date floor so hindsight rows can never become
paper targets.
"""

from __future__ import annotations

import bisect
import datetime as dt
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field

METHODOLOGY_VERSION = "dse-compression-breakout-20d-v1"
SOURCE_METHODOLOGY_VERSION = "squeeze-monitor-v3"
SOURCE_FAMILY = "compression_breakout"


class CompressionBreakoutObservation(BaseModel):
    """One archived setup state as it was knowable after a completed DSE session."""

    code: str = Field(min_length=1, max_length=16)
    as_of_date: dt.date
    state: str
    previous_state: str | None = None
    evidence_mode: Literal["forward", "reconstructed"]
    methodology_version: str
    setup_price: float | None = Field(default=None, gt=0)
    trigger_price: float | None = Field(default=None, gt=0)
    invalidation_price: float | None = Field(default=None, gt=0)
    risk_per_share: float | None = Field(default=None, gt=0)
    average_daily_value_mn: float | None = Field(default=None, ge=0)


class CompressionBreakoutPolicy(BaseModel):
    """Frozen portfolio-construction priors for the first forward experiment."""

    holding_sessions: int = Field(default=20, ge=1, le=60)
    maximum_positions: int = Field(default=8, ge=1, le=20)
    maximum_gross_weight: float = Field(default=0.60, gt=0, le=1)
    maximum_position_weight: float = Field(default=0.12, gt=0, le=1)
    risk_budget_per_position: float = Field(default=0.0075, gt=0, le=0.02)
    minimum_position_weight: float = Field(default=0.02, gt=0, le=0.12)
    minimum_average_daily_value_mn: float = Field(default=2.0, ge=0)
    maximum_stop_distance_pct: float = Field(default=0.15, gt=0, le=0.30)


@dataclass(frozen=True, slots=True)
class ScheduleRejection:
    date: dt.date
    code: str
    reason: str


@dataclass(frozen=True, slots=True)
class CompressionBreakoutSchedule:
    target_weights: dict[dt.date, dict[str, float]]
    confirmations: int
    accepted_entries: int
    exits: int
    rejections: tuple[ScheduleRejection, ...] = ()


@dataclass(slots=True)
class _Holding:
    code: str
    signal_index: int
    target_weight: float


def _confirmation(row: CompressionBreakoutObservation) -> bool:
    return row.state == "confirmed" and row.previous_state != "confirmed"


def _position_weight(
    row: CompressionBreakoutObservation,
    policy: CompressionBreakoutPolicy,
) -> tuple[float | None, str | None]:
    if (
        row.average_daily_value_mn is None
        or row.average_daily_value_mn < policy.minimum_average_daily_value_mn
    ):
        return None, "average_daily_value_below_floor"
    reference = row.trigger_price or row.setup_price
    if reference is None or row.risk_per_share is None:
        return None, "risk_geometry_missing"
    stop_distance = row.risk_per_share / reference
    if stop_distance <= 0 or stop_distance > policy.maximum_stop_distance_pct:
        return None, "stop_distance_outside_registered_range"
    weight = min(
        policy.maximum_position_weight,
        policy.risk_budget_per_position / stop_distance,
    )
    if weight < policy.minimum_position_weight:
        return None, "risk_sized_weight_below_minimum"
    return round(weight, 8), None


def build_compression_breakout_schedule(
    *,
    observations: list[CompressionBreakoutObservation],
    sessions: list[dt.date],
    policy: CompressionBreakoutPolicy | None = None,
    evidence_mode: Literal["forward", "reconstructed"] | None = None,
    signal_not_before: dt.date | None = None,
) -> CompressionBreakoutSchedule:
    """Build causal target changes from first confirmation transitions.

    Signals are observed after session ``T`` and therefore become targets on ``T`` for execution
    no earlier than ``T+1``. A target is removed after 20 completed holding sessions or after a
    recorded terminal failure/exhaustion, again for execution on the following session.
    """

    frozen = policy or CompressionBreakoutPolicy()
    ordered_sessions = sorted(set(sessions))
    session_index = {value: index for index, value in enumerate(ordered_sessions)}
    eligible_rows = [
        row
        for row in observations
        if row.methodology_version == SOURCE_METHODOLOGY_VERSION
        and row.as_of_date in session_index
        and (evidence_mode is None or row.evidence_mode == evidence_mode)
        and (signal_not_before is None or row.as_of_date >= signal_not_before)
    ]
    rows_by_date: dict[dt.date, list[CompressionBreakoutObservation]] = {}
    for row in eligible_rows:
        rows_by_date.setdefault(row.as_of_date, []).append(row)

    active: dict[str, _Holding] = {}
    schedule: dict[dt.date, dict[str, float]] = {}
    rejections: list[ScheduleRejection] = []
    confirmations = 0
    accepted_entries = 0
    exits = 0

    for date in ordered_sessions:
        index = session_index[date]
        changed = False

        expired = [
            code
            for code, holding in active.items()
            if index >= holding.signal_index + frozen.holding_sessions
        ]
        for code in sorted(expired):
            active.pop(code)
            exits += 1
            changed = True

        rows = rows_by_date.get(date, [])
        terminal_codes = {
            row.code for row in rows if row.state in {"failed", "exhausted"} and row.code in active
        }
        for code in sorted(terminal_codes):
            active.pop(code)
            exits += 1
            changed = True

        candidates = [row for row in rows if _confirmation(row)]
        confirmations += len(candidates)
        # Liquidity is an execution-quality rank, not an alpha score. The tie-break is stable.
        candidates.sort(
            key=lambda row: (
                -(row.average_daily_value_mn or 0.0),
                row.code,
            )
        )
        for row in candidates:
            if row.code in active:
                rejections.append(ScheduleRejection(date, row.code, "position_already_active"))
                continue
            if len(active) >= frozen.maximum_positions:
                rejections.append(ScheduleRejection(date, row.code, "position_limit"))
                continue
            weight, reason = _position_weight(row, frozen)
            if weight is None:
                rejections.append(ScheduleRejection(date, row.code, reason or "risk_gate"))
                continue
            remaining_gross = frozen.maximum_gross_weight - sum(
                holding.target_weight for holding in active.values()
            )
            weight = min(weight, remaining_gross)
            if weight < frozen.minimum_position_weight:
                rejections.append(ScheduleRejection(date, row.code, "gross_exposure_limit"))
                continue
            active[row.code] = _Holding(
                code=row.code,
                signal_index=index,
                target_weight=round(weight, 8),
            )
            accepted_entries += 1
            changed = True

        if changed:
            schedule[date] = {
                code: holding.target_weight for code, holding in sorted(active.items())
            }

    return CompressionBreakoutSchedule(
        target_weights=schedule,
        confirmations=confirmations,
        accepted_entries=accepted_entries,
        exits=exits,
        rejections=tuple(rejections),
    )


def delay_weight_schedule(
    schedule: dict[dt.date, dict[str, float]],
    *,
    sessions: list[dt.date],
    delay_sessions: int,
) -> dict[dt.date, dict[str, float]]:
    """Move every target change later by completed sessions for an event-timing placebo."""

    if delay_sessions < 1:
        raise ValueError("delay_sessions must be at least one")
    ordered = sorted(set(sessions))
    delayed: dict[dt.date, dict[str, float]] = {}
    for date, weights in sorted(schedule.items()):
        index = bisect.bisect_left(ordered, date)
        destination = index + delay_sessions
        if index < len(ordered) and ordered[index] == date and destination < len(ordered):
            delayed[ordered[destination]] = weights.copy()
    return delayed
