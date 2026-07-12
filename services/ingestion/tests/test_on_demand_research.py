from __future__ import annotations

import datetime as dt

from ingestion.on_demand_research import on_demand_manifest


def test_on_demand_manifest_is_single_symbol_strict_and_review_gated() -> None:
    generated_at = dt.datetime(2026, 7, 11, 12, 30, tzinfo=dt.UTC)

    first = on_demand_manifest("CDIO", generated_at=generated_at)
    second = on_demand_manifest("CDIO", generated_at=generated_at)

    assert first.symbols == ("CDIO",)
    assert first.manifest_sha256 == second.manifest_sha256
    assert first.backfill_years == 10
    assert first.policy.allowed_instrument_types == ("common_stock",)
    assert first.policy.min_market_cap_mn == 1.0
    assert first.policy.min_adtv_mn == 0.05
    assert first.policy.requires_risk_review is True
    assert first.risk_review_id is None
