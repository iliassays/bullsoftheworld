"""Point-in-time backtest and shadow-book engine for Bulls Atlas.

Signals use completed bars through T and trades fill no earlier than the next available session open.
The engine is deliberately long-only until market-specific borrowing and locate data exist.
"""

from __future__ import annotations

import datetime as dt
import math
import statistics
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, Field

from bulls.core.markets import add_market_sessions, get_market_profile

ENGINE_VERSION = "atlas-portfolio-engine-v3"
DSE_SETTLEMENT_RULE_EFFECTIVE_FROM = dt.date(2024, 7, 2)
US_T1_RULE_EFFECTIVE_FROM = dt.date(2024, 5, 28)


class StrategyBar(BaseModel):
    date: dt.date
    open: float = Field(gt=0)
    high: float = Field(gt=0)
    low: float = Field(gt=0)
    close: float = Field(gt=0)
    # Valuation features use the contemporaneous unadjusted quote. Trend/return features and fills
    # use adjusted OHLC so a later bonus or rights event does not masquerade as a crash.
    raw_close: float | None = Field(default=None, gt=0)
    volume: int = Field(ge=0)


class SecurityCategoryObservation(BaseModel):
    category: str = Field(min_length=1, max_length=8)
    known_at: dt.datetime
    source: str = Field(min_length=1, max_length=64)


class StrategyFundamentalObservation(BaseModel):
    fiscal_year: int = Field(ge=1900, le=2200)
    eps: float | None = None
    nav_per_share: float | None = None
    profit_mn: float | None = None
    known_at: dt.datetime
    source: str = Field(min_length=1, max_length=64)


class StrategySecurity(BaseModel):
    code: str
    sector: str = "Unclassified"
    cap_tier: str = "unclassified"
    category_observations: list[SecurityCategoryObservation] = Field(default_factory=list)
    fundamental_observations: list[StrategyFundamentalObservation] = Field(default_factory=list)
    settlement_trade_type: Literal["regular", "spot", "dvp"] = "regular"
    bars: list[StrategyBar]


class StrategyDefinition(BaseModel):
    key: str
    market: Literal["DSE", "US"]
    name: str
    family: str
    horizon: str
    scorer_key: str
    selection_key: str
    sizing_key: str
    methodology_version: str
    minimum_lookback: int
    rebalance_sessions: int
    maximum_positions: int
    required_evidence: tuple[str, ...] = ()
    research_state: Literal["diagnostic", "candidate", "eligible_for_shadow", "data_blocked"]
    automation_eligible: bool = False
    description: str
    economic_thesis: str = ""
    signal_contract: tuple[str, ...] = ()
    execution_contract: tuple[str, ...] = ()
    exit_contract: tuple[str, ...] = ()
    kill_criteria: tuple[str, ...] = ()


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
    contractual_settlement_date: dt.date | None = None
    settlement_rule: str | None = None
    settlement_class: str | None = None
    security_category: str | None = None


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


class BacktestResult(BaseModel):
    engine_version: str
    strategy: StrategyDefinition
    risk_policy: PortfolioRiskPolicy
    start_date: dt.date | None
    end_date: dt.date | None
    initial_capital: float
    final_nav: float
    benchmark_final: float
    trades: list[BacktestTrade]
    equity_curve: list[EquityPoint]
    risk_interventions: list[RiskIntervention]
    metrics: list[PerformanceSlice]
    turnover_pct: float
    fees_paid: float
    validation_status: Literal["diagnostic", "eligible_for_shadow"]
    failed_gates: list[str]
    warnings: list[str]
    latest_target_weights: dict[str, float]


class ShadowPosition(BaseModel):
    shares: int = Field(ge=0)
    average_cost: float = Field(ge=0)


class CashSettlement(BaseModel):
    receivable_key: str = Field(min_length=1, max_length=160)
    release_session: int = Field(ge=0)
    amount: float = Field(gt=0)
    trade_date: dt.date
    contractual_settlement_date: dt.date
    settlement_sessions: int = Field(gt=0)
    settlement_rule: str = Field(min_length=1, max_length=96)
    settlement_class: str = Field(min_length=1, max_length=48)
    trade_type: Literal["regular"]
    security_category: str | None = None


class ShareSettlement(BaseModel):
    lot_key: str = Field(min_length=1, max_length=160)
    code: str = Field(min_length=1, max_length=32)
    quantity: int = Field(gt=0)
    release_session: int = Field(ge=0)
    trade_date: dt.date
    contractual_settlement_date: dt.date
    settlement_sessions: int = Field(gt=0)
    settlement_rule: str = Field(min_length=1, max_length=96)
    settlement_class: str = Field(min_length=1, max_length=48)
    trade_type: Literal["regular"]
    security_category: str | None = None


class ShadowState(BaseModel):
    cash: float = Field(ge=0)
    positions: dict[str, ShadowPosition] = Field(default_factory=dict)
    pending_settlements: list[CashSettlement] = Field(default_factory=list)
    pending_share_settlements: list[ShareSettlement] = Field(default_factory=list)
    peak_nav: float = Field(gt=0)
    benchmark_nav: float = Field(gt=0)
    cumulative_fees: float = Field(default=0, ge=0)
    cumulative_turnover: float = Field(default=0, ge=0)


class ShadowAccountingEvent(BaseModel):
    """One deterministic cash, position, settlement, or valuation transition."""

    event_key: str = Field(min_length=1, max_length=160)
    session_number: int = Field(ge=0)
    effective_date: dt.date
    event_type: Literal[
        "opening_balance",
        "methodology_boundary",
        "settlement_release",
        "share_settlement_release",
        "fill",
        "valuation",
    ]
    code: str | None = None
    payload: dict[str, Any]


