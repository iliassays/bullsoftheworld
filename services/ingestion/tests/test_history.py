from __future__ import annotations

import json

import pytest
from sqlalchemy.dialects import postgresql

from ingestion.history import (
    _active_symbol_stmt,
    _default_days,
    _load_cohort,
    _mode_market,
    _select_codes,
)


def test_mode_market_keeps_legacy_dse_cli_shape() -> None:
    assert _mode_market("backfill", None) == ("DSE", "backfill")
    assert _mode_market("daily", "US") == ("US", "daily")
    assert _mode_market("US", "backfill") == ("US", "backfill")


def test_us_backfill_defaults_to_ten_year_window() -> None:
    assert 3650 <= _default_days("US", "backfill") <= 3654
    assert _default_days("US", "daily") == 14


def test_select_codes_filters_then_slices_stably() -> None:
    codes = ["AAPL", "BRK.B", "MSFT", "NVDA", "TSLA"]
    assert _select_codes(codes, offset=1, limit=2) == ["BRK.B", "MSFT"]
    assert _select_codes(codes, wanted=["tsla", "aapl"], limit=5) == ["AAPL", "TSLA"]


def test_hidden_research_history_requires_explicit_codes() -> None:
    broad = str(
        _active_symbol_stmt("US", include_reference=True).compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )
    targeted = str(
        _active_symbol_stmt(
            "US",
            include_reference=True,
            requested=["SOBR", "NVVE"],
        ).compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
    )

    assert "symbols.is_hidden IS false" in broad
    assert "symbols.is_hidden IS false" not in targeted
    assert "symbols.code IN ('NVVE', 'SOBR')" in targeted


def test_cohort_manifest_is_validated_and_normalized(tmp_path) -> None:
    path = tmp_path / "cohort.json"
    path.write_text(
        json.dumps(
            {
                "name": "launch-v1",
                "market": "US",
                "backfill_years": 10,
                "allow_restricted_research": True,
                "symbols": ["aapl", "BRK.B"],
            }
        )
    )

    cohort = _load_cohort(path, "US")
    assert cohort.name == "launch-v1"
    assert cohort.symbols == ("AAPL", "BRK.B")
    assert cohort.backfill_years == 10
    assert cohort.allow_restricted_research is True
    assert len(cohort.manifest_sha256) == 64
    assert cohort.policy.min_bars == 1250

    with pytest.raises(ValueError, match="does not match"):
        _load_cohort(path, "DSE")


def test_cohort_manifest_hash_is_semantic_and_policy_is_strict(tmp_path) -> None:
    payload = {
        "schema_version": 1,
        "name": "expansion",
        "version": "2026.1",
        "market": "US",
        "symbols": ["AAPL"],
        "policy": {"min_bars": 1000},
    }
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    first.write_text(json.dumps(payload, indent=2))
    second.write_text(json.dumps(payload, separators=(",", ":")))

    assert _load_cohort(first, "US").manifest_sha256 == _load_cohort(
        second, "US"
    ).manifest_sha256

    payload["policy"] = {"unknown_gate": True}
    first.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="unknown_gate"):
        _load_cohort(first, "US")
