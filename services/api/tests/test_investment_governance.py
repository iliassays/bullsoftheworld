from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from api.institutional_research.investment import (
    default_mandate_payload,
    risk_policy_from_mandate,
)
from api.institutional_research.schemas import (
    InvestmentMandateUpdate,
    PerformanceAttributionOut,
    PortfolioRiskReportOut,
)
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


def test_nested_portfolio_analytics_serialize_with_camel_case_contract() -> None:
    risk = PortfolioRiskReportOut.model_validate(
        {
            "gross_exposure_pct": 25,
            "cash_reserve_pct": 75,
            "largest_position_pct": 10,
            "largest_sector_pct": 20,
            "concentration_hhi": 0.5,
            "effective_positions": 2,
            "weighted_average_correlation": None,
            "maximum_pair_correlation": None,
            "maximum_exit_days": 1.5,
            "limit_checks": [
                {
                    "key": "gross_exposure",
                    "status": "within_limit",
                    "actual": 25,
                    "limit": 85,
                    "unit": "pct",
                    "detail": "Observed gross exposure.",
                }
            ],
            "stress_scenarios": [
                {
                    "key": "broad_market_down_10",
                    "label": "Broad market -10%",
                    "shock_pct": -10,
                    "estimated_loss_pct": 2.5,
                    "status": "within_limit",
                    "methodology": "Gross exposure shocked by ten percent.",
                }
            ],
            "breached_limits": [],
            "data_quality_notes": [],
        }
    ).model_dump(mode="json", by_alias=True)
    attribution = PerformanceAttributionOut.model_validate(
        {
            "portfolio_return_pct": 1,
            "benchmark_return_pct": 0.5,
            "excess_return_pct": 0.5,
            "components": [
                {
                    "key": "active_residual",
                    "label": "Active strategy residual",
                    "contribution_pct": 0.5,
                    "quality": "proxy",
                    "explanation": "Residual contribution.",
                }
            ],
            "rejected_actions": 0,
            "methodology_version": "atlas-additive-attribution-v1",
        }
    ).model_dump(mode="json", by_alias=True)

    assert risk["limitChecks"][0]["actual"] == 25
    assert risk["stressScenarios"][0]["estimatedLossPct"] == 2.5
    assert "estimated_loss_pct" not in risk["stressScenarios"][0]
    assert attribution["components"][0]["contributionPct"] == 0.5
    assert "contribution_pct" not in attribution["components"][0]
