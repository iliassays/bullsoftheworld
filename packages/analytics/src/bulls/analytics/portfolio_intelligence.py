"""Deterministic portfolio risk and attribution analytics for Atlas shadow books.

The functions in this module are intentionally persistence-agnostic. They accept point-in-time
inputs assembled by the API and return typed read models that can be tested without a database.
"""

from __future__ import annotations

import datetime as dt
import statistics
from itertools import pairwise
from typing import Literal

from pydantic import BaseModel, Field


class MandateLimits(BaseModel):
    market: Literal["DSE", "US"]
    benchmark_key: str
    max_gross_exposure_pct: float = Field(gt=0, le=100)
    min_cash_reserve_pct: float = Field(ge=0, lt=100)
    max_position_weight_pct: float = Field(gt=0, le=100)
    max_sector_weight_pct: float = Field(gt=0, le=100)
    max_adv_participation_pct: float = Field(gt=0, le=100)
    portfolio_drawdown_brake_pct: float = Field(gt=0, le=100)
    stress_loss_limit_pct: float = Field(gt=0, le=100)


class PositionRiskInput(BaseModel):
    code: str
    sector: str = "Unclassified"
    shares: int = Field(gt=0)
    price: float = Field(gt=0)
    average_daily_volume: float | None = Field(default=None, gt=0)
    returns: list[float] = Field(default_factory=list)
    return_observations: dict[dt.date, float] = Field(default_factory=dict)


class RiskLimitCheck(BaseModel):
    key: str
    status: Literal["within_limit", "breached", "unavailable"]
    actual: float | None
    limit: float
    unit: Literal["pct", "days"] = "pct"
    detail: str


class StressScenario(BaseModel):
    key: str
    label: str
    shock_pct: float
    estimated_loss_pct: float | None
    status: Literal["within_limit", "breached", "unavailable"]
    methodology: str


class PortfolioRiskReport(BaseModel):
    gross_exposure_pct: float
    cash_reserve_pct: float
    largest_position_pct: float
    largest_sector_pct: float
    concentration_hhi: float
    effective_positions: float
    weighted_average_correlation: float | None
    maximum_pair_correlation: float | None
    maximum_exit_days: float | None
    limit_checks: list[RiskLimitCheck]
    stress_scenarios: list[StressScenario]
    breached_limits: list[str]
    unavailable_limits: list[str]
    data_complete: bool
    data_quality_notes: list[str]


class AttributionPoint(BaseModel):
    nav: float = Field(gt=0)
    benchmark_nav: float = Field(gt=0)
    gross_exposure_pct: float = Field(ge=0, le=100)
    cumulative_fees: float = Field(ge=0)


class AttributionComponent(BaseModel):
    key: str
    label: str
    contribution_pct: float | None
    quality: Literal["exact", "proxy", "unavailable"]
    explanation: str


class PerformanceAttribution(BaseModel):
    portfolio_return_pct: float
    benchmark_return_pct: float
    excess_return_pct: float
    components: list[AttributionComponent]
    rejected_actions: int
    methodology_version: str = "atlas-additive-attribution-v1"


def _correlation(left: PositionRiskInput, right: PositionRiskInput) -> float | None:
    common_dates = sorted(set(left.return_observations) & set(right.return_observations))[-60:]
    if left.return_observations or right.return_observations:
        x = [left.return_observations[date] for date in common_dates]
        y = [right.return_observations[date] for date in common_dates]
    else:
        sample = min(len(left.returns), len(right.returns), 60)
        x = left.returns[-sample:]
        y = right.returns[-sample:]
    if len(x) < 20:
        return None
    if statistics.pstdev(x) == 0 or statistics.pstdev(y) == 0:
        return None
    covariance = statistics.fmean(
        (a - statistics.fmean(x)) * (b - statistics.fmean(y)) for a, b in zip(x, y, strict=True)
    )
    return covariance / (statistics.pstdev(x) * statistics.pstdev(y))


