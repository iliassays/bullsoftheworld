"""Point-in-time backtest and shadow-book engine for Bulls Atlas.

Signals use completed information through T and execute no earlier than the next observable
session. Execution timing is part of the frozen strategy specification: the legacy portal
strategies use next-open fills, while the institutional event and factor systems use next-close
fills because the research mandate explicitly prohibits optimistic opening-auction execution.
The engine is deliberately long-only until market-specific borrowing and locate data exist.
"""

from __future__ import annotations

import datetime as dt
import math
import statistics
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from bulls.analytics.cost_observatory import CostTier, cost_tiers, estimate_spread
from bulls.analytics.drawdown_ladder import (
    DrawdownLadder,
    LadderState,
    apply_drawdown_ladder,
)

ENGINE_VERSION = "atlas-portfolio-engine-v3"

type StrategyKey = Literal[
    "dse_reversal_v1",
    "dse_compression_breakout_20d_v1",
    "us_breakout_v1",
    "us_activist_13d_v1",
    "us_insider_cluster_v1",
    "us_forced_seller_v1",
    "us_factor_sleeve_v1",
]
type ExecutionTiming = Literal["next_open", "next_close"]
type RobustnessKey = Literal[
    "global_financial_crisis_2007_2009",
    "factor_drought_2017_2020",
    "pandemic_dislocation_2020_2021",
    "rates_inflation_2022_2023",
    "recent_2024_onward",
]

# Half-spread cost input for a backtest run:
#   None              -> use the policy's flat slippage_rate (backward-compatible default)
#   float (bps)       -> one flat one-way half-spread applied to every name (a stress tier)
#   dict[code, bps]   -> per-name measured half-spread, policy slippage_rate for anything missing
HalfSpreadInput = float | dict[str, float] | None


class StrategyBar(BaseModel):
    date: dt.date
    open: float = Field(gt=0)
    high: float = Field(gt=0)
    low: float = Field(gt=0)
    close: float = Field(gt=0)
    volume: int = Field(ge=0)


class StrategySecurity(BaseModel):
    code: str
    sector: str = "Unclassified"
    cap_tier: str = "unclassified"
    bars: list[StrategyBar]


class BenchmarkPoint(BaseModel):
    """One completed close for an independently specified market benchmark."""

    date: dt.date
    close: float = Field(gt=0)


class BenchmarkSeries(BaseModel):
    """Benchmark identity and observations, kept separate from the strategy universe."""

    key: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9_.-]+$")
    label: str = Field(min_length=1, max_length=120)
    points: list[BenchmarkPoint]

    @model_validator(mode="after")
    def unique_dates(self) -> BenchmarkSeries:
        dates = [point.date for point in self.points]
        if len(dates) != len(set(dates)):
            raise ValueError("benchmark points must contain unique dates")
        return self


class StrategyDefinition(BaseModel):
    key: StrategyKey
    market: Literal["DSE", "US"]
    name: str
    methodology_version: str
    minimum_lookback: int
    rebalance_sessions: int
    maximum_positions: int
    description: str
    # Holding-horizon description belongs to the registered strategy, not to whichever
    # presentation layer happens to render it.
    horizon: Literal["swing", "position"] = "position"
    expected_holding: str = "Defined by the registered strategy"


class PortfolioRiskPolicy(BaseModel):
    market: Literal["DSE", "US"]
    minimum_average_daily_value_mn: float
    max_adv_participation: float
    max_position_weight: float
    max_sector_weight: float
    max_gross_exposure: float
    target_annualized_volatility: float
    position_stop_loss: float
    portfolio_drawdown_brake: float
    fee_rate: float
    slippage_rate: float


class BacktestTrade(BaseModel):
    date: dt.date
    code: str
    side: Literal["buy", "sell"]
    quantity: int
    fill_price: float
    gross_value: float
    fee: float
    reason: str
    intended_quantity: int | None = Field(default=None, gt=0)
    constraint_notes: list[str] = Field(default_factory=list)
    decision_reference_price: float | None = Field(default=None, gt=0)
    implementation_shortfall_bps: float | None = None


class EquityPoint(BaseModel):
    date: dt.date
    nav: float
    benchmark: float
    cash: float
    gross_exposure_pct: float
    drawdown_pct: float


class RiskIntervention(BaseModel):
    date: dt.date
    code: str | None = None
    rule: str
    detail: str


class PerformanceSlice(BaseModel):
    label: Literal["full", "train", "validation", "test"]
    sessions: int
    total_return_pct: float | None
    annualized_return_pct: float | None
    annualized_volatility_pct: float | None
    sharpe: float | None
    sortino: float | None
    max_drawdown_pct: float | None


class RobustnessSlice(BaseModel):
    key: RobustnessKey
    label: str
    start_date: dt.date
    end_date: dt.date
    sessions: int
    total_return_pct: float
    benchmark_return_pct: float
    excess_return_pct: float
    max_drawdown_pct: float


class BacktestResult(BaseModel):
    engine_version: str
    strategy: StrategyDefinition
    risk_policy: PortfolioRiskPolicy
    start_date: dt.date | None
    end_date: dt.date | None
    initial_capital: float
    final_nav: float
    benchmark_final: float
    benchmark_key: str
    benchmark_label: str
    benchmark_method: Literal["explicit_series", "observable_universe_equal_weight"]
    benchmark_coverage_pct: float
    benchmark_valid: bool
    trades: list[BacktestTrade]
    equity_curve: list[EquityPoint]
    risk_interventions: list[RiskIntervention]
    metrics: list[PerformanceSlice]
    robustness_slices: list[RobustnessSlice]
    turnover_pct: float
    fees_paid: float
    validation_status: Literal["diagnostic", "eligible_for_shadow"]
    failed_gates: list[str]
    warnings: list[str]
    latest_target_weights: dict[str, float]


_ROBUSTNESS_WINDOWS: tuple[tuple[RobustnessKey, str, dt.date, dt.date], ...] = (
    (
        "global_financial_crisis_2007_2009",
        "Global financial crisis",
        dt.date(2007, 7, 1),
        dt.date(2009, 6, 30),
    ),
    (
        "factor_drought_2017_2020",
        "Factor drought",
        dt.date(2017, 1, 1),
        dt.date(2020, 1, 31),
    ),
    (
        "pandemic_dislocation_2020_2021",
        "Pandemic dislocation",
        dt.date(2020, 2, 1),
        dt.date(2021, 12, 31),
    ),
    (
        "rates_inflation_2022_2023",
        "Rates and inflation shock",
        dt.date(2022, 1, 1),
        dt.date(2023, 12, 31),
    ),
    (
        "recent_2024_onward",
        "Recent regime",
        dt.date(2024, 1, 1),
        dt.date.max,
    ),
)


def robustness_slices(equity_curve: list[EquityPoint]) -> list[RobustnessSlice]:
    """Measure named stress periods without synthesizing missing historical observations."""

    slices: list[RobustnessSlice] = []
    for key, label, window_start, window_end in _ROBUSTNESS_WINDOWS:
        points = [point for point in equity_curve if window_start <= point.date <= window_end]
        if len(points) < 2 or points[0].nav <= 0 or points[0].benchmark <= 0:
            continue
        peak = points[0].nav
        maximum_drawdown = 0.0
        for point in points:
            peak = max(peak, point.nav)
            if peak > 0:
                maximum_drawdown = max(maximum_drawdown, 1 - point.nav / peak)
        total_return = (points[-1].nav / points[0].nav - 1) * 100
        benchmark_return = (points[-1].benchmark / points[0].benchmark - 1) * 100
        slices.append(
            RobustnessSlice(
                key=key,
                label=label,
                start_date=points[0].date,
                end_date=points[-1].date,
                sessions=len(points),
                total_return_pct=round(total_return, 3),
                benchmark_return_pct=round(benchmark_return, 3),
                excess_return_pct=round(total_return - benchmark_return, 3),
                max_drawdown_pct=round(maximum_drawdown * 100, 3),
            )
        )
    return slices


