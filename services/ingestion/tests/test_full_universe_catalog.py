from __future__ import annotations

import datetime as dt
import json

from ingestion.cohorts import load_cohort
from ingestion.full_universe_catalog import catalog_payloads


def test_catalog_is_complete_deterministic_and_instrument_specific() -> None:
    records = [
        ("SPY", "etf"),
        ("AAPL", "common_stock"),
        ("BABA", "adr"),
        ("MSFT", "common_stock"),
        ("AAPL", "common_stock"),
        ("BAD", "warrant"),
    ]

    files, index = catalog_payloads(
        records,
        snapshot_date=dt.date(2026, 7, 17),
        cohort_size=1,
    )

    assert index["symbols"] == 4
    assert [row["instrument_type"] for row in index["cohorts"]] == [
        "common_stock",
        "common_stock",
        "adr",
        "etf",
    ]
    by_name = {name: payload for name, payload in files}
    assert by_name["full-common-stock-001.json"]["symbols"] == ["AAPL"]
    assert by_name["full-common-stock-001.json"]["policy"]["sec_facts_required_for"] == [
        "common_stock"
    ]
    assert by_name["full-adr-001.json"]["policy"]["sec_facts_required_for"] == []
    assert by_name["full-etf-001.json"]["policy"]["require_cik_for"] == []
    assert len({row["manifest_sha256"] for row in index["cohorts"]}) == 4


def test_catalog_index_hash_matches_the_onboarding_loader(tmp_path) -> None:
    files, index = catalog_payloads(
        [("AAPL", "common_stock")],
        snapshot_date=dt.date(2026, 7, 17),
    )
    filename, payload = files[0]
    path = tmp_path / filename
    path.write_text(json.dumps(payload))

    assert load_cohort(path, "US").manifest_sha256 == index["cohorts"][0]["manifest_sha256"]
