from __future__ import annotations

import datetime as dt
from types import SimpleNamespace

from api.institutional_research.decision_board import (
    adjustment_complete,
    derive_decision_state,
    direction_capabilities,
    discovery_performance,
    portfolio_stop_loss,
    price_plan,
)
from bulls.analytics.research_strategy import RISK_POLICIES


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


def test_adjustment_completeness_reports_raw_close_histories() -> None:
    adjusted = SimpleNamespace(adjusted_close=101.5)
    raw = SimpleNamespace(adjusted_close=None)

    assert adjustment_complete([adjusted, adjusted])
    assert not adjustment_complete([adjusted, raw])
    assert not adjustment_complete([])


def test_portfolio_stop_loss_prefers_pinned_mandate_and_falls_back() -> None:
    legacy = SimpleNamespace(configuration={})
    corrupt = SimpleNamespace(configuration={"mandate": {"market": "US"}})

    default_stop = RISK_POLICIES["US"].position_stop_loss
    assert portfolio_stop_loss(legacy, "US") == default_stop
    # An unparseable pinned mandate must fall back rather than crash the archive read.
    assert portfolio_stop_loss(corrupt, "US") == default_stop


def test_price_scale_restatement_guard_detects_split_and_tolerates_noise() -> None:
    from api.institutional_research.portfolio import detect_price_scale_restatement
    from bulls.analytics.research_strategy import StrategyBar, StrategySecurity

    as_of = dt.date(2026, 7, 20)
    bar = StrategyBar(date=as_of, open=10.0, high=10.0, low=10.0, close=10.0, volume=1000)
    security = StrategySecurity(code="SPLIT", sector="Test", cap_tier="test", bars=[bar])

    # Stored at 100.0, reloaded history now says 10.0 for the same session: a 10:1 restatement.
    restated = detect_price_scale_restatement(
        {"SPLIT": {"shares": 50, "average_cost": 95.0, "valuation_close": 100.0}},
        [security],
        as_of=as_of,
    )
    assert restated == ["SPLIT"]

    # Same scale within tolerance: no false alarm.
    unchanged = detect_price_scale_restatement(
        {"SPLIT": {"shares": 50, "average_cost": 95.0, "valuation_close": 10.0005}},
        [security],
        as_of=as_of,
    )
    assert unchanged == []

    # Legacy snapshots without a stored valuation close cannot be checked and must not block.
    legacy = detect_price_scale_restatement(
        {"SPLIT": {"shares": 50, "average_cost": 95.0}},
        [security],
        as_of=as_of,
    )
    assert legacy == []


def test_short_capability_fails_closed_without_borrow_contract() -> None:
    us = {item.direction: item for item in direction_capabilities("US")}
    assert us["long"].status == "active"
    assert us["short"].status == "blocked"
    assert "borrow availability" in us["short"].reason
    assert "FINRA daily short volume is not a substitute" in us["short"].reason