class ShadowPosition(BaseModel):
    shares: int = Field(ge=0)
    average_cost: float = Field(ge=0)


class ShadowState(BaseModel):
    cash: float = Field(ge=0)
    positions: dict[str, ShadowPosition] = Field(default_factory=dict)
    peak_nav: float = Field(gt=0)
    benchmark_nav: float = Field(gt=0)
    cumulative_fees: float = Field(default=0, ge=0)
    cumulative_turnover: float = Field(default=0, ge=0)
    # Live/shadow drawdown ladder: once the flatten rung trips, the book stays flat until an
    # operator clears the freeze after a written review (Phase 15 L2). Defaults False so existing
    # persisted shadow states deserialize unchanged.
    ladder_frozen: bool = False


class ShadowAdvanceResult(BaseModel):
    date: dt.date
    state: ShadowState
    nav: float
    gross_exposure_pct: float
    drawdown_pct: float
    trades: list[BacktestTrade]
    risk_interventions: list[RiskIntervention]
    next_target_weights: dict[str, float]


class PromotionCheck(BaseModel):
    key: str
    passed: bool
    actual: float | int | str
    requirement: str


class ShadowPromotionDecision(BaseModel):
    status: Literal["diagnostic", "collecting", "eligible", "rejected"]
    headline: str
    sessions: int
    portfolio_return_pct: float
    benchmark_return_pct: float
    excess_return_pct: float
    maximum_drawdown_pct: float
    executions: int
    checks: list[PromotionCheck]


def evaluate_shadow_promotion(
    *,
    source_validation_status: str,
    initial_nav: float,
    latest_nav: float,
    initial_benchmark_nav: float,
    latest_benchmark_nav: float,
    sessions: int,
    maximum_drawdown_pct: float,
    executions: int,
    benchmark_independent: bool = False,
    minimum_sessions: int = 60,
    minimum_excess_return_pct: float = 2.0,
    maximum_allowed_drawdown_pct: float = 15.0,
    minimum_executions: int = 10,
) -> ShadowPromotionDecision:
    """Evaluate evidence readiness without ever allocating capital or hiding failed gates."""

    if min(initial_nav, latest_nav, initial_benchmark_nav, latest_benchmark_nav) <= 0:
        raise ValueError("promotion evaluation requires positive NAV values")
    portfolio_return = (latest_nav / initial_nav - 1) * 100
    benchmark_return = (latest_benchmark_nav / initial_benchmark_nav - 1) * 100
    excess_return = portfolio_return - benchmark_return
    checks = [
        PromotionCheck(
            key="historical_validation",
            passed=source_validation_status == "eligible_for_shadow",
            actual=source_validation_status,
            requirement="Source backtest must pass every historical validation gate.",
        ),
        PromotionCheck(
            key="forward_sessions",
            passed=sessions >= minimum_sessions,
            actual=sessions,
            requirement=f"At least {minimum_sessions} completed forward sessions.",
        ),
        PromotionCheck(
            key="independent_benchmark",
            passed=benchmark_independent,
            actual="explicit_series"
            if benchmark_independent
            else "observable_universe_equal_weight",
            requirement=(
                "The forward benchmark must be an explicit independent market series; the "
                "current-universe equal-weight diagnostic cannot support promotion."
            ),
        ),
        PromotionCheck(
            key="benchmark_relative_return",
            passed=excess_return >= minimum_excess_return_pct,
            actual=round(excess_return, 3),
            requirement=f"Excess return of at least {minimum_excess_return_pct:.1f}%.",
        ),
        PromotionCheck(
            key="maximum_drawdown",
            passed=maximum_drawdown_pct <= maximum_allowed_drawdown_pct,
            actual=round(maximum_drawdown_pct, 3),
            requirement=f"Maximum drawdown no greater than {maximum_allowed_drawdown_pct:.1f}%.",
        ),
        PromotionCheck(
            key="executions",
            passed=executions >= minimum_executions,
            actual=executions,
            requirement=f"At least {minimum_executions} forward executions.",
        ),
    ]
    failed = {check.key for check in checks if not check.passed}
    if "historical_validation" in failed:
        status: Literal["diagnostic", "collecting", "eligible", "rejected"] = "diagnostic"
        headline = (
            "Forward paper evidence is collecting, but historical data gates block promotion."
        )
    elif "independent_benchmark" in failed:
        status = "diagnostic"
        headline = (
            "Forward paper evidence is collecting, but the benchmark basis is the "
            "current-universe equal-weight diagnostic; promotion requires an explicit "
            "independent market series."
        )
    elif sessions < minimum_sessions:
        status = "collecting"
        headline = "The shadow book has not completed the minimum forward observation window."
    elif failed:
        status = "rejected"
        headline = "The strategy failed one or more objective forward promotion gates."
    else:
        status = "eligible"
        headline = "The strategy is eligible for a separate investment-committee decision."
    return ShadowPromotionDecision(
        status=status,
        headline=headline,
        sessions=sessions,
        portfolio_return_pct=round(portfolio_return, 3),
        benchmark_return_pct=round(benchmark_return, 3),
        excess_return_pct=round(excess_return, 3),
        maximum_drawdown_pct=round(maximum_drawdown_pct, 3),
        executions=executions,
        checks=checks,
    )


STRATEGIES = {
    "dse_reversal_v1": StrategyDefinition(
        key="dse_reversal_v1",
        market="DSE",
        name="DSE liquid reversal",
        horizon="swing",
        expected_holding="Approximately 5-20 completed sessions",
        methodology_version="dse-liquid-reversal-v1",
        minimum_lookback=126,
        rebalance_sessions=5,
        maximum_positions=8,
        description=(
            "Ranks liquid drawdown recoveries using completed price and participation data. "
            "It does not use historically unavailable fundamental snapshots."
        ),
    ),
    "dse_compression_breakout_20d_v1": StrategyDefinition(
        key="dse_compression_breakout_20d_v1",
        market="DSE",
        name="DSE compression breakout 20-session study",
        horizon="swing",
        expected_holding="Up to 20 completed sessions; structural failure can exit sooner",
        methodology_version="dse-compression-breakout-20d-v1.1",
        minimum_lookback=20,
        rebalance_sessions=1,
        maximum_positions=8,
        description=(
            "A locked forward experiment using first squeeze-monitor-v3 compression-breakout "
            "confirmations. It is risk-sized and paper-observed, not a validated recommendation."
        ),
    ),
    "us_breakout_v1": StrategyDefinition(
        key="us_breakout_v1",
        market="US",
        name="US liquid trend participation",
        horizon="swing",
        expected_holding="Approximately 10-40 completed sessions",
        methodology_version="us-liquid-trend-v1",
        minimum_lookback=200,
        rebalance_sessions=5,
        maximum_positions=10,
        description=(
            "Ranks liquid positive trends with participation confirmation and extension control."
        ),
    ),
    "us_activist_13d_v1": StrategyDefinition(
        key="us_activist_13d_v1",
        market="US",
        name="US activist 13D event book",
        horizon="position",
        expected_holding="Campaign-driven, with a 12-month time stop",
        methodology_version="us-activist-13d-v1",
        minimum_lookback=20,
        rebalance_sessions=1,
        maximum_positions=20,
        description=(
            "Follows new Schedule 13D disclosures from a preregistered activist roster. "
            "Signals, rejections, thesis breaks, costs, and time stops are point-in-time."
        ),
    ),
    "us_insider_cluster_v1": StrategyDefinition(
        key="us_insider_cluster_v1",
        market="US",
        name="US opportunistic insider cluster book",
        horizon="position",
        expected_holding="Approximately 20-120 completed sessions",
        methodology_version="us-insider-cluster-v1",
        minimum_lookback=20,
        rebalance_sessions=1,
        maximum_positions=20,
        description=(
            "Follows non-plan open-market purchases by insiders classified from history "
            "available at each filing timestamp, with clusters ranked above single purchases."
        ),
    ),
    "us_forced_seller_v1": StrategyDefinition(
        key="us_forced_seller_v1",
        market="US",
        name="US forced-seller post-spin book",
        horizon="position",
        expected_holding="Event-driven, up to 24 months",
        methodology_version="us-forced-seller-post-spin-v1",
        minimum_lookback=20,
        rebalance_sessions=1,
        maximum_positions=20,
        description=(
            "Tests post-spin forced-selling dislocations only when authoritative point-in-time "
            "corporate-action, parent-holder, and distribution histories are available."
        ),
    ),
}