class ShadowAdvanceResult(BaseModel):
    date: dt.date
    state: ShadowState
    nav: float
    gross_exposure_pct: float
    drawdown_pct: float
    trades: list[BacktestTrade]
    risk_interventions: list[RiskIntervention]
    next_target_weights: dict[str, float]
    accounting_events: list[ShadowAccountingEvent]


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
        family="reversal",
        horizon="eod_swing",
        scorer_key="dse_liquid_reversal",
        selection_key="top_ranked",
        sizing_key="inverse_volatility",
        methodology_version="dse-liquid-reversal-v1",
        minimum_lookback=126,
        rebalance_sessions=5,
        maximum_positions=8,
        research_state="diagnostic",
        automation_eligible=True,
        description=(
            "Ranks liquid drawdown recoveries using completed price and participation data. "
            "It does not use historically unavailable fundamental snapshots."
        ),
        economic_thesis=(
            "Forced or impatient selling can temporarily push liquid DSE securities below a "
            "reasonable clearing price; a controlled recovery with renewed participation may "
            "capture the exhaustion of that pressure."
        ),
        signal_contract=(
            "At least 126 completed adjusted daily bars.",
            "Material 126-session drawdown, positive five-session recovery, controlled RSI, and participation confirmation.",
        ),
        execution_contract=(
            "Form target only after the completed session close.",
            "Fill no earlier than the next observable regular-session open with DSE costs, ADV capacity, and settlement constraints.",
        ),
        exit_contract=("Scheduled weekly rerank, 12% position stop, or portfolio drawdown brake.",),
        kill_criteria=(
            "Required adjusted-price, category, liquidity, or session evidence becomes unavailable.",
            "Historical or forward promotion gates fail; retain the failed trial record.",
        ),
    ),
    "dse_quality_value_v1": StrategyDefinition(
        key="dse_quality_value_v1",
        market="DSE",
        name="DSE point-in-time quality value",
        family="quality_value",
        horizon="multi_month",
        scorer_key="dse_quality_value",
        selection_key="rank_buffer_2x",
        sizing_key="inverse_volatility",
        methodology_version="dse-quality-value-v1",
        minimum_lookback=126,
        rebalance_sessions=20,
        maximum_positions=8,
        required_evidence=(
            "two point-in-time annual financial observations",
            "positive EPS, NAV, and profit",
            "bonus/right-safe daily prices",
            "completed daily liquidity history",
        ),
        research_state="candidate",
        automation_eligible=False,
        description=(
            "Ranks profitable, improving DSE companies at bounded earnings and book multiples. "
            "A financial row is invisible before its conservative platform knowledge time."
        ),
        economic_thesis=(
            "Slow diffusion of fundamental information and aversion to temporarily unfashionable "
            "companies may leave profitable, improving businesses too cheap relative to earnings "
            "and book value."
        ),
        signal_contract=(
            "Use only annual observations whose known_at is no later than the signal close.",
            "Require two fiscal years, positive and improving EPS, positive profit and NAV, ROE proxy of at least 8%, P/E no greater than 18, and P/B no greater than 2.5.",
            "Reject severe 63-session deterioration and securities below the portfolio liquidity floor.",
        ),
        execution_contract=(
            "Rebalance every 20 completed sessions and fill at the next observable open.",
            "Apply DSE fees, slippage, ADV capacity, category settlement, concentration, and cash constraints.",
        ),
        exit_contract=(
            "Leave when the security falls outside the two-times rank buffer, breaches the position stop, or the portfolio drawdown brake fires.",
        ),
        kill_criteria=(
            "Point-in-time financial revisions or bonus/right adjustments are incomplete for the evaluation window.",
            "The untouched test or forward book fails benchmark-relative, drawdown, execution, or multiple-testing gates.",
        ),
    ),
    "dse_pead_v1": StrategyDefinition(
        key="dse_pead_v1",
        market="DSE",
        name="DSE post-earnings announcement drift",
        family="event_drift",
        horizon="event_swing",
        scorer_key="data_blocked",
        selection_key="top_ranked",
        sizing_key="inverse_volatility",
        methodology_version="dse-pead-v1-contract",
        minimum_lookback=126,
        rebalance_sessions=1,
        maximum_positions=6,
        required_evidence=(
            "deep timestamped DSE earnings announcement history",
            "reported and comparable prior-period EPS",
            "consensus or preregistered expectation proxy",
            "next-observable price and liquidity after publication",
        ),
        research_state="data_blocked",
        automation_eligible=False,
        description=(
            "Preregistered event-drift contract. It cannot emit a signal, target, backtest, or "
            "shadow book until timestamped surprise evidence is deep enough."
        ),
        economic_thesis=(
            "Investors may incorporate a genuine earnings surprise gradually when analysis, "
            "attention, or liquidity is constrained."
        ),
        signal_contract=(
            "Measure a preregistered earnings surprise using evidence known at publication.",
            "Exclude announcements without a reliable publication clock or comparable period.",
        ),
        execution_contract=(
            "Trade no earlier than the first observable eligible session after publication and model post-event gaps explicitly.",
        ),
        exit_contract=(
            "Fixed event horizon, thesis-invalidating subsequent disclosure, stop, or portfolio brake.",
        ),
        kill_criteria=(
            "Announcement timing, surprise measurement, or next-observable execution coverage is incomplete.",
        ),
    ),
    "dse_trend_pullback_intraday_v1": StrategyDefinition(
        key="dse_trend_pullback_intraday_v1",
        market="DSE",
        name="DSE intraday trend pullback",
        family="trend_pullback",
        horizon="intraday_to_multiday",
        scorer_key="data_blocked",
        selection_key="top_ranked",
        sizing_key="inverse_volatility",
        methodology_version="dse-trend-pullback-intraday-v1-contract",
        minimum_lookback=60,
        rebalance_sessions=1,
        maximum_positions=6,
        required_evidence=(
            "complete 15-minute DSE bars",
            "real session VWAP and intraday EMA",
            "intraday completeness and stale-quote flags",
            "effective-dated circuits, category, costs, and next-observable fills",
        ),
        research_state="data_blocked",
        automation_eligible=False,
        description=(
            "The owner's preferred strong-trend, controlled-micro-pullback hypothesis. It is "
            "fully registered but intentionally cannot run on a daily proxy."
        ),
        economic_thesis=(
            "Persistent institutional or informed demand may resume after a low-volume, orderly "
            "micro-pullback when renewed participation reclaims VWAP or an intraday trend reference."
        ),
        signal_contract=(
            "Separate established trend from one-session spikes and circuit-lock behavior.",
            "Require orderly volatility-scaled pullback, contracting participation, structural invalidation, and renewed flow on reclaim.",
        ),
        execution_contract=(
            "Use only the next retained observable 15-minute price after confirmation with spread, slippage, circuit, ADV, and T+2 cash constraints.",
        ),
        exit_contract=(
            "Structural pullback-low invalidation, maximum holding horizon, strategy rerank, or portfolio brake.",
        ),
        kill_criteria=(
            "Any required intraday interval, VWAP input, quote-quality flag, or execution constraint is missing.",
            "Low/micro-cap results are not independently viable after stressed costs and drawdown controls.",
        ),
    ),
    "us_breakout_v1": StrategyDefinition(
        key="us_breakout_v1",
        market="US",
        name="US liquid trend participation",
        family="trend",
        horizon="eod_swing",
        scorer_key="us_liquid_trend",
        selection_key="top_ranked",
        sizing_key="inverse_volatility",
        methodology_version="us-liquid-trend-v1",
        minimum_lookback=200,
        rebalance_sessions=5,
        maximum_positions=10,
        research_state="diagnostic",
        automation_eligible=True,
        description=(
            "Ranks liquid positive trends with participation confirmation and extension control."
        ),
    ),
}


def get_strategy_definition(strategy_key: str) -> StrategyDefinition:
    """Resolve a registered strategy and fail closed for every unknown key."""

    strategy = STRATEGIES.get(strategy_key)
    if strategy is None:
        raise ValueError(f"Unknown registered strategy: {strategy_key}")
    return strategy


def registered_strategies(
    *, market: Literal["DSE", "US"] | None = None
) -> list[StrategyDefinition]:
    """Return the deterministic catalog rather than duplicating strategy keys in callers."""

    return [
        strategy for strategy in STRATEGIES.values() if market is None or strategy.market == market
    ]


