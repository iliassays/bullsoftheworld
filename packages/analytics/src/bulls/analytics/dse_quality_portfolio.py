"""Quarterly target-portfolio research for the DSE point-in-time quality universe.

This is deliberately not an event-trade backtester.  A quality/value holding is reviewed on a
fixed rebalance schedule and leaves the book when it loses universe membership or its relative
rank, not because an arbitrary swing-trade target happened to print.
"""

from __future__ import annotations

import datetime as dt
import statistics
from dataclasses import dataclass
from itertools import pairwise

from bulls.analytics.dse_edges import EdgeBar, ExecutionPolicy, limit_locked_entry
from bulls.analytics.dse_quality_universe import (
    QualityDividend,
    QualityFinancial,
    QualitySnapshot,
    QualityUniversePolicy,
    quality_universe_at_date,
)


@dataclass(frozen=True)
class QualityPortfolioPolicy:
    rebalance_sessions: int = 63
    target_positions: int = 10
    minimum_positions: int = 10
    gross_target_weight: float = 0.85
    capacity_aware_targets: bool = False
    maximum_position_weight: float = 0.10
    maximum_sector_weight: float = 0.25
    minimum_target_weight: float = 0.005


@dataclass(frozen=True)
class QualityRebalance:
    signal_date: dt.date
    execution_date: dt.date
    eligible_count: int
    targets: tuple[str, ...]
    scores: tuple[tuple[str, float], ...]
    snapshots: tuple[QualitySnapshot, ...]
    target_weights: tuple[tuple[str, float], ...] = ()


@dataclass(frozen=True)
class QualityTrade:
    code: str
    date: dt.date
    side: str
    shares: int
    fill: float
    fee: float
    reason: str


@dataclass(frozen=True)
class QualityPortfolioResult:
    start_date: dt.date | None
    end_date: dt.date | None
    total_return_pct: float
    benchmark_return_pct: float
    excess_return_pct: float
    cash_adjusted_benchmark_return_pct: float
    cash_adjusted_excess_return_pct: float
    maximum_drawdown_pct: float
    fees_paid: float
    turnover_value: float
    average_gross_exposure_pct: float
    ending_gross_exposure_pct: float
    buys: int
    sells: int
    capacity_shortfalls: int
    capacity_rejections: int
    locked_rejections: int
    rebalances: tuple[QualityRebalance, ...]
    trades: tuple[QualityTrade, ...]
    nav_curve: tuple[tuple[dt.date, float], ...]


@dataclass
class _Position:
    shares: int
    last_price: float


def _percentiles(values: dict[str, float], *, higher_is_better: bool) -> dict[str, float]:
    if not values:
        return {}
    unique = sorted(set(values.values()))
    if len(unique) == 1:
        return {code: 1.0 for code in values}
    ranks = {value: index / (len(unique) - 1) for index, value in enumerate(unique)}
    if higher_is_better:
        return {code: ranks[value] for code, value in values.items()}
    return {code: 1 - ranks[value] for code, value in values.items()}


def quality_value_scores(snapshots: dict[str, QualitySnapshot]) -> dict[str, float]:
    """Rank value only after every security has already cleared the absolute quality gate."""

    passing = {code: item for code, item in snapshots.items() if item.passes}
    pe = _percentiles(
        {code: float(item.pe) for code, item in passing.items() if item.pe is not None},
        higher_is_better=False,
    )
    pb = _percentiles(
        {code: float(item.pb) for code, item in passing.items() if item.pb is not None},
        higher_is_better=False,
    )
    roe = _percentiles(
        {code: float(item.roe_pct) for code, item in passing.items() if item.roe_pct is not None},
        higher_is_better=True,
    )
    retention = _percentiles(
        {
            code: min(float(item.eps_retention), 2.0)
            for code, item in passing.items()
            if item.eps_retention is not None
        },
        higher_is_better=True,
    )
    dividends = _percentiles(
        {
            code: float(item.cash_dividend_years)
            for code, item in passing.items()
            if item.cash_dividend_years is not None
        },
        higher_is_better=True,
    )
    scores = {}
    for code in passing:
        if not all(code in component for component in (pe, pb, roe, retention, dividends)):
            continue
        value_score = statistics.fmean((pe[code], pb[code]))
        quality_score = statistics.fmean((roe[code], retention[code], dividends[code]))
        scores[code] = statistics.fmean((value_score, quality_score))
    return scores


