from __future__ import annotations

from bulls.analytics.research_strategy import STRATEGIES
from bulls.analytics.strategy_readiness import (
    STRATEGY_READINESS,
    readiness_for_market,
)


def test_every_implemented_strategy_has_a_readiness_entry() -> None:
    implemented = {
        entry.implemented_strategy_key
        for entry in STRATEGY_READINESS.values()
        if entry.implemented_strategy_key is not None
    }
    assert implemented == set(STRATEGIES)


def test_implemented_entries_agree_with_the_registry_market() -> None:
    for entry in STRATEGY_READINESS.values():
        if entry.implemented_strategy_key is None:
            continue
        assert entry.market == STRATEGIES[entry.implemented_strategy_key].market


def test_nothing_short_or_scalp_is_ready() -> None:
    for entry in STRATEGY_READINESS.values():
        if entry.direction in {"short", "long_short"} or entry.horizon == "scalp":
            assert entry.status == "blocked", entry.key


def test_non_ready_entries_state_their_missing_data() -> None:
    for entry in STRATEGY_READINESS.values():
        assert entry.status in {"backtest_ready", "diagnostic_only", "blocked"}
        if entry.status != "backtest_ready":
            assert entry.missing_data, entry.key
            assert entry.rationale


def test_no_strategy_is_backtest_ready_on_current_data() -> None:
    """The 2026-07-24 audit found no strategy with promotion-grade inputs; if data lands,
    flipping a status here must be a deliberate reviewed change, not a drive-by edit."""

    assert all(entry.status != "backtest_ready" for entry in STRATEGY_READINESS.values())


def test_market_filter_is_strict() -> None:
    assert {entry.market for entry in readiness_for_market("DSE")} == {"DSE"}
    assert {entry.market for entry in readiness_for_market("US")} == {"US"}