STRATEGIES["us_factor_sleeve_v1"] = StrategyDefinition(
    key="us_factor_sleeve_v1",
    market="US",
    name="US factor sleeve",
    horizon="position",
    expected_holding="Monthly rebalance; multi-month holding",
    methodology_version="us-factor-sleeve-v1",
    # A year of history is required before the 12-1 momentum leg exists at all.
    minimum_lookback=252,
    rebalance_sessions=21,
    maximum_positions=40,
    description=(
        "Equal-weighted composite of value, momentum, quality and low-issuance ranks, "
        "vol-scaled within 1/N bands. Weights are supplied by the factor sleeve rather than "
        "computed from price features, so this strategy always runs from a weight schedule."
    ),
)


RISK_POLICIES = {
    "DSE": PortfolioRiskPolicy(
        market="DSE",
        minimum_average_daily_value_mn=2.0,
        max_adv_participation=0.02,
        max_position_weight=0.12,
        max_sector_weight=0.30,
        max_gross_exposure=0.85,
        target_annualized_volatility=0.18,
        position_stop_loss=0.12,
        portfolio_drawdown_brake=0.15,
        fee_rate=0.0040,
        slippage_rate=0.0025,
    ),
    "US": PortfolioRiskPolicy(
        market="US",
        minimum_average_daily_value_mn=1.0,
        max_adv_participation=0.05,
        max_position_weight=0.10,
        max_sector_weight=0.25,
        max_gross_exposure=0.90,
        target_annualized_volatility=0.20,
        position_stop_loss=0.10,
        portfolio_drawdown_brake=0.18,
        fee_rate=0.0005,
        slippage_rate=0.0015,
    ),
}


@dataclass
class _Position:
    shares: int
    average_cost: float


def _half_spread_rate(
    code: str, half_spread_bps: HalfSpreadInput, policy: PortfolioRiskPolicy
) -> float:
    """Resolve the one-way slippage rate for ``code`` given the run's half-spread input."""
    if half_spread_bps is None:
        return policy.slippage_rate
    if isinstance(half_spread_bps, dict):
        measured = half_spread_bps.get(code)
        return measured / 10_000.0 if measured is not None else policy.slippage_rate
    return half_spread_bps / 10_000.0


def _implementation_shortfall_bps(
    *,
    side: Literal["buy", "sell"],
    decision_price: float | None,
    fill_price: float,
) -> float | None:
    """Return signed adverse execution shortfall; negative values are favorable fills."""

    if decision_price is None or decision_price <= 0:
        return None
    adverse_return = (
        fill_price / decision_price - 1 if side == "buy" else 1 - fill_price / decision_price
    )
    return round(adverse_return * 10_000, 3)


def constrain_target_weights(
    target_weights: dict[str, float],
    *,
    security_by_code: dict[str, StrategySecurity],
    policy: PortfolioRiskPolicy,
) -> tuple[dict[str, float], list[str]]:
    """Fail closed and enforce mandate limits on an externally constructed long-only book.

    Signal builders are allowed to propose weights, never to bypass the portfolio mandate. Invalid
    values and unknown securities are removed, then name, sector, and gross limits are applied in
    that order. Sector and gross breaches are scaled proportionally so the ranking signal is
    preserved without allowing iteration order to decide which name receives capital.
    """

    constrained: dict[str, float] = {}
    notes: list[str] = []
    for code, raw_weight in sorted(target_weights.items()):
        security = security_by_code.get(code)
        if security is None:
            notes.append(f"{code}: removed because it is outside the observable universe")
            continue
        if not math.isfinite(raw_weight) or raw_weight <= 0:
            notes.append(f"{code}: removed because target weight is not positive and finite")
            continue
        weight = min(float(raw_weight), policy.max_position_weight)
        if weight < raw_weight:
            notes.append(f"{code}: clipped to the {policy.max_position_weight:.1%} position limit")
        constrained[code] = weight

    by_sector: dict[str, list[str]] = {}
    for code in constrained:
        by_sector.setdefault(security_by_code[code].sector or "Unclassified", []).append(code)
    for sector, codes in sorted(by_sector.items()):
        sector_gross = sum(constrained[code] for code in codes)
        if sector_gross <= policy.max_sector_weight or sector_gross <= 0:
            continue
        scale = policy.max_sector_weight / sector_gross
        for code in codes:
            constrained[code] *= scale
        notes.append(f"{sector}: scaled to the {policy.max_sector_weight:.1%} sector limit")

    gross = sum(constrained.values())
    if gross > policy.max_gross_exposure and gross > 0:
        scale = policy.max_gross_exposure / gross
        constrained = {code: weight * scale for code, weight in constrained.items()}
        notes.append(
            f"portfolio: scaled to the {policy.max_gross_exposure:.1%} gross-exposure limit"
        )
    return ({code: round(weight, 8) for code, weight in constrained.items()}, notes)


def _ladder_from_policy(policy: PortfolioRiskPolicy) -> DrawdownLadder:
    """Two-rung ladder derived from the mandate's single drawdown brake (no schema change).

    The existing ``portfolio_drawdown_brake`` stays the flatten rung, so behavior at that level is
    unchanged; the ladder adds an intermediate halve rung at two-thirds of it (Phase 15 L2).
    """
    flatten_at = policy.portfolio_drawdown_brake
    return DrawdownLadder(halve_at_pct=round(flatten_at * 2.0 / 3.0, 4), flatten_at_pct=flatten_at)


def _returns(values: list[float]) -> list[float]:
    return [
        values[index] / values[index - 1] - 1.0
        for index in range(1, len(values))
        if values[index - 1] > 0
    ]


def _annualized_volatility(values: list[float], lookback: int = 60) -> float | None:
    returns = _returns(values)[-lookback:]
    if len(returns) < 20:
        return None
    return statistics.stdev(returns) * math.sqrt(252)


def _rsi(values: list[float], period: int = 14) -> float | None:
    if len(values) <= period:
        return None
    changes = [
        values[index] - values[index - 1] for index in range(len(values) - period, len(values))
    ]
    gains = sum(max(change, 0.0) for change in changes) / period
    losses = sum(max(-change, 0.0) for change in changes) / period
    if losses == 0:
        return 100.0 if gains > 0 else 50.0
    return 100.0 - 100.0 / (1.0 + gains / losses)


def _feature_score(
    strategy: StrategyDefinition, history: list[StrategyBar]
) -> tuple[float, float, float] | None:
    if len(history) < strategy.minimum_lookback:
        return None
    closes = [bar.close for bar in history]
    volumes = [bar.volume for bar in history]
    volatility = _annualized_volatility(closes)
    if volatility is None or volatility <= 0:
        return None
    average_volume = statistics.fmean(volumes[-20:])
    long_volume = statistics.fmean(volumes[-60:]) if len(volumes) >= 60 else average_volume
    relative_volume = average_volume / long_volume if long_volume > 0 else 0.0
    if strategy.key == "dse_reversal_v1":
        peak = max(closes[-126:])
        drawdown = closes[-1] / peak - 1.0
        return_5 = closes[-1] / closes[-6] - 1.0
        rsi = _rsi(closes) or 50.0
        if drawdown > -0.12 or return_5 <= 0 or rsi > 58 or relative_volume < 0.90:
            return None
        score = abs(drawdown) * 100 + return_5 * 120 + relative_volume * 8 - max(0, rsi - 50)
    else:
        sma_50 = statistics.fmean(closes[-50:])
        sma_200 = statistics.fmean(closes[-200:])
        momentum_63 = closes[-1] / closes[-64] - 1.0
        high_20 = max(closes[-20:])
        extension = closes[-1] / sma_50 - 1.0
        if closes[-1] <= sma_50 or sma_50 <= sma_200 or momentum_63 <= 0 or relative_volume < 0.90:
            return None
        if extension > 0.25:
            return None
        proximity = closes[-1] / high_20
        score = momentum_63 * 100 + proximity * 20 + relative_volume * 8 - volatility * 10
    return score, volatility, average_volume