def _capacity_aware_weights(
    *,
    ordered: list[str],
    snapshots: dict[str, QualitySnapshot],
    execution_policy: ExecutionPolicy,
    portfolio_policy: QualityPortfolioPolicy,
) -> dict[str, float]:
    """Translate ranked quality into feasible one-session weights with concentration ceilings."""

    weights: dict[str, float] = {}
    sector_weights: dict[str, float] = {}
    remaining = portfolio_policy.gross_target_weight
    for code in ordered:
        if len(weights) >= portfolio_policy.target_positions or remaining <= 0:
            break
        snapshot = snapshots[code]
        sector = snapshot.sector or "Unclassified"
        capacity_weight = (
            (snapshot.trailing_value or 0.0)
            * execution_policy.maximum_adv_participation
            / execution_policy.assumed_capital
        )
        weight = min(
            portfolio_policy.maximum_position_weight,
            capacity_weight,
            portfolio_policy.maximum_sector_weight - sector_weights.get(sector, 0.0),
            remaining,
        )
        if weight < portfolio_policy.minimum_target_weight:
            continue
        weights[code] = weight
        sector_weights[sector] = sector_weights.get(sector, 0.0) + weight
        remaining -= weight
    return weights


def build_quality_rebalances(
    *,
    by_code: dict[str, list[EdgeBar]],
    market_closes: dict[dt.date, float],
    financials: dict[str, list[QualityFinancial]],
    dividends: dict[str, list[QualityDividend]],
    quality_policy: QualityUniversePolicy,
    execution_policy: ExecutionPolicy,
    portfolio_policy: QualityPortfolioPolicy,
    sectors: dict[str, str] | None = None,
) -> list[QualityRebalance]:
    """Freeze quarterly target lists after each completed close for next-session execution."""

    market_dates = sorted(market_closes)
    if len(market_dates) <= quality_policy.minimum_history + 1:
        return []
    result = []
    for market_index in range(
        quality_policy.minimum_history,
        len(market_dates) - 1,
        portfolio_policy.rebalance_sessions,
    ):
        signal_date = market_dates[market_index]
        execution_date = market_dates[market_index + 1]
        audit = quality_universe_at_date(
            signal_date=signal_date,
            next_market_date=execution_date,
            by_code=by_code,
            financials=financials,
            dividends=dividends,
            quality_policy=quality_policy,
            execution_policy=execution_policy,
            sectors=sectors,
        )
        snapshots = {code: item for code, item in audit.items() if item.passes}
        scores = quality_value_scores(snapshots)
        ordered = sorted(scores, key=lambda code: (-scores[code], code))
        targets: tuple[str, ...] = ()
        target_weights: dict[str, float] = {}
        if len(ordered) >= portfolio_policy.minimum_positions:
            if portfolio_policy.capacity_aware_targets:
                target_weights = _capacity_aware_weights(
                    ordered=ordered,
                    snapshots=snapshots,
                    execution_policy=execution_policy,
                    portfolio_policy=portfolio_policy,
                )
                targets = tuple(target_weights)
            else:
                targets = tuple(ordered[: portfolio_policy.target_positions])
                equal_weight = (
                    portfolio_policy.gross_target_weight / len(targets) if targets else 0.0
                )
                target_weights = {code: equal_weight for code in targets}
        result.append(
            QualityRebalance(
                signal_date=signal_date,
                execution_date=execution_date,
                eligible_count=len(snapshots),
                targets=targets,
                scores=tuple((code, scores[code]) for code in ordered),
                snapshots=tuple(snapshots[code] for code in sorted(snapshots)),
                target_weights=tuple(target_weights.items()),
            )
        )
    return result


def _benchmark_return(
    market_closes: dict[dt.date, float],
    start_date: dt.date,
    end_date: dt.date,
) -> float:
    dates = [date for date in sorted(market_closes) if start_date <= date <= end_date]
    if len(dates) < 2 or market_closes[dates[0]] <= 0:
        return 0.0
    return market_closes[dates[-1]] / market_closes[dates[0]] - 1


def _maximum_drawdown(values: list[float]) -> float:
    if not values:
        return 0.0
    peak = values[0]
    drawdown = 0.0
    for value in values:
        peak = max(peak, value)
        drawdown = max(drawdown, 1 - value / peak)
    return drawdown


def _cash_adjusted_benchmark_return(
    market_closes: dict[dt.date, float],
    start_date: dt.date,
    end_date: dt.date,
    *,
    invested_weight: float,
) -> float:
    dates = [date for date in sorted(market_closes) if start_date <= date <= end_date]
    multiple = 1.0
    for previous_date, current_date in pairwise(dates):
        previous = market_closes[previous_date]
        if previous <= 0:
            continue
        market_return = market_closes[current_date] / previous - 1
        multiple *= 1 + invested_weight * market_return
    return multiple - 1


def _limit_locked_sell(previous: EdgeBar, current: EdgeBar) -> bool:
    gap = current.open / previous.close - 1 if previous.close > 0 else 0.0
    intraday_range = (
        (current.high - current.low) / current.open if current.open > 0 else float("inf")
    )
    return gap <= -0.075 and intraday_range <= 0.002