def _assert_strategy_runnable(strategy: StrategyDefinition) -> None:
    if strategy.research_state != "data_blocked":
        return
    missing = "; ".join(strategy.required_evidence) or "required evidence is unavailable"
    raise ValueError(
        f"Strategy {strategy.key} is intentionally data-blocked and cannot create a signal, "
        f"target, backtest, or shadow book. Missing evidence: {missing}."
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


class SettlementTerms(BaseModel):
    market: Literal["DSE", "US"]
    security_category: str | None = None
    trade_type: Literal["regular"]
    settlement_sessions: int = Field(gt=0)
    settlement_rule: str = Field(min_length=1, max_length=96)
    settlement_class: str = Field(min_length=1, max_length=48)
    contractual_settlement_date: dt.date


def _category_known_by_open(
    security: StrategySecurity,
    *,
    trade_date: dt.date,
    market: Literal["DSE", "US"],
) -> str | None:
    profile = get_market_profile(market)
    market_open = dt.datetime.combine(trade_date, profile.open_time, tzinfo=profile.tz)
    eligible = []
    for observation in security.category_observations:
        if observation.known_at.tzinfo is None or observation.known_at.utcoffset() is None:
            raise ValueError(f"{security.code} category observation has no knowledge timezone")
        if observation.known_at <= market_open:
            eligible.append(observation)
    if not eligible:
        return None
    latest_known_at = max(item.known_at for item in eligible)
    latest_categories = {
        item.category.strip().upper() for item in eligible if item.known_at == latest_known_at
    }
    latest_categories.discard("")
    if len(latest_categories) > 1:
        raise ValueError(
            f"{security.code} has conflicting DSE categories at {latest_known_at.isoformat()}"
        )
    return next(iter(latest_categories), None)


def settlement_terms_for_security(
    *,
    market: Literal["DSE", "US"],
    security: StrategySecurity,
    trade_date: dt.date,
) -> SettlementTerms:
    """Resolve an effective-dated contractual settlement instruction or fail closed."""

    if security.settlement_trade_type != "regular":
        raise ValueError(
            f"{security.code} uses unsupported {security.settlement_trade_type} settlement"
        )
    if market == "DSE":
        if trade_date < DSE_SETTLEMENT_RULE_EFFECTIVE_FROM:
            raise ValueError(
                f"DSE settlement rule is unverified before {DSE_SETTLEMENT_RULE_EFFECTIVE_FROM}"
            )
        category = _category_known_by_open(security, trade_date=trade_date, market=market)
        if category is None:
            raise ValueError(f"{security.code} has no point-in-time DSE category at execution")
        if category == "Z":
            sessions = 3
            settlement_class = "dse_z_regular"
        elif category in {"A", "B", "G", "N"}:
            sessions = 2
            settlement_class = "dse_abgn_regular"
        else:
            raise ValueError(f"{security.code} has unsupported DSE category {category}")
        rule = "bsec-z-category-directive-2024-07-02"
    else:
        if trade_date < US_T1_RULE_EFFECTIVE_FROM:
            raise ValueError(f"US T+1 rule is unverified before {US_T1_RULE_EFFECTIVE_FROM}")
        category = None
        sessions = 1
        settlement_class = "us_equity_regular"
        rule = "us-equity-t1-2024-05-28"
    return SettlementTerms(
        market=market,
        security_category=category,
        trade_type="regular",
        settlement_sessions=sessions,
        settlement_rule=rule,
        settlement_class=settlement_class,
        contractual_settlement_date=add_market_sessions(trade_date, sessions, market),
    )


@dataclass
class _Position:
    shares: int
    average_cost: float


@dataclass(frozen=True)
class _PlannedOrder:
    code: str
    bar: StrategyBar
    side: Literal["buy", "sell"]
    quantity: int
    intended_quantity: int
    constraint_notes: tuple[str, ...]
    settlement_terms: SettlementTerms


@dataclass(frozen=True)
class _AccountingFill:
    trade: BacktestTrade
    cash_delta: float
    settlement: CashSettlement | None
    share_settlement: ShareSettlement | None
    fee: float
    turnover: float
    position_after: _Position | None


def _release_settlements(
    settlements: list[CashSettlement], *, session_number: int
) -> tuple[float, list[CashSettlement]]:
    released = sum(item.amount for item in settlements if item.release_session <= session_number)
    pending = [item for item in settlements if item.release_session > session_number]
    return released, pending


def _release_share_settlements(
    settlements: list[ShareSettlement], *, session_number: int
) -> tuple[list[ShareSettlement], list[ShareSettlement]]:
    released = [item for item in settlements if item.release_session <= session_number]
    pending = [item for item in settlements if item.release_session > session_number]
    return released, pending


def opening_accounting_events(
    *, initial_capital: float, effective_date: dt.date
) -> list[ShadowAccountingEvent]:
    """Create the event-first opening state for a new paper book."""

    if initial_capital <= 0:
        raise ValueError("initial_capital must be positive")
    return [
        ShadowAccountingEvent(
            event_key="s0:opening_balance",
            session_number=0,
            effective_date=effective_date,
            event_type="opening_balance",
            payload={
                "cash": round(initial_capital, 4),
                "peak_nav": round(initial_capital, 4),
                "benchmark_nav": round(initial_capital, 4),
                "cumulative_fees": 0.0,
                "cumulative_turnover": 0.0,
            },
        )
    ]


def methodology_boundary_accounting_events(
    *,
    state: ShadowState,
    session_number: int,
    effective_date: dt.date,
    source_snapshot_id: str,
) -> list[ShadowAccountingEvent]:
    """Start event-first accounting from an explicitly reconstructed legacy boundary."""

    return [
        ShadowAccountingEvent(
            event_key=f"s{session_number}:methodology_boundary",
            session_number=session_number,
            effective_date=effective_date,
            event_type="methodology_boundary",
            payload={
                "state": state.model_dump(mode="json"),
                "source_snapshot_id": source_snapshot_id,
                "origin": "accepted_pre_accounting_snapshot",
                "event_first_history_before_boundary": False,
            },
        )
    ]


def replay_accounting_events(
    previous: ShadowState | None,
    events: list[ShadowAccountingEvent],
) -> ShadowState:
    """Replay accounting events without using a shadow snapshot as an input projection."""

    if previous is None:
        initialized = False
        cash = 0.0
        positions: dict[str, ShadowPosition] = {}
        pending_settlements: list[CashSettlement] = []
        pending_share_settlements: list[ShareSettlement] = []
        peak_nav = 0.0
        benchmark_nav = 0.0
        cumulative_fees = 0.0
        cumulative_turnover = 0.0
    else:
        initialized = True
        cash = previous.cash
        positions = {
            code: position.model_copy(deep=True) for code, position in previous.positions.items()
        }
        pending_settlements = [
            settlement.model_copy(deep=True) for settlement in previous.pending_settlements
        ]
        pending_share_settlements = [
            settlement.model_copy(deep=True) for settlement in previous.pending_share_settlements
        ]
        peak_nav = previous.peak_nav
        benchmark_nav = previous.benchmark_nav
        cumulative_fees = previous.cumulative_fees
        cumulative_turnover = previous.cumulative_turnover

    for event in events:
        payload = event.payload
        if event.event_type == "opening_balance":
            if initialized:
                raise ValueError("opening_balance can only initialize a new accounting ledger")
            cash = float(payload["cash"])
            peak_nav = float(payload["peak_nav"])
            benchmark_nav = float(payload["benchmark_nav"])
            cumulative_fees = float(payload.get("cumulative_fees", 0.0))
            cumulative_turnover = float(payload.get("cumulative_turnover", 0.0))
            initialized = True
            continue
        if event.event_type == "methodology_boundary":
            if initialized:
                raise ValueError("methodology_boundary can only initialize a new accounting ledger")
            state = ShadowState.model_validate(payload["state"])
            cash = state.cash
            positions = {
                code: position.model_copy(deep=True) for code, position in state.positions.items()
            }
            pending_settlements = [
                settlement.model_copy(deep=True) for settlement in state.pending_settlements
            ]
            pending_share_settlements = [
                settlement.model_copy(deep=True) for settlement in state.pending_share_settlements
            ]
            peak_nav = state.peak_nav
            benchmark_nav = state.benchmark_nav
            cumulative_fees = state.cumulative_fees
            cumulative_turnover = state.cumulative_turnover
            initialized = True
            continue
        if not initialized:
            raise ValueError("accounting ledger must begin with opening_balance")
        if event.event_type == "settlement_release":
            settlement = CashSettlement.model_validate(payload)
            match = next(
                (index for index, item in enumerate(pending_settlements) if item == settlement),
                None,
            )
            if match is None:
                raise ValueError("settlement release does not match an open receivable")
            pending_settlements.pop(match)
            cash += settlement.amount
            continue
        if event.event_type == "share_settlement_release":
            settlement = ShareSettlement.model_validate(payload)
            match = next(
                (
                    index
                    for index, item in enumerate(pending_share_settlements)
                    if item == settlement
                ),
                None,
            )
            if match is None:
                raise ValueError("share settlement release does not match an unsettled lot")
            pending_share_settlements.pop(match)
            continue
        if event.event_type == "fill":
            if not event.code:
                raise ValueError("fill accounting event requires a security code")
            cash += float(payload["cash_delta"])
            settlement_payload = payload.get("settlement")
            if settlement_payload is not None:
                pending_settlements.append(CashSettlement.model_validate(settlement_payload))
            share_settlement_payload = payload.get("share_settlement")
            if share_settlement_payload is not None:
                pending_share_settlements.append(
                    ShareSettlement.model_validate(share_settlement_payload)
                )
            position_after = payload.get("position_after")
            if position_after is None:
                positions.pop(event.code, None)
            else:
                positions[event.code] = ShadowPosition.model_validate(position_after)
            cumulative_fees += float(payload["fee"])
            cumulative_turnover += float(payload["turnover"])
            continue
        if event.event_type == "valuation":
            closing_cash = float(payload["cash"])
            closing_fees = float(payload["cumulative_fees"])
            closing_turnover = float(payload["cumulative_turnover"])
            if not math.isclose(round(cash, 4), closing_cash, abs_tol=0.00005):
                raise ValueError("valuation cash does not reconcile accounting events")
            if not math.isclose(round(cumulative_fees, 4), closing_fees, abs_tol=0.00005):
                raise ValueError("valuation fees do not reconcile accounting events")
            if not math.isclose(round(cumulative_turnover, 4), closing_turnover, abs_tol=0.00005):
                raise ValueError("valuation turnover does not reconcile accounting events")
            cash = closing_cash
            cumulative_fees = closing_fees
            cumulative_turnover = closing_turnover
            peak_nav = float(payload["peak_nav"])
            benchmark_nav = float(payload["benchmark_nav"])

    if not initialized:
        raise ValueError("accounting replay requires an opening balance or previous state")
    if cash < -0.00005:
        raise ValueError("accounting replay produced negative settled cash")
    return ShadowState(
        cash=round(max(cash, 0.0), 4),
        positions=positions,
        pending_settlements=pending_settlements,
        pending_share_settlements=pending_share_settlements,
        peak_nav=round(peak_nav, 4),
        benchmark_nav=round(benchmark_nav, 4),
        cumulative_fees=round(cumulative_fees, 4),
        cumulative_turnover=round(cumulative_turnover, 4),
    )


def _advance_accounting_events(
    *,
    date: dt.date,
    session_number: int,
    released_settlements: list[CashSettlement],
    released_share_settlements: list[ShareSettlement],
    fills: list[_AccountingFill],
    state: ShadowState,
    nav: float,
    gross_exposure_pct: float,
    drawdown_pct: float,
) -> list[ShadowAccountingEvent]:
    events = [
        ShadowAccountingEvent(
            event_key=f"s{session_number}:settlement_release:{index}",
            session_number=session_number,
            effective_date=date,
            event_type="settlement_release",
            payload=settlement.model_dump(mode="json"),
        )
        for index, settlement in enumerate(released_settlements)
    ]
    events.extend(
        ShadowAccountingEvent(
            event_key=f"s{session_number}:share_settlement_release:{index}",
            session_number=session_number,
            effective_date=date,
            event_type="share_settlement_release",
            code=settlement.code,
            payload=settlement.model_dump(mode="json"),
        )
        for index, settlement in enumerate(released_share_settlements)
    )
    for index, fill in enumerate(fills):
        events.append(
            ShadowAccountingEvent(
                event_key=(f"s{session_number}:fill:{index}:{fill.trade.code}:{fill.trade.side}"),
                session_number=session_number,
                effective_date=date,
                event_type="fill",
                code=fill.trade.code,
                payload={
                    "trade": fill.trade.model_dump(mode="json"),
                    "cash_delta": fill.cash_delta,
                    "settlement": (
                        fill.settlement.model_dump(mode="json")
                        if fill.settlement is not None
                        else None
                    ),
                    "share_settlement": (
                        fill.share_settlement.model_dump(mode="json")
                        if fill.share_settlement is not None
                        else None
                    ),
                    "fee": fill.fee,
                    "turnover": fill.turnover,
                    "position_after": (
                        {
                            "shares": fill.position_after.shares,
                            "average_cost": fill.position_after.average_cost,
                        }
                        if fill.position_after is not None
                        else None
                    ),
                },
            )
        )
    events.append(
        ShadowAccountingEvent(
            event_key=f"s{session_number}:valuation",
            session_number=session_number,
            effective_date=date,
            event_type="valuation",
            payload={
                "cash": state.cash,
                "cumulative_fees": state.cumulative_fees,
                "cumulative_turnover": state.cumulative_turnover,
                "peak_nav": state.peak_nav,
                "benchmark_nav": state.benchmark_nav,
                "nav": round(nav, 2),
                "gross_exposure_pct": round(gross_exposure_pct, 3),
                "drawdown_pct": round(drawdown_pct, 3),
            },
        )
    )
    return events


def _execute_target_weights(
    *,
    market: Literal["DSE", "US"],
    date: dt.date,
    session_number: int,
    opening_nav: float,
    settled_cash: float,
    pending_settlements: list[CashSettlement],
    pending_share_settlements: list[ShareSettlement],
    positions: dict[str, _Position],
    target_weights: dict[str, float],
    bars: dict[str, StrategyBar | None],
    average_volumes: dict[str, float | None],
    securities: dict[str, StrategySecurity],
    policy: PortfolioRiskPolicy,
    reason: str,
) -> tuple[
    float,
    list[CashSettlement],
    list[ShareSettlement],
    list[BacktestTrade],
    list[RiskIntervention],
    float,
    float,
    list[_AccountingFill],
]:
    """Execute one target set without allowing symbol order or unsettled proceeds to fund buys."""

    planned: list[_PlannedOrder] = []
    interventions: list[RiskIntervention] = []
    for code in sorted(set(positions) | set(target_weights)):
        current_shares = positions.get(code, _Position(0, 0)).shares
        target_weight = target_weights.get(code, 0.0)
        bar = bars.get(code)
        if bar is None:
            if current_shares > 0 or target_weight > 0:
                interventions.append(
                    RiskIntervention(
                        date=date,
                        code=code,
                        rule="missing_bar",
                        detail="Order rejected because no current observable execution bar was available.",
                    )
                )
            continue
        desired_shares = int(opening_nav * target_weight / bar.open)
        raw_quantity = desired_shares - current_shares
        if raw_quantity == 0:
            continue
        security = securities.get(code)
        if security is None:
            interventions.append(
                RiskIntervention(
                    date=date,
                    code=code,
                    rule="settlement_identity_missing",
                    detail="Order rejected because settlement identity was unavailable.",
                )
            )
            continue
        try:
            settlement_terms = settlement_terms_for_security(
                market=market,
                security=security,
                trade_date=date,
            )
        except ValueError as exc:
            interventions.append(
                RiskIntervention(
                    date=date,
                    code=code,
                    rule="settlement_class_unsupported",
                    detail=f"Order rejected: {exc}.",
                )
            )
            continue
        intended_quantity = abs(raw_quantity)
        average_volume = average_volumes.get(code)
        if average_volume is None or average_volume <= 0:
            interventions.append(
                RiskIntervention(
                    date=date,
                    code=code,
                    rule="liquidity_unknown",
                    detail="Order rejected because a completed ADV baseline was unavailable.",
                )
            )
            continue
        maximum_quantity = int(average_volume * policy.max_adv_participation)
        constrained_quantity = max(-maximum_quantity, min(maximum_quantity, raw_quantity))
        notes: list[str] = []
        if abs(constrained_quantity) < intended_quantity:
            notes.append("adv_capacity")
            interventions.append(
                RiskIntervention(
                    date=date,
                    code=code,
                    rule="adv_capacity",
                    detail=(
                        f"Order constrained from {intended_quantity} to "
                        f"{abs(constrained_quantity)} shares by the mandate ADV participation ceiling."
                    ),
                )
            )
        if constrained_quantity == 0:
            continue
        planned.append(
            _PlannedOrder(
                code=code,
                bar=bar,
                side="buy" if constrained_quantity > 0 else "sell",
                quantity=abs(constrained_quantity),
                intended_quantity=intended_quantity,
                constraint_notes=tuple(notes),
                settlement_terms=settlement_terms,
            )
        )

    trades: list[BacktestTrade] = []
    fees_paid = 0.0
    traded_gross = 0.0
    accounting_fills: list[_AccountingFill] = []
    for order in (item for item in planned if item.side == "sell"):
        current = positions.get(order.code)
        unsettled_quantity = sum(
            item.quantity for item in pending_share_settlements if item.code == order.code
        )
        sellable_quantity = max(0, (current.shares if current else 0) - unsettled_quantity)
        quantity = min(order.quantity, sellable_quantity)
        sell_notes = list(order.constraint_notes)
        if quantity < order.quantity:
            sell_notes.append("share_settlement_lock")
            interventions.append(
                RiskIntervention(
                    date=date,
                    code=order.code,
                    rule="share_settlement_lock",
                    detail=(
                        f"Sell constrained from {order.quantity} to {quantity} shares because "
                        f"{unsettled_quantity} shares had not reached contractual settlement."
                    ),
                )
            )
        if quantity <= 0:
            continue
        fill_price = order.bar.open * (1 - policy.slippage_rate)
        gross = quantity * fill_price
        fee = gross * policy.fee_rate
        proceeds = gross - fee
        remaining = current.shares - quantity
        if remaining:
            current.shares = remaining
        else:
            positions.pop(order.code, None)
        settlement: CashSettlement | None = None
        cash_delta = 0.0
        terms = order.settlement_terms
        settlement = CashSettlement(
            receivable_key=f"s{session_number}:receivable:{order.code}",
            release_session=session_number + terms.settlement_sessions,
            amount=round(proceeds, 4),
            trade_date=date,
            contractual_settlement_date=terms.contractual_settlement_date,
            settlement_sessions=terms.settlement_sessions,
            settlement_rule=terms.settlement_rule,
            settlement_class=terms.settlement_class,
            trade_type=terms.trade_type,
            security_category=terms.security_category,
        )
        pending_settlements.append(settlement)
        fees_paid += fee
        traded_gross += gross
        trade = BacktestTrade(
            date=date,
            code=order.code,
            side="sell",
            quantity=quantity,
            fill_price=round(fill_price, 4),
            gross_value=round(gross, 2),
            fee=round(fee, 2),
            reason=reason,
            intended_quantity=order.intended_quantity,
            constraint_notes=sell_notes,
            contractual_settlement_date=terms.contractual_settlement_date,
            settlement_rule=terms.settlement_rule,
            settlement_class=terms.settlement_class,
            security_category=terms.security_category,
        )
        trades.append(trade)
        position_after = positions.get(order.code)
        accounting_fills.append(
            _AccountingFill(
                trade=trade,
                cash_delta=cash_delta,
                settlement=settlement,
                share_settlement=None,
                fee=fee,
                turnover=gross,
                position_after=(
                    _Position(position_after.shares, position_after.average_cost)
                    if position_after is not None
                    else None
                ),
            )
        )

    buys = [item for item in planned if item.side == "buy"]
    full_cost = sum(
        item.quantity * item.bar.open * (1 + policy.slippage_rate) * (1 + policy.fee_rate)
        for item in buys
    )
    cash_scale = min(1.0, settled_cash / full_cost) if full_cost > 0 else 1.0
    for order in buys:
        quantity = int(order.quantity * cash_scale)
        notes = list(order.constraint_notes)
        if quantity < order.quantity:
            notes.append("cash_capacity")
            rule = "cash_limit" if quantity <= 0 else "cash_capacity"
            interventions.append(
                RiskIntervention(
                    date=date,
                    code=order.code,
                    rule=rule,
                    detail=(
                        "Buy rejected because settled cash was insufficient."
                        if quantity <= 0
                        else (
                            f"Order constrained from {order.quantity} to {quantity} shares "
                            "by settled cash allocated across the complete buy basket."
                        )
                    ),
                )
            )
        if quantity <= 0:
            continue
        fill_price = order.bar.open * (1 + policy.slippage_rate)
        gross = quantity * fill_price
        fee = gross * policy.fee_rate
        total_cost = gross + fee
        if total_cost > settled_cash + 1e-8:
            raise RuntimeError("batch cash allocation exceeded settled cash")
        old = positions.get(order.code, _Position(0, 0.0))
        new_shares = old.shares + quantity
        positions[order.code] = _Position(
            shares=new_shares,
            average_cost=(old.average_cost * old.shares + total_cost) / new_shares,
        )
        settled_cash -= total_cost
        terms = order.settlement_terms
        share_settlement = ShareSettlement(
            lot_key=f"s{session_number}:share_lot:{order.code}",
            code=order.code,
            quantity=quantity,
            release_session=session_number + terms.settlement_sessions,
            trade_date=date,
            contractual_settlement_date=terms.contractual_settlement_date,
            settlement_sessions=terms.settlement_sessions,
            settlement_rule=terms.settlement_rule,
            settlement_class=terms.settlement_class,
            trade_type=terms.trade_type,
            security_category=terms.security_category,
        )
        pending_share_settlements.append(share_settlement)
        fees_paid += fee
        traded_gross += gross
        trade = BacktestTrade(
            date=date,
            code=order.code,
            side="buy",
            quantity=quantity,
            fill_price=round(fill_price, 4),
            gross_value=round(gross, 2),
            fee=round(fee, 2),
            reason=reason,
            intended_quantity=order.intended_quantity,
            constraint_notes=notes,
            contractual_settlement_date=terms.contractual_settlement_date,
            settlement_rule=terms.settlement_rule,
            settlement_class=terms.settlement_class,
            security_category=terms.security_category,
        )
        trades.append(trade)
        position_after = positions[order.code]
        accounting_fills.append(
            _AccountingFill(
                trade=trade,
                cash_delta=-total_cost,
                settlement=None,
                share_settlement=share_settlement,
                fee=fee,
                turnover=gross,
                position_after=_Position(
                    position_after.shares,
                    position_after.average_cost,
                ),
            )
        )
    return (
        settled_cash,
        pending_settlements,
        pending_share_settlements,
        trades,
        interventions,
        fees_paid,
        traded_gross,
        accounting_fills,
    )


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


FeatureScore = tuple[float, float, float]


def _price_inputs(history: list[StrategyBar]) -> tuple[list[float], float, float, float] | None:
    """Return common observable price inputs shared by registered scorers."""

    closes = [bar.close for bar in history]
    volumes = [bar.volume for bar in history]
    volatility = _annualized_volatility(closes)
    if volatility is None or volatility <= 0:
        return None
    average_volume = statistics.fmean(volumes[-20:])
    long_volume = statistics.fmean(volumes[-60:]) if len(volumes) >= 60 else average_volume
    relative_volume = average_volume / long_volume if long_volume > 0 else 0.0
    return closes, volatility, average_volume, relative_volume


def _score_dse_liquid_reversal(
    strategy: StrategyDefinition,
    history: list[StrategyBar],
    security: StrategySecurity,
) -> FeatureScore | None:
    if len(history) < strategy.minimum_lookback:
        return None
    inputs = _price_inputs(history)
    if inputs is None:
        return None
    closes, volatility, average_volume, relative_volume = inputs
    peak = max(closes[-126:])
    drawdown = closes[-1] / peak - 1.0
    return_5 = closes[-1] / closes[-6] - 1.0
    rsi = _rsi(closes) or 50.0
    if drawdown > -0.12 or return_5 <= 0 or rsi > 58 or relative_volume < 0.90:
        return None
    score = abs(drawdown) * 100 + return_5 * 120 + relative_volume * 8 - max(0, rsi - 50)
    return score, volatility, average_volume


def _score_us_liquid_trend(
    strategy: StrategyDefinition,
    history: list[StrategyBar],
    security: StrategySecurity,
) -> FeatureScore | None:
    if len(history) < strategy.minimum_lookback:
        return None
    inputs = _price_inputs(history)
    if inputs is None:
        return None
    closes, volatility, average_volume, relative_volume = inputs
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


def _fundamentals_known_by_signal_close(
    strategy: StrategyDefinition,
    security: StrategySecurity,
    signal_date: dt.date,
) -> list[StrategyFundamentalObservation]:
    profile = get_market_profile(strategy.market)
    signal_close = dt.datetime.combine(signal_date, profile.close_time, tzinfo=profile.tz)
    latest_by_year: dict[int, StrategyFundamentalObservation] = {}
    for observation in security.fundamental_observations:
        known_at = observation.known_at
        if known_at.tzinfo is None:
            known_at = known_at.replace(tzinfo=dt.UTC)
        if known_at > signal_close:
            continue
        previous = latest_by_year.get(observation.fiscal_year)
        if previous is None:
            latest_by_year[observation.fiscal_year] = observation
            continue
        previous_known_at = previous.known_at
        if previous_known_at.tzinfo is None:
            previous_known_at = previous_known_at.replace(tzinfo=dt.UTC)
        if known_at >= previous_known_at:
            latest_by_year[observation.fiscal_year] = observation
    return sorted(latest_by_year.values(), key=lambda item: item.fiscal_year, reverse=True)


def _score_dse_quality_value(
    strategy: StrategyDefinition,
    history: list[StrategyBar],
    security: StrategySecurity,
) -> FeatureScore | None:
    if len(history) < strategy.minimum_lookback:
        return None
    inputs = _price_inputs(history)
    if inputs is None:
        return None
    closes, volatility, average_volume, relative_volume = inputs
    financials = _fundamentals_known_by_signal_close(strategy, security, history[-1].date)
    if len(financials) < 2:
        return None
    current, prior = financials[:2]
    if (
        current.eps is None
        or prior.eps is None
        or current.nav_per_share is None
        or current.profit_mn is None
        or current.eps <= 0
        or prior.eps <= 0
        or current.nav_per_share <= 0
        or current.profit_mn <= 0
    ):
        return None
    earnings_growth = current.eps / prior.eps - 1.0
    roe_proxy = current.eps / current.nav_per_share
    raw_close = history[-1].raw_close or history[-1].close
    pe_ratio = raw_close / current.eps
    pb_ratio = raw_close / current.nav_per_share
    momentum_63 = closes[-1] / closes[-64] - 1.0
    if (
        earnings_growth <= 0
        or roe_proxy < 0.08
        or pe_ratio > 18
        or pb_ratio > 2.5
        or momentum_63 <= -0.15
        or relative_volume < 0.75
    ):
        return None
    score = (
        min(earnings_growth, 1.0) * 25
        + min(roe_proxy, 0.35) * 100
        + (1 / pe_ratio) * 120
        + (1 / pb_ratio) * 12
        + max(momentum_63, -0.15) * 10
        + relative_volume * 5
        - volatility * 8
    )
    return score, volatility, average_volume


_SCORERS = {
    "dse_liquid_reversal": _score_dse_liquid_reversal,
    "dse_quality_value": _score_dse_quality_value,
    "us_liquid_trend": _score_us_liquid_trend,
}


def _feature_score(
    strategy: StrategyDefinition,
    history: list[StrategyBar],
    security: StrategySecurity,
) -> FeatureScore | None:
    scorer = _SCORERS.get(strategy.scorer_key)
    if scorer is None:
        raise RuntimeError(
            f"Strategy {strategy.key} owns unregistered scorer {strategy.scorer_key}; refusing to run"
        )
    return scorer(strategy, history, security)


def _target_weights(
    strategy: StrategyDefinition,
    policy: PortfolioRiskPolicy,
    histories: dict[str, list[StrategyBar]],
    securities: dict[str, StrategySecurity],
    *,
    current_weights: dict[str, float] | None = None,
) -> dict[str, float]:
    ranked: list[tuple[float, str, float]] = []
    for code, history in histories.items():
        feature = _feature_score(strategy, history, securities[code])
        if feature is None:
            continue
        score, volatility, average_volume = feature
        average_value_mn = average_volume * history[-1].close / 1_000_000
        if average_value_mn < policy.minimum_average_daily_value_mn:
            continue
        ranked.append((score, code, volatility))
    ranked.sort(reverse=True)

    if strategy.selection_key == "top_ranked":
        selected = ranked[: strategy.maximum_positions]
    elif strategy.selection_key == "rank_buffer_2x":
        rank_by_code = {code: rank for rank, (_, code, _) in enumerate(ranked)}
        incumbents = [
            item
            for item in ranked
            if item[1] in (current_weights or {})
            and rank_by_code[item[1]] < strategy.maximum_positions * 2
        ]
        incumbent_codes = {item[1] for item in incumbents}
        selected = incumbents[: strategy.maximum_positions]
        for item in ranked:
            if len(selected) >= strategy.maximum_positions:
                break
            if item[1] not in incumbent_codes:
                selected.append(item)
    else:
        raise RuntimeError(
            f"Strategy {strategy.key} owns unregistered selection policy "
            f"{strategy.selection_key}; refusing to run"
        )

    weights: dict[str, float] = {}
    sector_weights: dict[str, float] = {}
    remaining = policy.max_gross_exposure
    for _, code, volatility in selected:
        if remaining <= 0:
            break
        sector = securities[code].sector
        if strategy.sizing_key == "inverse_volatility":
            desired_weight = (
                policy.max_gross_exposure
                / strategy.maximum_positions
                * policy.target_annualized_volatility
                / max(volatility, 0.05)
            )
        elif strategy.sizing_key == "equal_weight_full_gross":
            desired_weight = policy.max_gross_exposure / strategy.maximum_positions
        else:
            raise RuntimeError(
                f"Strategy {strategy.key} owns unregistered sizing policy "
                f"{strategy.sizing_key}; refusing to run"
            )
        desired = min(
            policy.max_position_weight,
            desired_weight,
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
    strategy_key: str,
    securities: list[StrategySecurity],
    initial_capital: float = 100_000.0,
    inactive_security_history_complete: bool = False,
    point_in_time_inputs_complete: bool = False,
    risk_policy: PortfolioRiskPolicy | None = None,
) -> BacktestResult:
    """Run the registered strategy with next-session execution and deterministic risk gates."""

    if initial_capital <= 0:
        raise ValueError("initial_capital must be positive")
    strategy = get_strategy_definition(strategy_key)
    if strategy.market != market:
        raise ValueError(f"Strategy {strategy_key} is not registered for {market}")
    _assert_strategy_runnable(strategy)
    policy = risk_policy or RISK_POLICIES[market]
    if policy.market != market:
        raise ValueError("risk policy belongs to another market")
    security_by_code = {security.code: security for security in securities}
    bars_by_code = {
        security.code: {bar.date: bar for bar in sorted(security.bars, key=lambda item: item.date)}
        for security in securities
    }
    dates = sorted({date for bars in bars_by_code.values() for date in bars})
    histories: dict[str, list[StrategyBar]] = {code: [] for code in bars_by_code}
    positions: dict[str, _Position] = {}
    cash = initial_capital
    pending_settlements: list[CashSettlement] = []
    pending_share_settlements: list[ShareSettlement] = []
    pending_weights: dict[str, float] | None = None
    pending_reason = "scheduled rebalance"
    trades: list[BacktestTrade] = []
    curve: list[EquityPoint] = []
    interventions: list[RiskIntervention] = []
    fees_paid = 0.0
    traded_gross = 0.0
    peak_nav = initial_capital
    benchmark = initial_capital
    latest_target_weights: dict[str, float] = {}

    for session_index, date in enumerate(dates):
        current = {code: bars.get(date) for code, bars in bars_by_code.items()}
        released_cash, pending_settlements = _release_settlements(
            pending_settlements,
            session_number=session_index,
        )
        cash += released_cash
        _, pending_share_settlements = _release_share_settlements(
            pending_share_settlements,
            session_number=session_index,
        )

        if pending_weights is not None:
            opening_nav = cash + sum(item.amount for item in pending_settlements)
            for code, position in positions.items():
                bar = current.get(code)
                if bar is not None:
                    opening_nav += position.shares * bar.open
                elif histories[code]:
                    opening_nav += position.shares * histories[code][-1].close
            average_volumes = {
                code: (statistics.fmean(item.volume for item in history[-20:]) if history else None)
                for code, history in histories.items()
            }
            (
                cash,
                pending_settlements,
                pending_share_settlements,
                session_trades,
                session_interventions,
                session_fees,
                session_gross,
                _,
            ) = _execute_target_weights(
                market=market,
                date=date,
                session_number=session_index,
                opening_nav=opening_nav,
                settled_cash=cash,
                pending_settlements=pending_settlements,
                pending_share_settlements=pending_share_settlements,
                positions=positions,
                target_weights=pending_weights,
                bars=current,
                average_volumes=average_volumes,
                securities=security_by_code,
                policy=policy,
                reason=pending_reason,
            )
            trades.extend(session_trades)
            interventions.extend(session_interventions)
            fees_paid += session_fees
            traded_gross += session_gross
            pending_weights = None

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
        if previous_closes and len(previous_closes) == len(current_closes):
            benchmark *= 1 + statistics.fmean(
                current_close / previous_close - 1.0
                for previous_close, current_close in zip(
                    previous_closes, current_closes, strict=True
                )
                if previous_close > 0
            )

        nav = cash + sum(item.amount for item in pending_settlements)
        position_value = 0.0
        for code, position in positions.items():
            bar = current.get(code)
            if bar is not None:
                marked_value = position.shares * bar.close
                nav += marked_value
                position_value += marked_value
            elif histories[code]:
                marked_value = position.shares * histories[code][-1].close
                nav += marked_value
                position_value += marked_value
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
        gross_exposure = position_value / nav if nav > 0 else 0.0
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
                        detail=f"Next-open exit scheduled after a {policy.position_stop_loss:.0%} loss threshold.",
                    )
                )
            pending_weights = target
            pending_reason = "position risk stop"
        if drawdown >= policy.portfolio_drawdown_brake:
            pending_weights = {}
            pending_reason = "portfolio drawdown brake"
            latest_target_weights = {}
            interventions.append(
                RiskIntervention(
                    date=date,
                    rule="portfolio_drawdown_brake",
                    detail=f"Gross exposure scheduled to zero after drawdown reached {drawdown:.1%}.",
                )
            )
        elif (
            session_index >= strategy.minimum_lookback
            and session_index % strategy.rebalance_sessions == 0
            and pending_weights is None
        ):
            latest_target_weights = _target_weights(
                strategy,
                policy,
                histories,
                security_by_code,
                current_weights=latest_target_weights,
            )
            pending_weights = latest_target_weights
            pending_reason = "scheduled point-in-time rebalance"

    nav_values = [point.nav for point in curve]
    split_1 = max(2, round(len(nav_values) * 0.6))
    split_2 = max(split_1 + 1, round(len(nav_values) * 0.8))
    metrics = [
        _performance_slice("full", nav_values),
        _performance_slice("train", nav_values[:split_1]),
        _performance_slice("validation", nav_values[split_1 - 1 : split_2]),
        _performance_slice("test", nav_values[split_2 - 1 :]),
    ]
    failed_gates: list[str] = []
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
        trades=trades,
        equity_curve=curve,
        risk_interventions=interventions,
        metrics=metrics,
        turnover_pct=round(traded_gross / initial_capital * 100, 3),
        fees_paid=round(fees_paid, 2),
        validation_status=validation_status,
        failed_gates=failed_gates,
        warnings=[
            "Results are research diagnostics, not expected returns or a recommendation.",
            "The benchmark is an equal-weight observable-universe series and shares current-universe bias.",
            "Fundamental and universe filters are validation-safe only when point-in-time input coverage is complete.",
            "Corporate-action safety depends on adjustment coverage; fills use the next-session open supplied by the point-in-time price adapter.",
            "A missing held-security bar carries the last observable close and records a stale-mark intervention.",
        ],
        latest_target_weights=latest_target_weights,
    )


