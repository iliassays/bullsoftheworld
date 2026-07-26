from __future__ import annotations

import datetime as dt

from research.edge_discovery.former_runner import (
    FormerRunnerSpec,
    RunnerBar,
    control_observations,
    scan_former_runner,
)


def _stak_like(*, probe_multiple: float = 4.0) -> list[RunnerBar]:
    start = dt.date(2026, 1, 1)
    bars = [
        RunnerBar(
            date=start + dt.timedelta(days=index),
            open=2.0,
            high=2.05,
            low=1.95,
            close=2.0,
            volume=300_000,
        )
        for index in range(28)
    ]
    bars[20] = RunnerBar(
        date=bars[20].date,
        open=2.0,
        high=4.4,
        low=2.0,
        close=3.6,
        volume=30_000_000,
    )
    bars[21] = RunnerBar(
        date=bars[21].date,
        open=3.2,
        high=3.3,
        low=1.8,
        close=1.9,
        volume=12_000_000,
    )
    bars[22] = RunnerBar(
        date=bars[22].date,
        open=1.56,
        high=1.65,
        low=1.37,
        close=1.44,
        volume=900_000,
    )
    bars[23] = RunnerBar(
        date=bars[23].date,
        open=1.45,
        high=1.5,
        low=1.2,
        close=1.31,
        volume=300_000 * probe_multiple,
    )
    bars[24] = RunnerBar(
        date=bars[24].date,
        open=1.30,
        high=1.43,
        low=1.18,
        close=1.32,
        volume=300_000 * probe_multiple,
    )
    bars[25] = RunnerBar(
        date=bars[25].date,
        open=1.25,
        high=3.0,
        low=1.17,
        close=2.5,
        volume=20_000_000,
    )
    return bars


def test_stak_sequence_becomes_watch_before_second_expansion() -> None:
    events = scan_former_runner("STAK", _stak_like())

    assert len(events) == 1
    event = events[0]
    assert event.watch_date == _stak_like()[24].date
    assert event.runner_date == _stak_like()[20].date
    assert event.primary_success is True
    assert event.secondary_success is True
    assert event.outcome_complete is True
    assert event.pullback_from_runner_high < -0.60


def test_high_volume_without_repeated_probe_is_not_a_setup() -> None:
    events = scan_former_runner("FAIL", _stak_like(probe_multiple=2.0))

    assert events == []


def test_future_bars_do_not_change_an_existing_watch_classification() -> None:
    original = _stak_like()
    extended = [
        *original,
        RunnerBar(
            date=original[-1].date + dt.timedelta(days=1),
            open=2.5,
            high=8.0,
            low=2.4,
            close=7.0,
            volume=50_000_000,
        ),
    ]

    original_event = scan_former_runner("STAK", original)[0]
    extended_event = scan_former_runner("STAK", extended)[0]

    assert original_event.watch_date == extended_event.watch_date
    assert original_event.runner_date == extended_event.runner_date
    assert original_event.trigger_reference == extended_event.trigger_reference


def test_controls_use_only_requested_dates_and_same_opportunity_definition() -> None:
    bars = _stak_like()
    watch = bars[24].date
    controls = control_observations("STAK", bars, {watch}, FormerRunnerSpec())

    assert len(controls) == 1
    assert controls[0].date == watch
    assert controls[0].primary_success is True


def test_barrier_hit_can_be_known_before_the_outcome_window_finishes() -> None:
    event = scan_former_runner("STAK", _stak_like()[:26])[0]

    assert event.outcome_complete is False
    assert event.primary_success is True
    assert event.secondary_success is True
