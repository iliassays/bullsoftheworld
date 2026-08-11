from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

import pytest

from bulls.analytics.research_conditions import (
    build_condition_outcomes,
    build_condition_timelines,
    build_condition_workbench,
    calibrate_condition_outcomes,
)


@dataclass(frozen=True)
class Bar:
    date: dt.date
    open: float
    high: float
    low: float
    close: float
    volume: float


def bars(
    count: int = 80,
    *,
    daily_step: float = 0.15,
    volumes: dict[int, float] | None = None,
) -> list[Bar]:
    volume_overrides = volumes or {}
    output: list[Bar] = []
    for index in range(count):
        close = 100.0 + index * daily_step
        output.append(
            Bar(
                date=dt.date(2026, 1, 1) + dt.timedelta(days=index),
                open=close - 0.1,
                high=close + 0.5,
                low=close - 0.5,
                close=close,
                volume=volume_overrides.get(index, 1_000.0),
            )
        )
    return output


def condition(workbench, key: str):
    return next(item for item in workbench.conditions if item.key == key)


def test_rising_orderly_history_observes_trend_and_pullback_context() -> None:
    result = build_condition_workbench(bars())

    assert condition(result, "trend_alignment").state == "observed"
    assert condition(result, "controlled_pullback_context").state == "observed"
    assert condition(result, "participation_expansion").state == "not_observed"
    assert len(result.overlays[0].points) == 61
    assert len(result.overlays[1].points) == 31


def test_participation_uses_prior_twenty_sessions_and_observes_positive_expansion() -> None:
    history = bars(volumes={79: 2_000.0})
    result = build_condition_workbench(history)
    expansion = condition(result, "participation_expansion")

    assert expansion.state == "observed"
    relative_volume = next(
        check for check in expansion.checks if check.fact_key == "relative_volume_20"
    )
    assert relative_volume.observed == pytest.approx(2.0)
    assert relative_volume.passed is True


def test_short_history_reports_unavailable_instead_of_seeding_indicators() -> None:
    result = build_condition_workbench(bars(12))

    assert all(item.state == "unavailable" for item in result.conditions)
    assert all(not overlay.points for overlay in result.overlays)
    assert "enough completed-session history" in result.conditions[0].summary


def test_future_bars_do_not_change_prior_overlays_or_observation_dates() -> None:
    history = bars(90, volumes={70: 2_000.0, 82: 2_000.0})
    cutoff = history[74].date
    prefix = build_condition_workbench(history[:75])
    full = build_condition_workbench(history)

    for prefix_overlay, full_overlay in zip(prefix.overlays, full.overlays, strict=True):
        assert prefix_overlay.points == tuple(
            point for point in full_overlay.points if point.date <= cutoff
        )
    for prefix_condition, full_condition in zip(prefix.conditions, full.conditions, strict=True):
        assert prefix_condition.transitions == tuple(
            transition for transition in full_condition.transitions if transition.date <= cutoff
        )


def test_observation_transition_is_recorded_once_per_episode() -> None:
    history = bars(90, volumes={70: 2_000.0, 72: 2_000.0})
    result = build_condition_workbench(history)
    transitions = condition(result, "participation_expansion").transitions

    assert [transition.sequence for transition in transitions] == [1, 2]
    assert [transition.date for transition in transitions] == [history[70].date, history[72].date]


def test_timeline_records_state_changes_with_point_in_time_checks() -> None:
    history = bars(75, volumes={70: 2_000.0})
    timeline = next(
        item for item in build_condition_timelines(history) if item.key == "participation_expansion"
    )

    assert [change.state for change in timeline.state_changes[-3:]] == [
        "not_observed",
        "observed",
        "not_observed",
    ]
    assert timeline.state_changes[-2].date == history[70].date
    assert next(
        check
        for check in timeline.state_changes[-2].checks
        if check.fact_key == "relative_volume_20"
    ).observed == pytest.approx(2.0)


def test_outcomes_start_after_observation_close_without_lookahead() -> None:
    history = bars(80, volumes={70: 2_000.0})
    outcomes = [
        item
        for item in build_condition_outcomes(history, horizons=(1, 5, 20))
        if item.condition_key == "participation_expansion"
        and item.observed_date == history[70].date
    ]

    one_session = next(item for item in outcomes if item.horizon_sessions == 1)
    assert one_session.status == "matured"
    assert one_session.outcome_date == history[71].date
    assert one_session.close_return_pct == pytest.approx(
        (history[71].close / history[70].close - 1.0) * 100.0,
        abs=1e-6,
    )
    assert next(item for item in outcomes if item.horizon_sessions == 20).status == "pending"


def test_future_bars_mature_pending_outcome_without_changing_observation() -> None:
    history = bars(80, volumes={70: 2_000.0})
    prefix = build_condition_outcomes(history[:75], horizons=(5,))
    full = build_condition_outcomes(history, horizons=(5,))
    prefix_outcome = next(
        item
        for item in prefix
        if item.condition_key == "participation_expansion"
        and item.observed_date == history[70].date
    )
    full_outcome = next(
        item
        for item in full
        if item.condition_key == "participation_expansion"
        and item.observed_date == history[70].date
    )

    assert prefix_outcome.status == "pending"
    assert full_outcome.status == "matured"
    assert prefix_outcome.observed_date == full_outcome.observed_date
    assert prefix_outcome.reference_close == full_outcome.reference_close


def test_excursions_are_bounded_at_zero_when_the_entire_path_moves_one_way() -> None:
    history = bars(72, volumes={70: 2_000.0})
    observed = history[70]
    history[71] = Bar(
        date=history[71].date,
        open=observed.close - 2.0,
        high=observed.close - 1.0,
        low=observed.close - 3.0,
        close=observed.close - 2.0,
        volume=1_000.0,
    )
    outcome = next(
        item
        for item in build_condition_outcomes(history, horizons=(1,))
        if item.condition_key == "participation_expansion"
        and item.observed_date == observed.date
    )

    assert outcome.max_favorable_pct == 0.0
    assert outcome.max_adverse_pct is not None and outcome.max_adverse_pct < 0


def test_benchmark_excess_and_calibration_are_kept_separate() -> None:
    history = bars(80, volumes={70: 2_000.0, 72: 2_000.0})
    benchmark = {bar.date: 1_000.0 + index for index, bar in enumerate(history)}
    outcomes = build_condition_outcomes(
        history,
        benchmark_closes=benchmark,
        horizons=(1,),
    )
    expansion = [item for item in outcomes if item.condition_key == "participation_expansion"]
    calibration = next(
        item
        for item in calibrate_condition_outcomes(expansion)
        if item.condition_key == "participation_expansion"
    )

    assert calibration.observations == 2
    assert calibration.matured == 2
    assert calibration.pending == 0
    assert calibration.benchmark_observations == 2
    assert calibration.median_excess_return_pct is not None


def test_outcome_horizons_must_be_positive_and_unique() -> None:
    with pytest.raises(ValueError, match="positive"):
        build_condition_outcomes(bars(), horizons=(0,))
    with pytest.raises(ValueError, match="unique"):
        build_condition_outcomes(bars(), horizons=(1, 1))


def test_rejects_non_monotonic_history() -> None:
    history = bars(3)
    history[2] = Bar(**{**history[2].__dict__, "date": history[1].date})

    with pytest.raises(ValueError, match="strictly increasing"):
        build_condition_workbench(history)