def _target_weights(
    strategy: StrategyDefinition,
    policy: PortfolioRiskPolicy,
    histories: dict[str, list[StrategyBar]],
    securities: dict[str, StrategySecurity],
) -> dict[str, float]:
    ranked: list[tuple[float, str, float]] = []
    for code, history in histories.items():
        feature = _feature_score(strategy, history)
        if feature is None:
            continue
        score, volatility, average_volume = feature
        average_value_mn = average_volume * history[-1].close / 1_000_000
        if average_value_mn < policy.minimum_average_daily_value_mn:
            continue
        ranked.append((score, code, volatility))
    ranked.sort(reverse=True)

    weights: dict[str, float] = {}
    sector_weights: dict[str, float] = {}
    remaining = policy.max_gross_exposure
    for _, code, volatility in ranked[: strategy.maximum_positions]:
        if remaining <= 0:
            break
        sector = securities[code].sector
        volatility_weight = policy.target_annualized_volatility / max(volatility, 0.05)
        desired = min(
            policy.max_position_weight,
            policy.max_gross_exposure / strategy.maximum_positions * volatility_weight,
            policy.max_sector_weight - sector_weights.get(sector, 0.0),
            remaining,
        )
        if desired <= 0.005:
            continue
        weights[code] = round(desired, 6)
        sector_weights[sector] = sector_weights.get(sector, 0.0) + desired
        remaining -= desired
    return weights


def _performance_slice(
    label: Literal["full", "train", "validation", "test"], nav: list[float]
) -> PerformanceSlice:
    if len(nav) < 2 or nav[0] <= 0:
        return PerformanceSlice(
            label=label,
            sessions=len(nav),
            total_return_pct=None,
            annualized_return_pct=None,
            annualized_volatility_pct=None,
            sharpe=None,
            sortino=None,
            max_drawdown_pct=None,
        )
    returns = _returns(nav)
    total = nav[-1] / nav[0] - 1.0
    years = max((len(nav) - 1) / 252, 1 / 252)
    annualized = (1 + total) ** (1 / years) - 1 if total > -1 else -1.0
    volatility = statistics.stdev(returns) * math.sqrt(252) if len(returns) > 1 else 0.0
    average = statistics.fmean(returns) if returns else 0.0
    downside = [min(value, 0.0) for value in returns]
    downside_deviation = (
        math.sqrt(statistics.fmean(value * value for value in downside)) * math.sqrt(252)
        if downside
        else 0.0
    )
    peak = nav[0]
    maximum_drawdown = 0.0
    for value in nav:
        peak = max(peak, value)
        maximum_drawdown = max(maximum_drawdown, 1.0 - value / peak)
    return PerformanceSlice(
        label=label,
        sessions=len(nav),
        total_return_pct=round(total * 100, 3),
        annualized_return_pct=round(annualized * 100, 3),
        annualized_volatility_pct=round(volatility * 100, 3),
        sharpe=round(average * 252 / volatility, 3) if volatility > 0 else None,
        sortino=round(average * 252 / downside_deviation, 3) if downside_deviation > 0 else None,
        max_drawdown_pct=round(maximum_drawdown * 100, 3),
    )