def advance_shadow_portfolio(
    *,
    market: Literal["DSE", "US"],
    strategy_key: str,
    securities: list[StrategySecurity],
    previous: ShadowState,
    target_weights: dict[str, float],
    session_number: int,
    as_of_date: dt.date | None = None,
    risk_policy: PortfolioRiskPolicy | None = None,
) -> ShadowAdvanceResult:
    """Advance one real-time shadow book by one completed market session.

    ``target_weights`` must have been formed after the previous close. It executes at the current
    session's adjusted open and the function forms the next target only after observing this close.
    """

    strategy = get_strategy_definition(strategy_key)
    if strategy.market != market:
        raise ValueError(f"Strategy {strategy_key} is not registered for {market}")
    _assert_strategy_runnable(strategy)
    if not securities:
        raise ValueError("shadow portfolio requires current security history")
    latest_dates = {security.bars[-1].date for security in securities if security.bars}
    if not latest_dates:
        raise ValueError("shadow portfolio requires at least one completed security bar")
    date = as_of_date or (next(iter(latest_dates)) if len(latest_dates) == 1 else None)
    if date is None:
        raise ValueError("as_of_date is required when security histories end on different dates")
    if any(latest > date for latest in latest_dates):
        raise ValueError("shadow portfolio security history extends beyond its as-of session")
    if not any(security.bars and security.bars[-1].date == date for security in securities):
        raise ValueError("shadow portfolio has no observable bar on its as-of session")
    policy = risk_policy or RISK_POLICIES[market]
    if policy.market != market:
        raise ValueError("risk policy belongs to another market")
    by_code = {security.code: security for security in securities}
    missing_held_codes = sorted(set(previous.positions) - set(by_code))
    if missing_held_codes:
        raise ValueError(
            "shadow portfolio cannot advance without current history for held positions: "
            + ", ".join(missing_held_codes)
        )
    positions = {
        code: _Position(position.shares, position.average_cost)
        for code, position in previous.positions.items()
    }
    released_settlements = [
        settlement
        for settlement in previous.pending_settlements
        if settlement.release_session <= session_number
    ]
    released_cash, pending_settlements = _release_settlements(
        previous.pending_settlements,
        session_number=session_number,
    )
    released_share_settlements, pending_share_settlements = _release_share_settlements(
        previous.pending_share_settlements,
        session_number=session_number,
    )
    cash = previous.cash + released_cash

    current_bars = {
        code: security.bars[-1] if security.bars and security.bars[-1].date == date else None
        for code, security in by_code.items()
    }
    opening_nav = cash + sum(item.amount for item in pending_settlements)
    for code, position in positions.items():
        security = by_code[code]
        current_bar = current_bars[code]
        opening_nav += position.shares * (
            current_bar.open if current_bar is not None else security.bars[-1].close
        )
    average_volumes = {
        code: (
            statistics.fmean(item.volume for item in security.bars[-21:-1])
            if len(security.bars) >= 21
            else None
        )
        for code, security in by_code.items()
    }
    (
        cash,
        pending_settlements,
        pending_share_settlements,
        trades,
        interventions,
        session_fees,
        session_turnover,
        accounting_fills,
    ) = _execute_target_weights(
        market=market,
        date=date,
        session_number=session_number,
        opening_nav=opening_nav,
        settled_cash=cash,
        pending_settlements=pending_settlements,
        pending_share_settlements=pending_share_settlements,
        positions=positions,
        target_weights=target_weights,
        bars=current_bars,
        average_volumes=average_volumes,
        securities=by_code,
        policy=policy,
        reason="prior-close shadow target",
    )

    position_value = 0.0
    for code, position in positions.items():
        security = by_code[code]
        current_bar = current_bars[code]
        position_value += position.shares * (
            current_bar.close if current_bar is not None else security.bars[-1].close
        )
        if current_bar is None:
            interventions.append(
                RiskIntervention(
                    date=date,
                    code=code,
                    rule="stale_mark",
                    detail=(
                        "No completed bar was available; NAV carried the last observable close, "
                        "settlements still matured, and no execution was permitted."
                    ),
                )
            )
    nav = cash + sum(item.amount for item in pending_settlements) + position_value
    peak_nav = max(previous.peak_nav, nav)
    drawdown = 1 - nav / peak_nav if peak_nav > 0 else 0.0
    gross_exposure = position_value / nav if nav > 0 else 0.0
    benchmark_returns = [
        security.bars[-1].close / security.bars[-2].close - 1
        for security in securities
        if len(security.bars) >= 2
        and security.bars[-1].date == date
        and security.bars[-2].close > 0
    ]
    benchmark_nav = previous.benchmark_nav * (
        1 + statistics.fmean(benchmark_returns) if benchmark_returns else 1
    )
    histories = {
        security.code: security.bars
        for security in securities
        if security.bars and security.bars[-1].date == date
    }
    current_securities = {code: by_code[code] for code in histories}
    next_targets = (
        _target_weights(
            strategy,
            policy,
            histories,
            current_securities,
            current_weights=target_weights,
        )
        if session_number % strategy.rebalance_sessions == 0
        else target_weights.copy()
    )
    for code, position in positions.items():
        security = by_code.get(code)
        if (
            security is not None
            and security.bars[-1].date == date
            and security.bars[-1].close / position.average_cost - 1 <= -policy.position_stop_loss
        ):
            next_targets.pop(code, None)
            interventions.append(
                RiskIntervention(
                    date=date,
                    code=code,
                    rule="position_stop",
                    detail="Next-open exit required by the deterministic position stop.",
                )
            )
    if drawdown >= policy.portfolio_drawdown_brake:
        next_targets = {}
        interventions.append(
            RiskIntervention(
                date=date,
                rule="portfolio_drawdown_brake",
                detail="Next-open gross exposure set to zero by the portfolio drawdown brake.",
            )
        )
    state = ShadowState(
        cash=round(cash, 4),
        positions={
            code: ShadowPosition(shares=position.shares, average_cost=position.average_cost)
            for code, position in positions.items()
        },
        pending_settlements=pending_settlements,
        pending_share_settlements=pending_share_settlements,
        peak_nav=round(peak_nav, 4),
        benchmark_nav=round(benchmark_nav, 4),
        cumulative_fees=round(previous.cumulative_fees + session_fees, 4),
        cumulative_turnover=round(previous.cumulative_turnover + session_turnover, 4),
    )
    accounting_events = _advance_accounting_events(
        date=date,
        session_number=session_number,
        released_settlements=released_settlements,
        released_share_settlements=released_share_settlements,
        fills=accounting_fills,
        state=state,
        nav=nav,
        gross_exposure_pct=gross_exposure * 100,
        drawdown_pct=drawdown * 100,
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
        accounting_events=accounting_events,
    )
