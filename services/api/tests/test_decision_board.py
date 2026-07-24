from __future__ import annotations

from types import SimpleNamespace

from api.institutional_research.decision_board import (
    derive_decision_state,
    direction_capabilities,
    discovery_performance,
    price_plan,
)


def test_decision_state_keeps_targets_positions_and_rejections_distinct() -> None:
    rejection = SimpleNamespace(event_type="rejection")

    assert (
        derive_decision_state(target_weight=0.08, has_position=False, snapshot_events=[]) == "ready"
    )
    assert (
        derive_decision_state(
            target_weight=0.08,
            has_position=False,
            snapshot_events=[rejection],
        )
        == "blocked"
    )
    assert (
        derive_decision_state(target_weight=0.08, has_position=True, snapshot_events=[]) == "manage"
    )
    assert derive_decision_state(target_weight=0, has_position=True, snapshot_events=[]) == "exit"
    assert (
        derive_decision_state(target_weight=0, has_position=False, snapshot_events=[]) == "closed"
    )


def test_discovery_performance_reports_current_and_excursions() -> None:
    current, favorable, adverse = discovery_performance(
        [100, 96, 108, 105],
        reference_price=100,
    )

    assert current == 5
    assert favorable == 8
    assert adverse == -4


def test_discovery_performance_fails_closed_without_reference_price() -> None:
    assert discovery_performance([100, 105], reference_price=None) == (None, None, None)
    assert discovery_performance([], reference_price=100) == (None, None, None)


def test_price_plan_uses_fill_cost_for_positions_and_reference_close_before_fill() -> None:
    assert price_plan(
        state="ready",
        as_of_price=100,
        average_cost=None,
        stop_loss=0.10,
    ) == (100, 90, 120)
    assert price_plan(
        state="manage",
        as_of_price=107,
        average_cost=95,
        stop_loss=0.10,
    ) == (95, 85.5, 114)


def test_price_plan_does_not_invent_targets_for_non_entry_states() -> None:
    for state in ("blocked", "exit", "closed"):
        assert price_plan(
            state=state,
            as_of_price=100,
            average_cost=95,
            stop_loss=0.10,
        ) == (None, None, None)


def test_short_capability_fails_closed_without_borrow_contract() -> None:
    us = {item.direction: item for item in direction_capabilities("US")}
    assert us["long"].status == "active"
    assert us["short"].status == "blocked"
    assert "borrow availability" in us["short"].reason
    assert "FINRA daily short volume is not a substitute" in us["short"].reason