def run_backtest(
    *,
    market: Literal["DSE", "US"],
    strategy_key: StrategyKey,
    securities: list[StrategySecurity],
    initial_capital: float = 100_000.0,
    inactive_security_history_complete: bool = False,
    point_in_time_inputs_complete: bool = False,
    risk_policy: PortfolioRiskPolicy | None = None,
    half_spread_bps: HalfSpreadInput = None,
    weight_schedule: dict[dt.date, dict[str, float]] | None = None,
    execution_timing: ExecutionTiming = "next_open",
    use_point_in_time_spread: bool = False,
    benchmark_series: BenchmarkSeries | None = None,
) -> BacktestResult:
    """Run the registered strategy with next-session execution and deterministic risk gates.

    ``weight_schedule`` drives event- and factor-driven books whose targets are decided outside
    the price-feature engine (System A's filings book, System C's factor sleeve). When supplied,
    the strategy's own signal is never consulted; targets are taken from the schedule on the dates
    it specifies. Execution, costs, ADV limits and the drawdown ladder are identical either way,
    which is the point of routing every book through one engine.

    ``execution_timing`` is frozen with the experiment. ``next_close`` still delays every target by
    a full observable session; it never fills on the close that formed the signal.

    ``half_spread_bps`` selects the trading-cost model (see ``HalfSpreadInput``); the default keeps
    the policy's flat slippage. When ``use_point_in_time_spread`` is true, each order estimates its
    half-spread using only bars completed before that order. The drawdown response is the two-rung
    ladder (halve then flatten and freeze). A historical run cannot invent the written review
    required to clear a freeze, so it stays flat and becomes diagnostic after that transition.
    """

    if initial_capital <= 0:
        raise ValueError("initial_capital must be positive")
    if execution_timing not in {"next_open", "next_close"}:
        raise ValueError(f"unknown execution timing {execution_timing!r}")
    strategy = STRATEGIES[strategy_key]
    if strategy.market != market:
        raise ValueError(f"Strategy {strategy_key} is not registered for {market}")
    policy = risk_policy or RISK_POLICIES[market]
    if policy.market != market:
        raise ValueError("risk policy belongs to another market")
    ladder = _ladder_from_policy(policy)
    security_by_code = {security.code: security for security in securities}
    bars_by_code = {
        security.code: {bar.date: bar for bar in sorted(security.bars, key=lambda item: item.date)}
        for security in securities
    }
    dates = sorted({date for bars in bars_by_code.values() for date in bars})
    benchmark_by_date = (
        {point.date: point.close for point in benchmark_series.points}
        if benchmark_series is not None
        else {}
    )
    benchmark_method: Literal["explicit_series", "observable_universe_equal_weight"] = (
        "explicit_series" if benchmark_series is not None else "observable_universe_equal_weight"
    )
    benchmark_key = (
        benchmark_series.key
        if benchmark_series is not None
        else f"{market.lower()}_observable_universe_equal_weight"
    )
    benchmark_label = (
        benchmark_series.label
        if benchmark_series is not None
        else "Observable-universe equal weight (diagnostic)"
    )
    histories: dict[str, list[StrategyBar]] = {code: [] for code in bars_by_code}
    positions: dict[str, _Position] = {}
    cash = initial_capital
    pending_weights: dict[str, float] | None = None
    pending_reason = "scheduled rebalance"
    pending_decision_prices: dict[str, float] = {}
    trades: list[BacktestTrade] = []
    curve: list[EquityPoint] = []
    interventions: list[RiskIntervention] = []
    fees_paid = 0.0
    traded_gross = 0.0
    peak_nav = initial_capital
    benchmark = initial_capital
    previous_benchmark_close: float | None = None
    benchmark_observations = 0
    latest_target_weights: dict[str, float] = {}
    ladder_multiplier = 1.0
    ladder_state = LadderState()
    historical_freeze_triggered = False

    for session_index, date in enumerate(dates):
        current = {code: bars.get(date) for code, bars in bars_by_code.items()}

        if pending_weights is not None:
            retry_pending_target = False
            execution_nav = cash
            for code, position in positions.items():
                bar = current.get(code)
                if bar is not None:
                    reference_price = bar.open if execution_timing == "next_open" else bar.close
                    execution_nav += position.shares * reference_price
                elif histories[code]:
                    execution_nav += position.shares * histories[code][-1].close
            all_codes = set(positions) | set(pending_weights)
            prioritized_codes: list[tuple[int, str]] = []
            for code in all_codes:
                bar = current.get(code)
                if bar is None:
                    prioritized_codes.append((2, code))
                    continue
                reference_price = bar.open if execution_timing == "next_open" else bar.close
                current_shares = positions.get(code, _Position(0, 0.0)).shares
                desired_shares = int(
                    execution_nav * pending_weights.get(code, 0.0) / reference_price
                )
                prioritized_codes.append((0 if desired_shares < current_shares else 1, code))

            for _, code in sorted(prioritized_codes):
                bar = current.get(code)
                if bar is None:
                    retry_pending_target = True
                    interventions.append(
                        RiskIntervention(
                            date=date,
                            code=code,
                            rule="execution_bar_missing",
                            detail=(
                                f"Target could not execute at the {execution_timing.removeprefix('next_')} "
                                "because no observable bar was available."
                            ),
                        )
                    )
                    continue
                current_shares = positions.get(code, _Position(0, 0.0)).shares
                reference_price = bar.open if execution_timing == "next_open" else bar.close
                desired_value = execution_nav * pending_weights.get(code, 0.0)
                desired_shares = int(desired_value / reference_price)
                quantity = desired_shares - current_shares
                intended_quantity = abs(quantity)
                constraint_notes: list[str] = []
                history = histories[code]
                average_volume = (
                    statistics.fmean(item.volume for item in history[-20:]) if history else 0.0
                )
                max_quantity = int(average_volume * policy.max_adv_participation)
                if max_quantity <= 0 and quantity != 0:
                    interventions.append(
                        RiskIntervention(
                            date=date,
                            code=code,
                            rule="liquidity_unknown",
                            detail="Order rejected because a completed ADV baseline was unavailable.",
                        )
                    )
                    continue
                clipped_quantity = max(-max_quantity, min(max_quantity, quantity))
                if clipped_quantity != quantity:
                    constraint_notes.append(
                        f"ADV participation clipped {intended_quantity} intended shares "
                        f"to {abs(clipped_quantity)}"
                    )
                    interventions.append(
                        RiskIntervention(
                            date=date,
                            code=code,
                            rule="adv_participation_limit",
                            detail=constraint_notes[-1],
                        )
                    )
                quantity = clipped_quantity
                if quantity == 0:
                    continue
                side: Literal["buy", "sell"] = "buy" if quantity > 0 else "sell"
                if use_point_in_time_spread:
                    spread = estimate_spread(
                        code,
                        [item.high for item in history],
                        [item.low for item in history],
                    )
                    slippage_rate = (
                        spread.half_spread_bps / 10_000.0
                        if spread is not None
                        else policy.slippage_rate
                    )
                else:
                    slippage_rate = _half_spread_rate(code, half_spread_bps, policy)
                fill_price = reference_price * (
                    1 + slippage_rate if side == "buy" else 1 - slippage_rate
                )
                absolute_quantity = abs(quantity)
                gross = absolute_quantity * fill_price
                fee = gross * policy.fee_rate
                if side == "buy":
                    affordable = int(cash / (fill_price * (1 + policy.fee_rate)))
                    if affordable < absolute_quantity:
                        constraint_notes.append(
                            f"settled cash clipped {absolute_quantity} shares to {affordable}"
                        )
                        interventions.append(
                            RiskIntervention(
                                date=date,
                                code=code,
                                rule="cash_limit",
                                detail=constraint_notes[-1],
                            )
                        )
                    absolute_quantity = min(absolute_quantity, affordable)
                    if absolute_quantity <= 0:
                        interventions.append(
                            RiskIntervention(
                                date=date,
                                code=code,
                                rule="cash_limit",
                                detail="Buy was rejected because settled cash was insufficient.",
                            )
                        )
                        continue
                    gross = absolute_quantity * fill_price
                    fee = gross * policy.fee_rate
                    old = positions.get(code, _Position(0, 0.0))
                    new_shares = old.shares + absolute_quantity
                    average_cost = (
                        (old.average_cost * old.shares + gross + fee) / new_shares
                        if new_shares
                        else 0.0
                    )
                    positions[code] = _Position(new_shares, average_cost)
                    cash -= gross + fee
                else:
                    absolute_quantity = min(absolute_quantity, current_shares)
                    if absolute_quantity <= 0:
                        continue
                    gross = absolute_quantity * fill_price
                    fee = gross * policy.fee_rate
                    remaining = current_shares - absolute_quantity
                    cash += gross - fee
                    if remaining:
                        positions[code].shares = remaining
                    else:
                        positions.pop(code, None)
                fees_paid += fee
                traded_gross += gross
                trades.append(
                    BacktestTrade(
                        date=date,
                        code=code,
                        side=side,
                        quantity=absolute_quantity,
                        fill_price=round(fill_price, 4),
                        gross_value=round(gross, 2),
                        fee=round(fee, 2),
                        reason=pending_reason,
                        intended_quantity=intended_quantity or None,
                        constraint_notes=constraint_notes,
                        decision_reference_price=pending_decision_prices.get(code),
                        implementation_shortfall_bps=_implementation_shortfall_bps(
                            side=side,
                            decision_price=pending_decision_prices.get(code),
                            fill_price=fill_price,
                        ),
                    )
                )
            if not retry_pending_target:
                pending_weights = None
                pending_decision_prices = {}

        previous_closes: list[float] = []
        current_closes: list[float] = []
        for code, bar in current.items():
            if bar is None:
                continue
            history = histories[code]
            if history:
                previous_closes.append(history[-1].close)
                current_closes.append(bar.close)
            history.append(bar)
        if benchmark_series is not None:
            benchmark_close = benchmark_by_date.get(date)
            if benchmark_close is not None:
                benchmark_observations += 1
                if previous_benchmark_close is not None:
                    benchmark *= benchmark_close / previous_benchmark_close
                previous_benchmark_close = benchmark_close
        elif previous_closes and len(previous_closes) == len(current_closes):
            benchmark *= 1 + statistics.fmean(
                current_close / previous_close - 1.0
                for previous_close, current_close in zip(
                    previous_closes, current_closes, strict=True
                )
                if previous_close > 0
            )

        nav = cash
        for code, position in positions.items():
            bar = current.get(code)
            if bar is not None:
                nav += position.shares * bar.close
            elif histories[code]:
                nav += position.shares * histories[code][-1].close
                interventions.append(
                    RiskIntervention(
                        date=date,
                        code=code,
                        rule="stale_mark",
                        detail=(
                            "No completed bar was available; NAV carried the last observable "
                            "close and no execution was permitted."
                        ),
                    )
                )
        peak_nav = max(peak_nav, nav)
        drawdown = 1.0 - nav / peak_nav if peak_nav > 0 else 0.0
        gross_exposure = (nav - cash) / nav if nav > 0 else 0.0
        curve.append(
            EquityPoint(
                date=date,
                nav=round(nav, 2),
                benchmark=round(benchmark, 2),
                cash=round(cash, 2),
                gross_exposure_pct=round(gross_exposure * 100, 3),
                drawdown_pct=round(drawdown * 100, 3),
            )
        )

        stopped_codes = {
            code
            for code, position in positions.items()
            if current.get(code) is not None
            and current[code].close / position.average_cost - 1.0 <= -policy.position_stop_loss
        }
        if stopped_codes:
            target = latest_target_weights.copy()
            for code in stopped_codes:
                target.pop(code, None)
                interventions.append(
                    RiskIntervention(
                        date=date,
                        code=code,
                        rule="position_stop",
                        detail=(
                            f"Next-{execution_timing.removeprefix('next_')} exit scheduled after a "
                            f"{policy.position_stop_loss:.0%} loss threshold."
                        ),
                    )
                )
            latest_target_weights = target
        # The freeze is part of the strategy path. A historical simulation cannot fabricate the
        # written review required to clear it, so the book remains flat after the second rung.
        was_frozen = ladder_state.frozen
        ladder_action = apply_drawdown_ladder(
            drawdown_pct=max(drawdown, 0.0), state=ladder_state, ladder=ladder
        )
        ladder_state = LadderState(frozen=ladder_action.frozen)
        proposed_target: dict[str, float] | None = None
        proposed_reason = ""
        if weight_schedule is not None:
            scheduled = weight_schedule.get(date)
            if scheduled is not None:
                proposed_target, constraint_notes = constrain_target_weights(
                    scheduled, security_by_code=security_by_code, policy=policy
                )
                for detail in constraint_notes:
                    interventions.append(
                        RiskIntervention(
                            date=date,
                            rule="target_weight_constraint",
                            detail=detail,
                        )
                    )
                latest_target_weights = proposed_target
                proposed_reason = "externally scheduled target weights"
        elif (
            session_index >= strategy.minimum_lookback
            and session_index % strategy.rebalance_sessions == 0
        ):
            raw_target = _target_weights(strategy, policy, histories, security_by_code)
            proposed_target, constraint_notes = constrain_target_weights(
                raw_target, security_by_code=security_by_code, policy=policy
            )
            for detail in constraint_notes:
                interventions.append(
                    RiskIntervention(
                        date=date,
                        rule="target_weight_constraint",
                        detail=detail,
                    )
                )
            latest_target_weights = proposed_target
            proposed_reason = "scheduled point-in-time rebalance"

        if stopped_codes:
            for code in stopped_codes:
                latest_target_weights.pop(code, None)
                if proposed_target is not None:
                    proposed_target.pop(code, None)

        multiplier_changed = ladder_action.gross_multiplier != ladder_multiplier
        ladder_multiplier = ladder_action.gross_multiplier
        if ladder_multiplier == 0.0:
            ladder_changed_target = (
                multiplier_changed or proposed_target is not None or stopped_codes
            )
            latest_target_weights = {}
            if ladder_changed_target:
                pending_weights = {}
                pending_reason = "drawdown ladder: flatten"
                pending_decision_prices = {
                    code: current[code].close for code in positions if current.get(code) is not None
                }
            if ladder_action.frozen and not was_frozen:
                historical_freeze_triggered = True
                interventions.append(
                    RiskIntervention(
                        date=date,
                        rule="drawdown_ladder_flatten",
                        detail=ladder_action.detail,
                    )
                )
            elif was_frozen and proposed_target is not None:
                interventions.append(
                    RiskIntervention(
                        date=date,
                        rule="frozen_target_rejected",
                        detail=(
                            "A scheduled target was suppressed because the historical book "
                            "remains frozen pending a review that cannot be fabricated."
                        ),
                    )
                )
        elif proposed_target is not None or stopped_codes or multiplier_changed:
            if (
                pending_weights is None
                or stopped_codes
                or proposed_target is not None
                or multiplier_changed
            ):
                pending_weights = {
                    code: round(weight * ladder_multiplier, 8)
                    for code, weight in latest_target_weights.items()
                }
                pending_decision_prices = {
                    code: current[code].close
                    for code in set(positions) | set(pending_weights)
                    if current.get(code) is not None
                }
                pending_reason = (
                    "position risk stop"
                    if stopped_codes
                    else proposed_reason or "drawdown ladder exposure restoration"
                )
            if ladder_multiplier < 1.0:
                pending_reason = f"{pending_reason} (halved by drawdown ladder)"
                interventions.append(
                    RiskIntervention(
                        date=date, rule="drawdown_ladder_halve", detail=ladder_action.detail
                    )
                )

    nav_values = [point.nav for point in curve]
    split_1 = max(2, round(len(nav_values) * 0.6))
    split_2 = max(split_1 + 1, round(len(nav_values) * 0.8))
    metrics = [
        _performance_slice("full", nav_values),
        _performance_slice("train", nav_values[:split_1]),
        _performance_slice("validation", nav_values[split_1 - 1 : split_2]),
        _performance_slice("test", nav_values[split_2 - 1 :]),
    ]
    regime_slices = robustness_slices(curve)
    failed_gates: list[str] = []
    benchmark_coverage_pct = (
        benchmark_observations / len(dates) * 100.0
        if benchmark_series is not None and dates
        else (100.0 if dates else 0.0)
    )
    benchmark_valid = (
        benchmark_series is not None
        and bool(dates)
        and benchmark_coverage_pct >= 98.0
        and dates[0] in benchmark_by_date
        and dates[-1] in benchmark_by_date
    )
    if len(dates) < 756:
        failed_gates.append("Fewer than three years of completed sessions.")
    if len(securities) < 20:
        failed_gates.append("Universe contains fewer than 20 securities.")
    if not inactive_security_history_complete:
        failed_gates.append("Inactive and delisted security history is not complete.")
    if not point_in_time_inputs_complete:
        failed_gates.append("Point-in-time input revisions are not complete for the test window.")
    if len(trades) < 30:
        failed_gates.append("Fewer than 30 completed executions are available for inference.")
    if benchmark_series is None:
        failed_gates.append(
            "An explicit independent market benchmark was not supplied; the universe baseline "
            "is diagnostic only."
        )
    elif not benchmark_valid:
        failed_gates.append(
            "The explicit benchmark does not cover at least 98% of strategy sessions including "
            "the first and final session."
        )
    if historical_freeze_triggered:
        failed_gates.append(
            "The drawdown ladder froze the historical book; no unrecorded review was invented to re-arm it."
        )
    validation_status: Literal["diagnostic", "eligible_for_shadow"] = (
        "eligible_for_shadow" if not failed_gates else "diagnostic"
    )
    return BacktestResult(
        engine_version=ENGINE_VERSION,
        strategy=strategy,
        risk_policy=policy,
        start_date=dates[0] if dates else None,
        end_date=dates[-1] if dates else None,
        initial_capital=initial_capital,
        final_nav=round(nav_values[-1] if nav_values else initial_capital, 2),
        benchmark_final=round(benchmark, 2),
        benchmark_key=benchmark_key,
        benchmark_label=benchmark_label,
        benchmark_method=benchmark_method,
        benchmark_coverage_pct=round(benchmark_coverage_pct, 3),
        benchmark_valid=benchmark_valid,
        trades=trades,
        equity_curve=curve,
        risk_interventions=interventions,
        metrics=metrics,
        robustness_slices=regime_slices,
        turnover_pct=round(traded_gross / initial_capital * 100, 3),
        fees_paid=round(fees_paid, 2),
        validation_status=validation_status,
        failed_gates=failed_gates,
        warnings=[
            "Results are research diagnostics, not expected returns or a recommendation.",
            (
                "The benchmark is an independently supplied completed-close series."
                if benchmark_series is not None
                else "The displayed baseline is an equal-weight observable-universe diagnostic "
                "and shares current-universe bias; it is not a market benchmark."
            ),
            "Fundamental and universe filters are validation-safe only when point-in-time input coverage is complete.",
            (
                "Corporate-action safety depends on adjustment coverage; fills use the "
                f"{execution_timing.replace('_', '-')} supplied by the point-in-time price adapter."
            ),
            "A missing held-security bar carries the last observable close and records a stale-mark intervention.",
        ],
        latest_target_weights=latest_target_weights,
    )