def analyze_portfolio_risk(
    *,
    nav: float,
    cash: float,
    drawdown_pct: float,
    positions: list[PositionRiskInput],
    mandate: MandateLimits,
    unavailable_position_codes: list[str] | None = None,
) -> PortfolioRiskReport:
    """Evaluate observable portfolio risk against one market-bound mandate."""

    if nav <= 0 or cash < 0:
        raise ValueError("portfolio risk requires positive NAV and non-negative cash")

    unavailable_position_codes = sorted(set(unavailable_position_codes or []))
    position_values = {item.code: item.shares * item.price for item in positions}
    weights = {code: value / nav * 100 for code, value in position_values.items()}
    gross_exposure = sum(weights.values())
    cash_reserve = cash / nav * 100
    largest_position = max(weights.values(), default=0.0)
    sector_weights: dict[str, float] = {}
    for item in positions:
        sector_weights[item.sector] = sector_weights.get(item.sector, 0.0) + weights[item.code]
    largest_sector = max(sector_weights.values(), default=0.0)
    normalized_weights = (
        [weight / gross_exposure for weight in weights.values()] if gross_exposure else []
    )
    hhi = sum(weight**2 for weight in normalized_weights)
    effective_positions = 1 / hhi if hhi > 0 else 0.0

    correlation_rows: list[tuple[float, float]] = []
    for index, left in enumerate(positions):
        for right in positions[index + 1 :]:
            correlation = _correlation(left, right)
            if correlation is None:
                continue
            pair_weight = weights[left.code] * weights[right.code]
            correlation_rows.append((correlation, pair_weight))
    weighted_correlation = (
        sum(value * weight for value, weight in correlation_rows)
        / sum(weight for _, weight in correlation_rows)
        if correlation_rows and sum(weight for _, weight in correlation_rows) > 0
        else None
    )
    maximum_correlation = max((value for value, _ in correlation_rows), default=None)

    exit_days: list[float] = []
    missing_liquidity: list[str] = []
    adv_fraction = mandate.max_adv_participation_pct / 100
    for item in positions:
        if item.average_daily_volume is None:
            missing_liquidity.append(item.code)
            continue
        exit_days.append(item.shares / (item.average_daily_volume * adv_fraction))
    maximum_exit_days = max(exit_days, default=None)

    def check(
        key: str,
        actual: float | None,
        limit: float,
        detail: str,
        *,
        minimum: bool = False,
    ) -> RiskLimitCheck:
        if actual is None:
            status: Literal["within_limit", "breached", "unavailable"] = "unavailable"
        elif actual < limit if minimum else actual > limit:
            status = "breached"
        else:
            status = "within_limit"
        return RiskLimitCheck(key=key, status=status, actual=actual, limit=limit, detail=detail)

    positions_complete = not unavailable_position_codes
    checks = [
        check(
            "gross_exposure",
            gross_exposure if positions_complete else None,
            mandate.max_gross_exposure_pct,
            "Total invested weight versus the mandate ceiling.",
        ),
        check(
            "cash_reserve",
            cash_reserve,
            mandate.min_cash_reserve_pct,
            "Settled cash available for risk and new targets.",
            minimum=True,
        ),
        check(
            "single_name",
            largest_position if positions_complete else None,
            mandate.max_position_weight_pct,
            "Largest observable security weight.",
        ),
        check(
            "sector_concentration",
            largest_sector if positions_complete else None,
            mandate.max_sector_weight_pct,
            "Largest observable sector weight.",
        ),
        check(
            "drawdown_brake",
            drawdown_pct,
            mandate.portfolio_drawdown_brake_pct,
            "Current peak-to-trough drawdown.",
        ),
    ]

    broad_market_loss = gross_exposure * 0.10
    sector_loss = largest_sector * 0.15
    illiquid_weight = sum(
        weights[item.code]
        for item in positions
        if item.average_daily_volume is None
        or item.shares / (item.average_daily_volume * adv_fraction) > 2
    )
    liquidity_gap_loss = illiquid_weight * 0.20
    stresses = [
        StressScenario(
            key="broad_market_down_10",
            label="Broad market -10%",
            shock_pct=-10,
            estimated_loss_pct=round(broad_market_loss, 3) if positions_complete else None,
            status=(
                "unavailable"
                if not positions_complete
                else "breached"
                if broad_market_loss > mandate.stress_loss_limit_pct
                else "within_limit"
            ),
            methodology="Applies a simultaneous -10% price shock to current gross exposure; no diversification benefit.",
        ),
        StressScenario(
            key="largest_sector_down_15",
            label="Largest sector -15%",
            shock_pct=-15,
            estimated_loss_pct=round(sector_loss, 3) if positions_complete else None,
            status=(
                "unavailable"
                if not positions_complete
                else "breached"
                if sector_loss > mandate.stress_loss_limit_pct
                else "within_limit"
            ),
            methodology="Applies a -15% shock to the largest observed sector allocation.",
        ),
        StressScenario(
            key="illiquid_positions_gap_20",
            label="Illiquid holdings -20% gap",
            shock_pct=-20,
            estimated_loss_pct=round(liquidity_gap_loss, 3) if positions_complete else None,
            status=(
                "unavailable"
                if not positions_complete
                else "breached"
                if liquidity_gap_loss > mandate.stress_loss_limit_pct
                else "within_limit"
            ),
            methodology="Applies a -20% gap to holdings requiring more than two mandate-sized ADV days; missing liquidity is treated as exposed.",
        ),
    ]
    breached = [item.key for item in checks if item.status == "breached"] + [
        item.key for item in stresses if item.status == "breached"
    ]
    unavailable = [item.key for item in checks if item.status == "unavailable"] + [
        item.key for item in stresses if item.status == "unavailable"
    ]
    notes: list[str] = []
    if unavailable_position_codes:
        notes.append(
            "Held-position market history is unavailable or stale for: "
            f"{', '.join(unavailable_position_codes)}. Exposure and stress limits fail closed."
        )
    if missing_liquidity:
        notes.append(
            f"Average-volume history is unavailable for: {', '.join(sorted(missing_liquidity))}."
        )
    if positions and weighted_correlation is None:
        notes.append(
            "At least 20 aligned return observations are required for correlation diagnostics."
        )
    if not positions:
        notes.append(
            "The book is fully in cash; security-level risk diagnostics are not applicable."
        )

    return PortfolioRiskReport(
        gross_exposure_pct=round(gross_exposure, 3),
        cash_reserve_pct=round(cash_reserve, 3),
        largest_position_pct=round(largest_position, 3),
        largest_sector_pct=round(largest_sector, 3),
        concentration_hhi=round(hhi, 4),
        effective_positions=round(effective_positions, 2),
        weighted_average_correlation=(
            round(weighted_correlation, 4) if weighted_correlation is not None else None
        ),
        maximum_pair_correlation=(
            round(maximum_correlation, 4) if maximum_correlation is not None else None
        ),
        maximum_exit_days=(round(maximum_exit_days, 2) if maximum_exit_days is not None else None),
        limit_checks=checks,
        stress_scenarios=stresses,
        breached_limits=breached,
        unavailable_limits=unavailable,
        data_complete=not unavailable_position_codes,
        data_quality_notes=notes,
    )


