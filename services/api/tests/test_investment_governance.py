from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from api.institutional_research.investment import (
    default_mandate_payload,
    risk_policy_from_mandate,
)
from api.institutional_research.schemas import InvestmentMandateUpdate
from bulls.core.models import ResearchInvestmentMandate


def test_default_mandates_match_existing_market_risk_authority() -> None:
    dse = default_mandate_payload("DSE")
    us = default_mandate_payload("US")

    assert (dse.max_gross_exposure_pct, dse.max_adv_participation_pct) == (85, 2)
    assert (us.max_gross_exposure_pct, us.max_adv_participation_pct) == (90, 5)
    assert dse.benchmark_key == "dsex_equal_weight_proxy"
    assert us.benchmark_key == "us_equal_weight_proxy"


def test_mandate_rejects_incoherent_capital_and_concentration_limits() -> None:
    with pytest.raises(ValidationError, match="gross exposure plus minimum cash reserve"):
        InvestmentMandateUpdate(
            objective="Preserve capital while compounding against a declared benchmark.",
            benchmark_key="test_proxy",
            max_gross_exposure_pct=95,
            min_cash_reserve_pct=10,
            max_position_weight_pct=10,
            max_sector_weight_pct=30,
            max_adv_participation_pct=2,
            portfolio_drawdown_brake_pct=15,
            stress_loss_limit_pct=12,
        )


def test_persisted_mandate_rehydrates_exact_engine_limits() -> None:
    record = ResearchInvestmentMandate(
        market="DSE",
        max_gross_exposure_pct=Decimal("70"),
        max_position_weight_pct=Decimal("8"),
        max_sector_weight_pct=Decimal("20"),
        max_adv_participation_pct=Decimal("1.5"),
        portfolio_drawdown_brake_pct=Decimal("10"),
    )

    # The record-to-snapshot boundary requires the remaining persisted fields. This focused test
    # sets them directly without opening a database session.
    record.id = "00000000-0000-0000-0000-000000000001"
    record.workspace_id = "00000000-0000-0000-0000-000000000002"
    record.tenant_id = "bullsofdhaka"
    record.version = 2
    record.status = "active"
    record.objective = "Preserve capital while compounding against a declared benchmark."
    record.benchmark_key = "dsex_equal_weight_proxy"
    record.min_cash_reserve_pct = Decimal("30")
    record.stress_loss_limit_pct = Decimal("10")
    record.specification_hash = "0" * 64
    record.effective_at = "2026-07-18T00:00:00Z"
    record.superseded_at = None

    policy = risk_policy_from_mandate(record)

    assert policy.market == "DSE"
    assert policy.max_gross_exposure == 0.70
    assert policy.max_position_weight == 0.08
    assert policy.max_sector_weight == 0.20
    assert policy.max_adv_participation == 0.015
    assert policy.portfolio_drawdown_brake == 0.10