class CostTierOutcome(BaseModel):
    """One backtest run's headline result at a single trading-cost assumption."""

    tier: CostTier
    final_nav: float
    net_return_pct: float
    benchmark_return_pct: float
    excess_return_pct: float
    max_drawdown_pct: float | None
    sharpe: float | None
    trades: int
    # True when this tier's net return still beats the benchmark after its costs.
    edge_survives: bool


class CostTieredBacktest(BaseModel):
    """A strategy run across the measured cost and the 10/30/50 bps stress floors (Phase 13.2)."""

    engine_version: str
    strategy_key: str
    fee_bps: float
    # Per-name measured half-spreads (bps); names too thin to measure are absent.
    measured_half_spread_bps: dict[str, float]
    universe_size: int
    measured_coverage: int
    outcomes: list[CostTierOutcome]
    # Lowest one-way cost (bps) at which the edge no longer beats the benchmark, if any.
    edge_dies_at_bps: float | None
    # The authoritative full backtest at the realistic cost basis (measured per-name half-spreads
    # when available, otherwise the lightest stress tier) — the run the validation gate scores.
    primary: BacktestResult


def run_cost_tiered_backtest(
    *,
    market: Literal["DSE", "US"],
    strategy_key: StrategyKey,
    securities: list[StrategySecurity],
    initial_capital: float = 100_000.0,
    inactive_security_history_complete: bool = False,
    point_in_time_inputs_complete: bool = False,
    risk_policy: PortfolioRiskPolicy | None = None,
    stress_levels_bps: tuple[float, ...] = (10.0, 30.0, 50.0),
    weight_schedule: dict[dt.date, dict[str, float]] | None = None,
    execution_timing: ExecutionTiming = "next_open",
    benchmark_series: BenchmarkSeries | None = None,
) -> CostTieredBacktest:
    """Run the strategy at its measured per-name cost and at fixed one-way stress floors.

    Phase 13.2's rule: "any system whose edge dies at 30 bps one-way in its actual universe is
    dead." Every tier's ``one_way_bps`` is a *total* one-way cost (half-spread + fee), so the
    tiers are directly comparable. The measured tier uses Corwin-Schultz per-name half-spreads;
    the stress tiers hold total one-way cost at 10/30/50 bps regardless of what was measured.
    """
    policy = risk_policy or RISK_POLICIES[market]
    fee_bps = policy.fee_rate * 10_000.0

    measured: dict[str, float] = {}
    for security in securities:
        estimate = estimate_spread(
            security.code,
            [bar.high for bar in security.bars],
            [bar.low for bar in security.bars],
        )
        if estimate is not None:
            measured[security.code] = round(estimate.half_spread_bps, 4)
    measured_average = statistics.fmean(measured.values()) if measured else None

    tiers = cost_tiers(
        measured_half_spread_bps=measured_average,
        fee_bps=fee_bps,
        stress_levels_bps=stress_levels_bps,
    )

    def _run(tier: CostTier) -> BacktestResult:
        if tier.measured:
            return run_backtest(
                market=market,
                strategy_key=strategy_key,
                securities=securities,
                initial_capital=initial_capital,
                inactive_security_history_complete=inactive_security_history_complete,
                point_in_time_inputs_complete=point_in_time_inputs_complete,
                risk_policy=policy,
                half_spread_bps=measured,
                weight_schedule=weight_schedule,
                execution_timing=execution_timing,
                use_point_in_time_spread=True,
                benchmark_series=benchmark_series,
            )
        # Hold total one-way cost at the tier: half-spread = tier - fee (the engine adds fee back).
        flat_half_spread = max(tier.one_way_bps - fee_bps, 0.0)
        return run_backtest(
            market=market,
            strategy_key=strategy_key,
            securities=securities,
            initial_capital=initial_capital,
            inactive_security_history_complete=inactive_security_history_complete,
            point_in_time_inputs_complete=point_in_time_inputs_complete,
            risk_policy=policy,
            half_spread_bps=flat_half_spread,
            weight_schedule=weight_schedule,
            execution_timing=execution_timing,
            benchmark_series=benchmark_series,
        )

    outcomes: list[CostTierOutcome] = []
    primary: BacktestResult | None = None
    for tier in tiers:
        result = _run(tier)
        # The realistic basis is the measured tier; if nothing was measurable, the first (lightest)
        # tier stands in so a run always has an authoritative full result to score.
        if primary is None or tier.measured:
            primary = result
        net = (result.final_nav / initial_capital - 1.0) * 100.0
        benchmark = (result.benchmark_final / initial_capital - 1.0) * 100.0
        outcomes.append(
            CostTierOutcome(
                tier=tier,
                final_nav=result.final_nav,
                net_return_pct=round(net, 3),
                benchmark_return_pct=round(benchmark, 3),
                excess_return_pct=round(net - benchmark, 3),
                max_drawdown_pct=result.metrics[0].max_drawdown_pct,
                sharpe=result.metrics[0].sharpe,
                trades=len(result.trades),
                edge_survives=result.benchmark_valid and net - benchmark > 0,
            )
        )

    # The cheapest stress tier at which the edge stops beating the benchmark — where it "dies".
    dead_tiers = sorted(
        outcome.tier.one_way_bps
        for outcome in outcomes
        if not outcome.tier.measured and not outcome.edge_survives
    )
    if primary is None:
        # No tiers at all only happens with an empty stress set and no measurable spread; run once
        # at the policy default so the caller always receives an authoritative result.
        primary = run_backtest(
            market=market,
            strategy_key=strategy_key,
            securities=securities,
            initial_capital=initial_capital,
            inactive_security_history_complete=inactive_security_history_complete,
            point_in_time_inputs_complete=point_in_time_inputs_complete,
            risk_policy=policy,
            weight_schedule=weight_schedule,
            execution_timing=execution_timing,
        )
    return CostTieredBacktest(
        engine_version=ENGINE_VERSION,
        strategy_key=strategy_key,
        fee_bps=round(fee_bps, 4),
        measured_half_spread_bps=measured,
        universe_size=len(securities),
        measured_coverage=len(measured),
        outcomes=outcomes,
        edge_dies_at_bps=dead_tiers[0] if dead_tiers else None,
        primary=primary,
    )