def simulate_quality_portfolio(
    *,
    rebalances: list[QualityRebalance],
    by_code: dict[str, list[EdgeBar]],
    market_closes: dict[dt.date, float],
    execution_policy: ExecutionPolicy,
    portfolio_policy: QualityPortfolioPolicy,
    signal_start: dt.date | None = None,
    signal_end: dt.date | None = None,
) -> QualityPortfolioResult:
    """Execute target changes at the next open with fees, slippage, capacity, and T+2 cash."""

    selected_rebalances = [
        item
        for item in rebalances
        if (signal_start is None or item.signal_date >= signal_start)
        and (signal_end is None or item.signal_date < signal_end)
    ]
    if not selected_rebalances:
        return QualityPortfolioResult(
            start_date=None,
            end_date=None,
            total_return_pct=0.0,
            benchmark_return_pct=0.0,
            excess_return_pct=0.0,
            cash_adjusted_benchmark_return_pct=0.0,
            cash_adjusted_excess_return_pct=0.0,
            maximum_drawdown_pct=0.0,
            fees_paid=0.0,
            turnover_value=0.0,
            average_gross_exposure_pct=0.0,
            ending_gross_exposure_pct=0.0,
            buys=0,
            sells=0,
            capacity_shortfalls=0,
            capacity_rejections=0,
            locked_rejections=0,
            rebalances=(),
            trades=(),
            nav_curve=(),
        )

    bar_maps = {
        code: {bar.date: bar for bar in sorted(bars, key=lambda item: item.date)}
        for code, bars in by_code.items()
    }
    rebalance_by_execution = {item.execution_date: item for item in selected_rebalances}
    start_date = selected_rebalances[0].execution_date
    market_dates = sorted(market_closes)
    requested_end = (
        min(signal_end - dt.timedelta(days=1), market_dates[-1])
        if signal_end is not None
        else market_dates[-1]
    )
    axis = [date for date in market_dates if start_date <= date <= requested_end]
    if not axis:
        return simulate_quality_portfolio(
            rebalances=[],
            by_code=by_code,
            market_closes=market_closes,
            execution_policy=execution_policy,
            portfolio_policy=portfolio_policy,
        )
    axis_index = {date: index for index, date in enumerate(axis)}

    cash = execution_policy.assumed_capital
    pending_cash: list[tuple[dt.date, float]] = []
    positions: dict[str, _Position] = {}
    trades: list[QualityTrade] = []
    nav_curve: list[tuple[dt.date, float]] = []
    gross_exposures: list[float] = []
    fees_paid = 0.0
    turnover_value = 0.0
    capacity_shortfalls = 0
    capacity_rejections = 0
    locked_rejections = 0

    for date in axis:
        matured = [item for item in pending_cash if item[0] <= date]
        cash += sum(value for _, value in matured)
        pending_cash = [item for item in pending_cash if item[0] > date]

        rebalance = rebalance_by_execution.get(date)
        if rebalance is not None:
            targets = set(rebalance.targets)
            target_weights = dict(rebalance.target_weights)
            if targets and not target_weights:
                target_weights = {
                    code: portfolio_policy.gross_target_weight / len(targets) for code in targets
                }
            snapshot_by_code = {item.code: item for item in rebalance.snapshots}
            opening_prices = {
                code: bar_maps.get(code, {}).get(date).open
                for code in set(positions) | targets
                if bar_maps.get(code, {}).get(date) is not None
            }
            opening_nav = (
                cash
                + sum(value for _, value in pending_cash)
                + sum(
                    position.shares * opening_prices.get(code, position.last_price)
                    for code, position in positions.items()
                )
            )
            for code, position in list(positions.items()):
                bar = bar_maps.get(code, {}).get(date)
                previous = bar_maps.get(code, {}).get(rebalance.signal_date)
                if bar is None or previous is None:
                    continue
                current_value = position.shares * bar.open
                target_value = opening_nav * target_weights.get(code, 0.0)
                excess_value = (
                    current_value if code not in targets else max(0.0, current_value - target_value)
                )
                shares = min(position.shares, int(excess_value / bar.open))
                if shares <= 0:
                    continue
                if _limit_locked_sell(previous, bar):
                    locked_rejections += 1
                    continue
                fill = bar.open * (1 - execution_policy.slippage_rate)
                gross = shares * fill
                fee = gross * execution_policy.fee_rate
                settlement_index = min(axis_index[date] + 2, len(axis) - 1)
                pending_cash.append((axis[settlement_index], gross - fee))
                position.shares -= shares
                position.last_price = bar.close
                if position.shares == 0:
                    positions.pop(code)
                fees_paid += fee
                turnover_value += gross
                trades.append(
                    QualityTrade(
                        code=code,
                        date=date,
                        side="sell",
                        shares=shares,
                        fill=round(fill, 4),
                        fee=round(fee, 2),
                        reason="left_target" if code not in targets else "rebalance_down",
                    )
                )

            planned_buys: list[tuple[str, EdgeBar, int]] = []
            ordered_targets = [code for code, _score in rebalance.scores if code in targets]
            for code in ordered_targets:
                bar = bar_maps.get(code, {}).get(date)
                previous = bar_maps.get(code, {}).get(rebalance.signal_date)
                snapshot = snapshot_by_code.get(code)
                if bar is None or previous is None or snapshot is None:
                    continue
                if limit_locked_entry(previous, bar):
                    locked_rejections += 1
                    continue
                current = positions.get(code)
                current_value = current.shares * bar.open if current is not None else 0.0
                target_value = opening_nav * target_weights.get(code, 0.0)
                desired_value = max(0.0, target_value - current_value)
                trade_capacity = (
                    snapshot.trailing_value or 0.0
                ) * execution_policy.maximum_adv_participation
                if trade_capacity < desired_value:
                    capacity_shortfalls += 1
                budget = min(desired_value, trade_capacity)
                fill = bar.open * (1 + execution_policy.slippage_rate)
                shares = int(budget / (fill * (1 + execution_policy.fee_rate)))
                if shares <= 0:
                    if desired_value > 0:
                        capacity_rejections += 1
                    continue
                planned_buys.append((code, bar, shares))

            full_cost = sum(
                shares
                * bar.open
                * (1 + execution_policy.slippage_rate)
                * (1 + execution_policy.fee_rate)
                for _code, bar, shares in planned_buys
            )
            cash_scale = min(1.0, cash / full_cost) if full_cost > 0 else 1.0
            for code, bar, planned_shares in planned_buys:
                shares = int(planned_shares * cash_scale)
                if shares <= 0:
                    capacity_rejections += 1
                    continue
                fill = bar.open * (1 + execution_policy.slippage_rate)
                gross = shares * fill
                fee = gross * execution_policy.fee_rate
                if gross + fee > cash + 1e-8:
                    raise RuntimeError("DSE batch buy allocation exceeded settled cash")
                cash -= gross + fee
                fees_paid += fee
                turnover_value += gross
                current = positions.get(code)
                if current is None:
                    positions[code] = _Position(shares=shares, last_price=bar.close)
                else:
                    current.shares += shares
                    current.last_price = bar.close
                trades.append(
                    QualityTrade(
                        code=code,
                        date=date,
                        side="buy",
                        shares=shares,
                        fill=round(fill, 4),
                        fee=round(fee, 2),
                        reason="target_rebalance",
                    )
                )

        for code, position in positions.items():
            bar = bar_maps.get(code, {}).get(date)
            if bar is not None:
                position.last_price = bar.close
        nav = (
            cash
            + sum(value for _, value in pending_cash)
            + sum(position.shares * position.last_price for position in positions.values())
        )
        nav_curve.append((date, nav))
        gross_value = sum(position.shares * position.last_price for position in positions.values())
        gross_exposures.append(gross_value / nav if nav > 0 else 0.0)

    end_date = axis[-1]
    total_return = nav_curve[-1][1] / execution_policy.assumed_capital - 1
    benchmark_return = _benchmark_return(market_closes, start_date, end_date)
    cash_adjusted_benchmark = _cash_adjusted_benchmark_return(
        market_closes,
        start_date,
        end_date,
        invested_weight=portfolio_policy.gross_target_weight,
    )
    return QualityPortfolioResult(
        start_date=start_date,
        end_date=end_date,
        total_return_pct=round(total_return * 100, 3),
        benchmark_return_pct=round(benchmark_return * 100, 3),
        excess_return_pct=round((total_return - benchmark_return) * 100, 3),
        cash_adjusted_benchmark_return_pct=round(cash_adjusted_benchmark * 100, 3),
        cash_adjusted_excess_return_pct=round(
            (total_return - cash_adjusted_benchmark) * 100,
            3,
        ),
        maximum_drawdown_pct=round(
            _maximum_drawdown([value for _, value in nav_curve]) * 100,
            3,
        ),
        fees_paid=round(fees_paid, 2),
        turnover_value=round(turnover_value, 2),
        average_gross_exposure_pct=round(statistics.fmean(gross_exposures) * 100, 3),
        ending_gross_exposure_pct=round(gross_exposures[-1] * 100, 3),
        buys=sum(item.side == "buy" for item in trades),
        sells=sum(item.side == "sell" for item in trades),
        capacity_shortfalls=capacity_shortfalls,
        capacity_rejections=capacity_rejections,
        locked_rejections=locked_rejections,
        rebalances=tuple(selected_rebalances),
        trades=tuple(trades),
        nav_curve=tuple(nav_curve),
    )
