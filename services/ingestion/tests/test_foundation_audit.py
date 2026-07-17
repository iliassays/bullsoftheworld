from __future__ import annotations

import datetime as dt

from ingestion.foundation_audit import health_issues


def _snapshot(market: str = "US") -> dict:
    date = dt.date(2026, 7, 16)
    return {
        "market": market,
        "symbols": {"ready": 100},
        "identity": {
            "security_id_mismatches": 0,
            "eligible_listings_missing_symbol": 0,
            "ready_symbols_missing_active_master": 0,
        }
        if market == "US"
        else None,
        "market_data": {
            "bars": {
                "rows": 1_000,
                "latest_date": date,
                "ready_coverage_ratio": 0.98,
            },
            "analytics": {
                "rows": 100,
                "fingerprinted": 100,
                "latest_date": date,
                "unclassified_cap_tier": 0,
            },
        },
        "onboarding": {
            "stale_running": 0,
            "recent_failure_reasons": {},
        },
        "sources": (
            {"sec_financial_facts": 1_000} if market == "US" else {"company_profiles": 100}
        ),
        "lineage": {
            "unknown_code_versions_by_dataset": {},
            "daily_bar_observation_ratio": 1.0,
            "security_listing_observations": 100 if market == "US" else 0,
            "sec_fact_observations": 1_000 if market == "US" else 0,
            "company_data_observations": 1_000 if market == "DSE" else 0,
        },
    }


def test_healthy_market_has_no_dynamic_foundation_issues() -> None:
    assert health_issues(_snapshot()) == []


def test_foundation_audit_fails_closed_on_coverage_identity_and_stale_runs() -> None:
    snapshot = _snapshot()
    snapshot["market_data"]["bars"]["ready_coverage_ratio"] = 0.5
    snapshot["market_data"]["analytics"]["latest_date"] = dt.date(2026, 7, 15)
    snapshot["identity"]["security_id_mismatches"] = 1
    snapshot["onboarding"]["stale_running"] = 1

    issues = health_issues(snapshot)

    assert {item["code"] for item in issues} == {
        "latest_bar_coverage_below_90pct",
        "analytics_not_aligned_to_latest_bar",
        "security_identity_drift",
        "stale_onboarding_run",
    }
    assert {item["severity"] for item in issues} == {"critical"}


def test_foundation_audit_separates_research_warnings_from_critical_health() -> None:
    snapshot = _snapshot("DSE")
    snapshot["market_data"]["analytics"]["unclassified_cap_tier"] = 7
    snapshot["onboarding"]["recent_failure_reasons"] = {"sec_facts": 3}

    issues = health_issues(snapshot)

    assert [(item["severity"], item["code"]) for item in issues] == [
        ("warning", "recent_gate_failures_need_disposition"),
        ("warning", "unclassified_market_cap"),
    ]


def test_foundation_audit_rejects_incomplete_revision_ledger() -> None:
    snapshot = _snapshot()
    snapshot["lineage"]["daily_bar_observation_ratio"] = 0.5
    snapshot["lineage"]["security_listing_observations"] = 0
    snapshot["lineage"]["sec_fact_observations"] = 0
    snapshot["market_data"]["analytics"]["fingerprinted"] = 20

    assert {item["code"] for item in health_issues(snapshot)} == {
        "bar_revision_ledger_incomplete",
        "analytics_inputs_not_fingerprinted",
        "security_listing_history_missing",
        "sec_fact_revision_history_missing",
    }


def test_foundation_audit_rejects_unknown_source_release_lineage() -> None:
    snapshot = _snapshot()
    snapshot["lineage"]["unknown_code_versions_by_dataset"] = {
        "daily_bars": 100,
        "sec_company_facts": 3,
    }

    issues = health_issues(snapshot)

    assert [(item["severity"], item["code"]) for item in issues] == [
        ("critical", "source_release_lineage_unknown")
    ]