def advance_shadow_portfolio(
    *,
    market: Literal["DSE", "US"],
    strategy_key: StrategyKey,
    securities: list[StrategySecurity],
    previous: ShadowState,
    target_weights: dict[str, float],
    session_number: int,
    risk_policy: PortfolioRiskPolicy | None = None,
    execution_timing: ExecutionTiming = "next_open",
    next_target_weights: dict[str, float] | None = None,
    benchmark_return: float | None = None,
) -> ShadowAdvanceResult:
    """Advance one real-time shadow book by one completed market session.

    ``target_weights`` must have been formed after the previous completed session. It executes at
    the strategy's frozen current-session open/close. Event and factor adapters may supply
    ``next_target_weights`` formed after observing this close; legacy price strategies calculate
    their next target inside the engine.

    ``benchmark_return`` is the completed-session return of an explicit independent market
    series (SPY / DSEX). When supplied, ``benchmark_nav`` compounds it; when None, the legacy
    equal-weight observable-universe diagnostic is used — a basis that can never support
    promotion (see ``evaluate_shadow_promotion``).
    """

    strategy = STRATEGIES[strategy_key]
    if strategy.market != market:
        raise ValueError(f"Strategy {strategy_key} is not registered for {market}")
    if not securities:
        raise ValueError("shadow portfolio requires current security history")
    dates = {security.bars[-1].date for security in securities if security.bars}
    if len(dates) != 1:
        raise ValueError("shadow portfolio securities must share one completed session date")
    date = dates.pop()
    policy = risk_policy or RISK_POLICIES[market]
    if policy.market != market:
        raise ValueError("risk policy belongs to another market")
    by_code = {security.code: security for security in securities}
    positions = {
        code: _Position(position.shares, position.average_cost)
        for code, position in previous.positions.items()
    }
    cash = previous.cash
    trades: list[BacktestTrade] = []
    interventions: list[RiskIntervention] = []
    session_fees = 0.0
    session_turnover = 0.0

    def reference(security: StrategySecurity) -> float:
        return (
            security.bars[-1].open if execution_timing == "next_open" else security.bars[-1].close
        )

    execution_nav = cash + sum(
        position.shares * reference(by_code[code])
        for code, position in positions.items()
        if code in by_code
    )
    for code in sorted(set(positions) | set(target_weights)):
        security = by_code.get(code)
        if security is None or len(security.bars) < 21:
            continue
        reference_price = reference(security)
        current_shares = positions.get(code, _Position(0, 0)).shares
        desired_shares = int(execution_nav * target_weights.get(code, 0.0) / reference_price)
        quantity = desired_shares - current_shares
        intended_quantity = abs(quantity)
        average_volume = statistics.fmean(item.volume for item in security.bars[-21:-1])
        maximum_quantity = int(average_volume * policy.max_adv_participation)
        quantity = max(-maximum_quantity, min(maximum_quantity, quantity))
        constraint_notes: list[str] = []
        if abs(quantity) < intended_quantity:
            constraint_notes.append("adv_capacity")
            interventions.append(
                RiskIntervention(
                    date=date,
                    code=code,
                    rule="adv_capacity",
                    detail=(
                        f"Order constrained from {intended_quantity} to {abs(quantity)} shares "
                        "by the mandate ADV participation ceiling."
                    ),
                )
            )
        if quantity == 0:
            continue
        side: Literal["buy", "sell"] = "buy" if quantity > 0 else "sell"
        fill_price = reference_price * (
            1 + policy.slippage_rate if side == "buy" else 1 - policy.slippage_rate
        )
        absolute_quantity = abs(quantity)
        if side == "buy":
            affordable = int(cash / (fill_price * (1 + policy.fee_rate)))
            before_cash_constraint = absolute_quantity
            absolute_quantity = min(absolute_quantity, affordable)
            if absolute_quantity <= 0:
                interventions.append(
                    RiskIntervention(
                        date=date,
                        code=code,
                        rule="cash_limit",
                        detail="Buy rejected because settled shadow cash was insufficient.",
                    )
                )
                continue
            if absolute_quantity < before_cash_constraint:
                constraint_notes.append("cash_capacity")
                interventions.append(
                    RiskIntervention(
                        date=date,
                        code=code,
                        rule="cash_capacity",
                        detail=(
                            f"Order constrained from {before_cash_constraint} to "
                            f"{absolute_quantity} shares by settled shadow cash."
                        ),
                    )
                )
            gross = absolute_quantity * fill_price
            fee = gross * policy.fee_rate
            old = positions.get(code, _Position(0, 0))
            new_shares = old.shares + absolute_quantity
            positions[code] = _Position(
                shares=new_shares,
                average_cost=(old.average_cost * old.shares + gross + fee) / new_shares,
            )
            cash -= gross + fee
        else:
            absolute_quantity = min(absolute_quantity, current_shares)
            if absolute_quantity <= 0:
                continue
            gross = absolute_quantity * fill_price
            fee = gross * policy.fee_rate
            cash += gross - fee
            remaining = current_shares - absolute_quantity
            if remaining:
                positions[code].shares = remaining
            else:
                positions.pop(code, None)
        session_fees += fee
        session_turnover += gross
        trades.append(
            BacktestTrade(
                date=date,
                code=code,
                side=side,
                quantity=absolute_quantity,
                fill_price=round(fill_price, 4),
                gross_value=round(gross, 2),
                fee=round(fee, 2),
                reason=f"prior-session shadow target ({execution_timing.replace('_', '-')})",
                intended_quantity=intended_quantity,
                constraint_notes=constraint_notes,
                decision_reference_price=security.bars[-2].close,
                implementation_shortfall_bps=_implementation_shortfall_bps(
                    side=side,
                    decision_price=security.bars[-2].close,
                    fill_price=fill_price,
                ),
            )
        )

    nav = cash + sum(
        position.shares * by_code[code].bars[-1].close
        for code, position in positions.items()
        if code in by_code
    )
    peak_nav = max(previous.peak_nav, nav)
    drawdown = 1 - nav / peak_nav if peak_nav > 0 else 0.0
    gross_exposure = (nav - cash) / nav if nav > 0 else 0.0
    if benchmark_return is not None:
        benchmark_nav = previous.benchmark_nav * (1 + benchmark_return)
    else:
        benchmark_returns = [
            security.bars[-1].close / security.bars[-2].close - 1
            for security in securities
            if len(security.bars) >= 2 and security.bars[-2].close > 0
        ]
        benchmark_nav = previous.benchmark_nav * (
            1 + statistics.fmean(benchmark_returns) if benchmark_returns else 1
        )
    histories = {security.code: security.bars for security in securities}
    if next_target_weights is not None:
        next_targets, constraint_notes = constrain_target_weights(
            next_target_weights,
            security_by_code=by_code,
            policy=policy,
        )
        interventions.extend(
            RiskIntervention(
                date=date,
                rule="target_weight_constraint",
                detail=detail,
            )
            for detail in constraint_notes
        )
    elif strategy.key in {
        "us_activist_13d_v1",
        "us_insider_cluster_v1",
        "us_forced_seller_v1",
        "us_factor_sleeve_v1",
    }:
        next_targets = target_weights.copy()
    else:
        next_targets = (
            _target_weights(strategy, policy, histories, by_code)
            if session_number % strategy.rebalance_sessions == 0
            else target_weights.copy()
        )
    for code, position in positions.items():
        security = by_code.get(code)
        if (
            security is not None
            and security.bars[-1].close / position.average_cost - 1 <= -policy.position_stop_loss
        ):
            next_targets.pop(code, None)
            interventions.append(
                RiskIntervention(
                    date=date,
                    code=code,
                    rule="position_stop",
                    detail=(
                        f"Next-{execution_timing.removeprefix('next_')} exit required by the "
                        "deterministic position stop."
                    ),
                )
            )
    # Two-rung drawdown ladder with the LIVE freeze semantics: a book that trips the flatten rung
    # stays flat until an operator clears the freeze after a written review (Phase 15 L2). The
    # freeze carries in ShadowState across sessions, so a mechanical NAV recovery cannot silently
    # re-arm the book.
    ladder = _ladder_from_policy(policy)
    ladder_action = apply_drawdown_ladder(
        drawdown_pct=max(drawdown, 0.0),
        state=LadderState(frozen=previous.ladder_frozen),
        ladder=ladder,
    )
    ladder_frozen = ladder_action.frozen
    if ladder_action.gross_multiplier == 0.0:
        next_targets = {}
        interventions.append(
            RiskIntervention(date=date, rule="drawdown_ladder_flatten", detail=ladder_action.detail)
        )
    elif ladder_action.gross_multiplier < 1.0:
        next_targets = {
            code: round(weight * ladder_action.gross_multiplier, 6)
            for code, weight in next_targets.items()
        }
        interventions.append(
            RiskIntervention(date=date, rule="drawdown_ladder_halve", detail=ladder_action.detail)
        )
    state = ShadowState(
        cash=round(cash, 4),
        positions={
            code: ShadowPosition(shares=position.shares, average_cost=position.average_cost)
            for code, position in positions.items()
        },
        peak_nav=round(peak_nav, 4),
        benchmark_nav=round(benchmark_nav, 4),
        cumulative_fees=round(previous.cumulative_fees + session_fees, 4),
        cumulative_turnover=round(previous.cumulative_turnover + session_turnover, 4),
        ladder_frozen=ladder_frozen,
    )
    return ShadowAdvanceResult(
        date=date,
        state=state,
        nav=round(nav, 2),
        gross_exposure_pct=round(gross_exposure * 100, 3),
        drawdown_pct=round(drawdown * 100, 3),
        trades=trades,
        risk_interventions=interventions,
        next_target_weights=next_targets,
    )
