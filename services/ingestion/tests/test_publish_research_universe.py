"""Tests for owner-acknowledged research publication of evaluated symbols."""

from __future__ import annotations

import pytest

from ingestion.publish_research_universe import _args, plan_publication


class _Evidence:
    """Stand-in for a persisted UniverseOnboardingResult row."""

    def __init__(self, code: str, *, passed: bool, failure_reasons: list[str] | None = None):
        self.code = code
        self.required_gates_passed = passed
        self.failure_reasons = failure_reasons or []


def test_fully_passing_symbols_are_published_ready() -> None:
    planned = plan_publication([_Evidence("CPHI", passed=True), _Evidence("VIVK", passed=True)])
    assert sorted(planned["ready"]) == ["CPHI", "VIVK"]
    assert planned["research_only"] == []


def test_marketability_only_failures_open_as_research_only() -> None:
    # Liquidity/price/market-cap failures are marketability, not integrity: research tier.
    planned = plan_publication(
        [_Evidence("TINY", passed=False, failure_reasons=["liquidity", "price_floor"])]
    )
    assert planned["ready"] == []
    assert planned["research_only"] == ["TINY"]


def test_integrity_failures_stay_private() -> None:
    # A hard gate failure (identity/history/freshness) must never be published by this command.
    planned = plan_publication(
        [
            _Evidence("BADID", passed=False, failure_reasons=["stable_identity"]),
            _Evidence("STALE", passed=False, failure_reasons=["freshness", "liquidity"]),
        ]
    )
    assert planned["ready"] == []
    assert planned["research_only"] == []


def test_risk_review_id_is_mandatory() -> None:
    with pytest.raises(SystemExit):
        _args(["--market", "US"])


def test_dry_run_flag_parses() -> None:
    parsed = _args(["--risk-review-id", "owner-ack-1", "--dry-run"])
    assert parsed.dry_run is True
    assert parsed.risk_review_id == "owner-ack-1"
    assert parsed.market == "US"