def attribute_performance(
    points: list[AttributionPoint], *, rejected_actions: int = 0
) -> PerformanceAttribution:
    """Build an additive daily attribution without pretending unavailable precision exists."""

    if not points:
        return PerformanceAttribution(
            portfolio_return_pct=0,
            benchmark_return_pct=0,
            excess_return_pct=0,
            rejected_actions=rejected_actions,
            components=[
                AttributionComponent(
                    key=key,
                    label=label,
                    contribution_pct=None,
                    quality="unavailable",
                    explanation="No completed forward interval exists.",
                )
                for key, label in (
                    ("market_beta", "Market beta proxy"),
                    ("active_residual", "Active strategy residual"),
                    ("costs", "Explicit fees"),
                    ("linking_residual", "Compounding residual"),
                    ("timing", "Execution timing"),
                    ("sizing", "Sizing effect"),
                    ("constraints", "Constraint opportunity cost"),
                )
            ],
        )

    initial = points[0]
    latest = points[-1]
    portfolio_return = (latest.nav / initial.nav - 1) * 100
    benchmark_return = (latest.benchmark_nav / initial.benchmark_nav - 1) * 100
    beta_proxy = 0.0
    cost_contribution = 0.0
    active_residual = 0.0
    for previous, current in pairwise(points):
        portfolio_period = current.nav / previous.nav - 1
        benchmark_period = current.benchmark_nav / previous.benchmark_nav - 1
        fee_period = max(0.0, current.cumulative_fees - previous.cumulative_fees) / previous.nav
        beta_period = benchmark_period * previous.gross_exposure_pct / 100
        beta_proxy += beta_period
        cost_contribution -= fee_period
        active_residual += portfolio_period - beta_period + fee_period

    linking_residual = portfolio_return / 100 - beta_proxy - active_residual - cost_contribution

    components = [
        AttributionComponent(
            key="market_beta",
            label="Market beta proxy",
            contribution_pct=round(beta_proxy * 100, 3),
            quality="proxy",
            explanation="Daily benchmark return multiplied by prior-close gross exposure; factor beta is not yet estimated.",
        ),
        AttributionComponent(
            key="active_residual",
            label="Active strategy residual",
            contribution_pct=round(active_residual * 100, 3),
            quality="proxy",
            explanation="Residual after the market-exposure proxy and explicit fees; it still combines selection, sizing, and timing.",
        ),
        AttributionComponent(
            key="costs",
            label="Explicit fees",
            contribution_pct=round(cost_contribution * 100, 3),
            quality="exact",
            explanation="Incremental recorded paper fees divided by prior NAV. Modeled slippage remains embedded in fills.",
        ),
        AttributionComponent(
            key="linking_residual",
            label="Compounding residual",
            contribution_pct=round(linking_residual * 100, 3),
            quality="exact",
            explanation="Reconciles additive daily contributions to the geometrically compounded portfolio return.",
        ),
        AttributionComponent(
            key="timing",
            label="Execution timing",
            contribution_pct=None,
            quality="unavailable",
            explanation="Requires an arrival-price or decision-price benchmark that current snapshots do not retain.",
        ),
        AttributionComponent(
            key="sizing",
            label="Sizing effect",
            contribution_pct=None,
            quality="unavailable",
            explanation="Requires a frozen equal-weight counterfactual for every target set.",
        ),
        AttributionComponent(
            key="constraints",
            label="Constraint opportunity cost",
            contribution_pct=None,
            quality="unavailable",
            explanation=f"{rejected_actions} constrained or rejected actions are recorded, but counterfactual prices are not yet mature.",
        ),
    ]
    return PerformanceAttribution(
        portfolio_return_pct=round(portfolio_return, 3),
        benchmark_return_pct=round(benchmark_return, 3),
        excess_return_pct=round(portfolio_return - benchmark_return, 3),
        components=components,
        rejected_actions=rejected_actions,
    )
