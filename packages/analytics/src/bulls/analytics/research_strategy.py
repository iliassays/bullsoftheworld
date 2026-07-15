"""Point-in-time backtest and shadow-book engine for Bulls Atlas.

Signals use completed bars through T and trades fill no earlier than the next available session open.
The engine is deliberately long-only until market-specific borrowing and locate data exist.
"""

from __future__ import annotations

import datetime as dt
import math
import statistics
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field

ENGINE_VERSION = "atlas-portfolio-engine-v1"


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
    key: Literal["dse_reversal_v1", "us_breakout_v1"]
    market: Literal["DSE", "US"]
    name: str
    methodology_version: str
    minimum_lookback: int
    rebalance_sessions: int
    maximum_positions: int
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


class BacktestTrade(BaseModel):
    date: dt.date
    code: str
    side: Literal["buy", "sell"]
    quantity: int
    fill_price: float
    gross_value: float
    fee: float
    reason: str


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


class ShadowState(BaseModel):
    cash: float = Field(ge=0)
    positions: dict[str, ShadowPosition] = Field(default_factory=dict)
    peak_nav: float = Field(gt=0)
    benchmark_nav: float = Field(gt=0)
    cumulative_fees: float = Field(default=0, ge=0)
    cumulative_turnover: float = Field(default=0, ge=0)


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
        methodology_version="dse-liquid-reversal-v1",
        minimum_lookback=126,
        rebalance_sessions=5,
        maximum_positions=8,
        description=(
            "Ranks liquid drawdown recoveries using completed price and participation data. "
            "It does not use historically unavailable fundamental snapshots."
        ),
    ),
    "us_breakout_v1": StrategyDefinition(
        key="us_breakout_v1",
        market="US",
        name="US liquid trend participation",
        methodology_version="us-liquid-trend-v1",
        minimum_lookback=200,
        rebalance_sessions=5,
        maximum_positions=10,
        description=(
            "Ranks liquid positive trends with participation confirmation and extension control."
        ),
    ),
}


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
    strategy_key: Literal["dse_reversal_v1", "us_breakout_v1"],
    securities: list[StrategySecurity],
    initial_capital: float = 100_000.0,
    inactive_security_history_complete: bool = False,
) -> BacktestResult:
    """Run the registered strategy with next-session execution and deterministic risk gates."""

    if initial_capital <= 0:
        raise ValueError("initial_capital must be positive")
    strategy = STRATEGIES[strategy_key]
    if strategy.market != market:
        raise ValueError(f"Strategy {strategy_key} is not registered for {market}")
    policy = RISK_POLICIES[market]
    security_by_code = {security.code: security for security in securities}
    bars_by_code = {
        security.code: {bar.date: bar for bar in sorted(security.bars, key=lambda item: item.date)}
        for security in securities
    }
    dates = sorted({date for bars in bars_by_code.values() for date in bars})
    histories: dict[str, list[StrategyBar]] = {code: [] for code in bars_by_code}
    positions: dict[str, _Position] = {}
    cash = initial_capital
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

        if pending_weights is not None:
            opening_nav = cash
            for code, position in positions.items():
                bar = current.get(code)
                if bar is not None:
                    opening_nav += position.shares * bar.open
                elif histories[code]:
                    opening_nav += position.shares * histories[code][-1].close
            all_codes = set(positions) | set(pending_weights)
            for code in sorted(all_codes):
                bar = current.get(code)
                if bar is None:
                    continue
                current_shares = positions.get(code, _Position(0, 0.0)).shares
                desired_value = opening_nav * pending_weights.get(code, 0.0)
                desired_shares = int(desired_value / bar.open)
                quantity = desired_shares - current_shares
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
                quantity = max(-max_quantity, min(max_quantity, quantity))
                if quantity == 0:
                    continue
                side: Literal["buy", "sell"] = "buy" if quantity > 0 else "sell"
                fill_price = bar.open * (
                    1 + policy.slippage_rate if side == "buy" else 1 - policy.slippage_rate
                )
                absolute_quantity = abs(quantity)
                gross = absolute_quantity * fill_price
                fee = gross * policy.fee_rate
                if side == "buy":
                    affordable = int(cash / (fill_price * (1 + policy.fee_rate)))
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
                    )
                )
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
            latest_target_weights = _target_weights(strategy, policy, histories, security_by_code)
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
            "Corporate-action safety depends on adjustment coverage; fills use the next-session open supplied by the point-in-time price adapter.",
            "A missing held-security bar carries the last observable close and records a stale-mark intervention.",
        ],
        latest_target_weights=latest_target_weights,
    )


def advance_shadow_portfolio(
    *,
    market: Literal["DSE", "US"],
    strategy_key: Literal["dse_reversal_v1", "us_breakout_v1"],
    securities: list[StrategySecurity],
    previous: ShadowState,
    target_weights: dict[str, float],
    session_number: int,
) -> ShadowAdvanceResult:
    """Advance one real-time shadow book by one completed market session.

    ``target_weights`` must have been formed after the previous close. It executes at the current
    session's adjusted open and the function forms the next target only after observing this close.
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
    policy = RISK_POLICIES[market]
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

    opening_nav = cash + sum(
        position.shares * by_code[code].bars[-1].open
        for code, position in positions.items()
        if code in by_code
    )
    for code in sorted(set(positions) | set(target_weights)):
        security = by_code.get(code)
        if security is None or len(security.bars) < 21:
            continue
        bar = security.bars[-1]
        current_shares = positions.get(code, _Position(0, 0)).shares
        desired_shares = int(opening_nav * target_weights.get(code, 0.0) / bar.open)
        quantity = desired_shares - current_shares
        average_volume = statistics.fmean(item.volume for item in security.bars[-21:-1])
        maximum_quantity = int(average_volume * policy.max_adv_participation)
        quantity = max(-maximum_quantity, min(maximum_quantity, quantity))
        if quantity == 0:
            continue
        side: Literal["buy", "sell"] = "buy" if quantity > 0 else "sell"
        fill_price = bar.open * (
            1 + policy.slippage_rate if side == "buy" else 1 - policy.slippage_rate
        )
        absolute_quantity = abs(quantity)
        if side == "buy":
            affordable = int(cash / (fill_price * (1 + policy.fee_rate)))
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
                reason="prior-close shadow target",
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
        peak_nav=round(peak_nav, 4),
        benchmark_nav=round(benchmark_nav, 4),
        cumulative_fees=round(previous.cumulative_fees + session_fees, 4),
        cumulative_turnover=round(previous.cumulative_turnover + session_turnover, 4),
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
