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

ENGINE_VERSION = "atlas-portfolio-engine-v2"


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
    settlement_sessions: int = Field(ge=0)


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


class ShadowState(BaseModel):
    cash: float = Field(ge=0)
    positions: dict[str, ShadowPosition] = Field(default_factory=dict)
    pending_settlements: list[CashSettlement] = Field(default_factory=list)
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
        "opening_balance", "methodology_boundary", "settlement_release", "fill", "valuation"
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
        settlement_sessions=2,
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
        settlement_sessions=1,
    ),
}


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


@dataclass(frozen=True)
class _AccountingFill:
    trade: BacktestTrade
    cash_delta: float
    settlement: CashSettlement | None
    fee: float
    turnover: float
    position_after: _Position | None


def _release_settlements(
    settlements: list[CashSettlement], *, session_number: int
) -> tuple[float, list[CashSettlement]]:
    released = sum(item.amount for item in settlements if item.release_session <= session_number)
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
            peak_nav = state.peak_nav
            benchmark_nav = state.benchmark_nav
            cumulative_fees = state.cumulative_fees
            cumulative_turnover = state.cumulative_turnover
            initialized = True
            continue
        if not initialized:
            raise ValueError("accounting ledger must begin with opening_balance")
        if event.event_type == "settlement_release":
            receivable_key = str(payload["receivable_key"])
            release_session = int(payload["release_session"])
            amount = float(payload["amount"])
            match = next(
                (
                    index
                    for index, item in enumerate(pending_settlements)
                    if item.receivable_key == receivable_key
                    and item.release_session == release_session
                    and math.isclose(item.amount, amount, abs_tol=0.00005)
                ),
                None,
            )
            if match is None:
                raise ValueError("settlement release does not match an open receivable")
            pending_settlements.pop(match)
            cash += amount
            continue
        if event.event_type == "fill":
            if not event.code:
                raise ValueError("fill accounting event requires a security code")
            cash += float(payload["cash_delta"])
            settlement_payload = payload.get("settlement")
            if settlement_payload is not None:
                pending_settlements.append(CashSettlement.model_validate(settlement_payload))
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
    date: dt.date,
    session_number: int,
    opening_nav: float,
    settled_cash: float,
    pending_settlements: list[CashSettlement],
    positions: dict[str, _Position],
    target_weights: dict[str, float],
    bars: dict[str, StrategyBar | None],
    average_volumes: dict[str, float | None],
    policy: PortfolioRiskPolicy,
    reason: str,
) -> tuple[
    float,
    list[CashSettlement],
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
            )
        )

    trades: list[BacktestTrade] = []
    fees_paid = 0.0
    traded_gross = 0.0
    accounting_fills: list[_AccountingFill] = []
    for order in (item for item in planned if item.side == "sell"):
        current = positions.get(order.code)
        quantity = min(order.quantity, current.shares if current else 0)
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
        if policy.settlement_sessions == 0:
            settled_cash += proceeds
            cash_delta = proceeds
        else:
            settlement = CashSettlement(
                receivable_key=f"s{session_number}:receivable:{order.code}",
                release_session=session_number + policy.settlement_sessions,
                amount=round(proceeds, 4),
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
            constraint_notes=list(order.constraint_notes),
        )
        trades.append(trade)
        position_after = positions.get(order.code)
        accounting_fills.append(
            _AccountingFill(
                trade=trade,
                cash_delta=cash_delta,
                settlement=settlement,
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
        )
        trades.append(trade)
        position_after = positions[order.code]
        accounting_fills.append(
            _AccountingFill(
                trade=trade,
                cash_delta=-total_cost,
                settlement=None,
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


_SCORERS = {
    "dse_liquid_reversal": _score_dse_liquid_reversal,
    "us_liquid_trend": _score_us_liquid_trend,
}


def _feature_score(
    strategy: StrategyDefinition,
    history: list[StrategyBar],
) -> FeatureScore | None:
    scorer = _SCORERS.get(strategy.scorer_key)
    if scorer is None:
        raise RuntimeError(
            f"Strategy {strategy.key} owns unregistered scorer {strategy.scorer_key}; refusing to run"
        )
    return scorer(strategy, history)


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
        feature = _feature_score(strategy, history)
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
                session_trades,
                session_interventions,
                session_fees,
                session_gross,
                _,
            ) = _execute_target_weights(
                date=date,
                session_number=session_index,
                opening_nav=opening_nav,
                settled_cash=cash,
                pending_settlements=pending_settlements,
                positions=positions,
                target_weights=pending_weights,
                bars=current,
                average_volumes=average_volumes,
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
    risk_policy: PortfolioRiskPolicy | None = None,
) -> ShadowAdvanceResult:
    """Advance one real-time shadow book by one completed market session.

    ``target_weights`` must have been formed after the previous close. It executes at the current
    session's adjusted open and the function forms the next target only after observing this close.
    """

    strategy = get_strategy_definition(strategy_key)
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
    cash = previous.cash + released_cash

    opening_nav = (
        cash
        + sum(item.amount for item in pending_settlements)
        + sum(
            position.shares * by_code[code].bars[-1].open
            for code, position in positions.items()
            if code in by_code
        )
    )
    current_bars = {code: security.bars[-1] for code, security in by_code.items() if security.bars}
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
        trades,
        interventions,
        session_fees,
        session_turnover,
        accounting_fills,
    ) = _execute_target_weights(
        date=date,
        session_number=session_number,
        opening_nav=opening_nav,
        settled_cash=cash,
        pending_settlements=pending_settlements,
        positions=positions,
        target_weights=target_weights,
        bars=current_bars,
        average_volumes=average_volumes,
        policy=policy,
        reason="prior-close shadow target",
    )

    position_value = sum(
        position.shares * by_code[code].bars[-1].close
        for code, position in positions.items()
        if code in by_code
    )
    nav = cash + sum(item.amount for item in pending_settlements) + position_value
    peak_nav = max(previous.peak_nav, nav)
    drawdown = 1 - nav / peak_nav if peak_nav > 0 else 0.0
    gross_exposure = position_value / nav if nav > 0 else 0.0
    benchmark_returns = [
        security.bars[-1].close / security.bars[-2].close - 1
        for security in securities
        if len(security.bars) >= 2 and security.bars[-2].close > 0
    ]
    benchmark_nav = previous.benchmark_nav * (
        1 + statistics.fmean(benchmark_returns) if benchmark_returns else 1
    )
    histories = {security.code: security.bars for security in securities}
    next_targets = (
        _target_weights(
            strategy,
            policy,
            histories,
            by_code,
            current_weights=target_weights,
        )
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
        peak_nav=round(peak_nav, 4),
        benchmark_nav=round(benchmark_nav, 4),
        cumulative_fees=round(previous.cumulative_fees + session_fees, 4),
        cumulative_turnover=round(previous.cumulative_turnover + session_turnover, 4),
    )
    accounting_events = _advance_accounting_events(
        date=date,
        session_number=session_number,
        released_settlements=released_settlements,
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
