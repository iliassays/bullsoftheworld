from __future__ import annotations

import datetime as dt
import uuid

from bulls.core.models import SecurityMaster, Symbol
from ingestion.cohorts import OnboardingPolicy
from ingestion.onboarding_gates import _evaluate_symbol


def _symbol(security_id: uuid.UUID) -> Symbol:
    return Symbol(
        market="US",
        code="TEST",
        security_id=security_id,
        name_en="Test Inc.",
        is_active=True,
        is_hidden=False,
        data_status="onboarding",
    )


def _security(security_id: uuid.UUID, instrument_type: str = "common_stock") -> SecurityMaster:
    return SecurityMaster(
        security_id=security_id,
        market="US",
        symbol="TEST",
        raw_symbol="TEST",
        security_name="Test Inc.",
        exchange="Nasdaq",
        cik=1 if instrument_type != "etf" else None,
        instrument_type=instrument_type,
        is_active=True,
        is_product_eligible=True,
        source="test",
        source_file="test",
        last_seen_at=dt.datetime(2026, 7, 10, tzinfo=dt.UTC),
        updated_at=dt.datetime(2026, 7, 10, tzinfo=dt.UTC),
    )


def _policy() -> OnboardingPolicy:
    return OnboardingPolicy(
        min_bars=252,
        min_history_days=365,
        max_staleness_days=10,
        min_adjusted_close_ratio=0.98,
        min_nonzero_volume_ratio=0.95,
    )


def test_common_stock_passes_only_with_complete_required_evidence() -> None:
    security_id = uuid.uuid4()
    evidence = _evaluate_symbol(
        code="TEST",
        symbol=_symbol(security_id),
        security=_security(security_id),
        bars=(300, dt.date(2025, 1, 1), dt.date(2026, 7, 9), 300, 299, 0),
        sec_filings=10,
        sec_facts=20,
        has_analytics=True,
        has_13f=False,
        policy=_policy(),
        as_of_date=dt.date(2026, 7, 11),
    )

    assert evidence.passed
    assert evidence.failure_reasons == []
    assert not evidence.gates["institutional_mapping"]["passed"]
    assert not evidence.gates["institutional_mapping"]["required"]


def test_required_failures_are_named_and_optional_evidence_does_not_block() -> None:
    security_id = uuid.uuid4()
    evidence = _evaluate_symbol(
        code="TEST",
        symbol=_symbol(security_id),
        security=_security(security_id),
        bars=(100, dt.date(2026, 1, 1), dt.date(2026, 6, 1), 50, 50, 2),
        sec_filings=0,
        sec_facts=0,
        has_analytics=False,
        has_13f=False,
        policy=_policy(),
        as_of_date=dt.date(2026, 7, 11),
    )

    assert not evidence.passed
    assert set(evidence.failure_reasons) == {
        "bar_depth",
        "history_span",
        "freshness",
        "adjusted_close",
        "nonzero_volume",
        "ohlc_integrity",
        "sec_filings",
        "sec_facts",
        "analytics",
    }
    assert "institutional_mapping" not in evidence.failure_reasons


def test_etf_does_not_inherit_common_stock_sec_requirements() -> None:
    security_id = uuid.uuid4()
    evidence = _evaluate_symbol(
        code="TEST",
        symbol=_symbol(security_id),
        security=_security(security_id, "etf"),
        bars=(300, dt.date(2025, 1, 1), dt.date(2026, 7, 9), 300, 300, 0),
        sec_filings=0,
        sec_facts=0,
        has_analytics=True,
        has_13f=True,
        policy=_policy(),
        as_of_date=dt.date(2026, 7, 11),
    )

    assert evidence.passed
    assert not evidence.gates["cik"]["required"]
    assert not evidence.gates["sec_facts"]["required"]
