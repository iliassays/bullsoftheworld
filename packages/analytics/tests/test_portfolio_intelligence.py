from __future__ import annotations

import pytest

from bulls.analytics.portfolio_intelligence import (
    AttributionPoint,
    MandateLimits,
    PositionRiskInput,
    analyze_portfolio_risk,
    attribute_performance,
)


def mandate() -> MandateLimits:
    return MandateLimits(
        market="DSE",
        benchmark_key="dsex_equal_weight_proxy",
        max_gross_exposure_pct=85,
        min_cash_reserve_pct=15,
        max_position_weight_pct=12,
        max_sector_weight_pct=30,
        max_adv_participation_pct=2,
        portfolio_drawdown_brake_pct=15,
        stress_loss_limit_pct=12,
    )


def test_risk_report_fails_closed_on_concentration_and_missing_liquidity() -> None:
    report = analyze_portfolio_risk(
        nav=100_000,
        cash=10_000,
        drawdown_pct=16,
        mandate=mandate(),
        positions=[
            PositionRiskInput(
                code="AAA",
                sector="Bank",
                shares=2_000,
                price=20,
                average_daily_volume=10_000,
                returns=[index / 10_000 for index in range(30)],
            ),
            PositionRiskInput(
                code="BBB",
                sector="Bank",
                shares=1_000,
                price=30,
                returns=[index / 12_000 for index in range(30)],
            ),
        ],
    )

    assert {"cash_reserve", "single_name", "sector_concentration", "drawdown_brake"} <= set(
        report.breached_limits
    )
    assert report.maximum_exit_days == 10
    assert report.data_quality_notes == ["Average-volume history is unavailable for: BBB."]
    assert (
        next(
            item for item in report.stress_scenarios if item.key == "illiquid_positions_gap_20"
        ).estimated_loss_pct
        == 14
    )


def test_cash_only_book_has_explicit_non_applicable_risk_state() -> None:
    report = analyze_portfolio_risk(
        nav=100_000,
        cash=100_000,
        drawdown_pct=0,
        mandate=mandate(),
        positions=[],
    )

    assert report.gross_exposure_pct == 0
    assert report.breached_limits == []
    assert "fully in cash" in report.data_quality_notes[0]


def test_attribution_reconciles_beta_proxy_active_residual_and_exact_costs() -> None:
    result = attribute_performance(
        [
            AttributionPoint(nav=100, benchmark_nav=100, gross_exposure_pct=50, cumulative_fees=0),
            AttributionPoint(
                nav=101, benchmark_nav=102, gross_exposure_pct=60, cumulative_fees=0.2
            ),
        ],
        rejected_actions=2,
    )

    components = {item.key: item for item in result.components}
    assert result.portfolio_return_pct == 1
    assert result.benchmark_return_pct == 2
    assert components["market_beta"].contribution_pct == 1
    assert components["costs"].contribution_pct == -0.2
    assert components["active_residual"].contribution_pct == pytest.approx(0.2)
    assert components["timing"].quality == "unavailable"
    assert components["constraints"].contribution_pct is None


def test_empty_attribution_never_invents_components() -> None:
    result = attribute_performance([])

    assert result.portfolio_return_pct == 0
    assert all(component.quality == "unavailable" for component in result.components)
