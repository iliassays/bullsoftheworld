"""Execution, validation, and portfolio simulation for registered DSE edge signals."""

from __future__ import annotations

import datetime as dt
import random
import statistics
from bisect import bisect_left, bisect_right
from collections import defaultdict
from dataclasses import dataclass
from itertools import pairwise
from typing import Literal

from bulls.analytics.dse_edges import (
    DEFAULT_EXECUTION_POLICY,
    EdgeBar,
    EdgeSignal,
    EdgeSpec,
    ExecutionPolicy,
    limit_locked_entry,
)


@dataclass(frozen=True)
class EdgeOutcome:
    strategy: str
    code: str
    signal_date: dt.date
    entry_date: dt.date
    exit_date: dt.date
    entry_fill: float
    exit_fill: float
    net_return_pct: float
    benchmark_return_pct: float
    excess_return_pct: float
    maximum_favorable_excursion_pct: float
    maximum_adverse_excursion_pct: float
    exit_reason: Literal["stop", "target", "time"]


@dataclass(frozen=True)
class OutcomeSummary:
    observations: int
    mean_return_pct: float | None
    median_return_pct: float | None
    win_rate_pct: float | None
    mean_excess_return_pct: float | None
    median_excess_return_pct: float | None
    profit_factor: float | None
    median_mfe_pct: float | None
    median_mae_pct: float | None
    mean_excess_ci_low_pct: float | None
    mean_excess_ci_high_pct: float | None


@dataclass(frozen=True)
class PromotionDecision:
    eligible_for_forward_paper: bool
    failed_gates: tuple[str, ...]


@dataclass(frozen=True)
class PortfolioTrade:
    code: str
    entry_date: dt.date
    exit_date: dt.date
    net_return_pct: float
    exit_reason: Literal["stop", "target", "time"]


@dataclass(frozen=True)
class PortfolioSummary:
    start_date: dt.date | None
    end_date: dt.date | None
    total_return_pct: float
    benchmark_return_pct: float
    excess_return_pct: float
    maximum_drawdown_pct: float
    trades: int
    win_rate_pct: float | None
    profit_factor: float | None
    fees_paid: float
    capacity_rejections: int
    slot_rejections: int


@dataclass
class _OpenPosition:
    code: str
    shares: int
    entry_date: dt.date
    entry_fill: float
    stop_price: float
    target_price: float
    sessions: int = 0


def _benchmark_return(
    market_closes: dict[dt.date, float],
    start_date: dt.date,
    end_date: dt.date,
) -> float:
    dates = sorted(market_closes)
    if not dates:
        return 0.0
    start_index = bisect_left(dates, start_date)
    end_index = bisect_right(dates, end_date) - 1
    if start_index >= len(dates) or end_index < 0 or start_index > end_index:
        return 0.0
    start_value = market_closes[dates[start_index]]
    end_value = market_closes[dates[end_index]]
    return end_value / start_value - 1 if start_value > 0 else 0.0


def evaluate_signal(
    *,
    signal: EdgeSignal,
    bars: list[EdgeBar],
    market_closes: dict[dt.date, float],
    spec: EdgeSpec,
    policy: ExecutionPolicy = DEFAULT_EXECUTION_POLICY,
) -> EdgeOutcome | None:
    """Model one next-open trade with conservative gap and stop/target handling."""

    bars = sorted(bars, key=lambda item: item.date)
    if signal.entry_index >= len(bars):
        return None
    signal_bar = bars[signal.signal_index]
    entry_bar = bars[signal.entry_index]
    if limit_locked_entry(signal_bar, entry_bar):
        return None
    maximum_position_value = signal.trailing_value * policy.maximum_adv_participation
    target_position_value = policy.assumed_capital * policy.target_position_weight
    if maximum_position_value < target_position_value * 0.50:
        return None

    entry_fill = entry_bar.open * (1 + policy.slippage_rate)
    stop_price = entry_fill * (1 + spec.stop_loss)
    target_price = entry_fill * (1 + spec.take_profit)
    required_final_index = signal.entry_index + spec.holding_sessions - 1
    final_index = min(required_final_index, len(bars) - 1)
    if final_index <= signal.entry_index:
        return None
    outcome_window = bars[signal.entry_index : final_index + 1]
    for previous, current in pairwise(outcome_window):
        if previous.close > 0 and abs(current.close / previous.close - 1) > 0.35:
            return None

    exit_bar: EdgeBar | None = None
    exit_raw: float | None = None
    reason: Literal["stop", "target", "time"] = "time"
    for current in outcome_window:
        if current.open <= stop_price:
            exit_bar = current
            exit_raw = current.open
            reason = "stop"
            break
        if current.open >= target_price:
            exit_bar = current
            exit_raw = current.open
            reason = "target"
            break
        if current.low <= stop_price:
            exit_bar = current
            exit_raw = stop_price
            reason = "stop"
            break
        if current.high >= target_price:
            exit_bar = current
            exit_raw = target_price
            reason = "target"
            break

    if exit_bar is None or exit_raw is None:
        if required_final_index >= len(bars):
            return None
        exit_bar = outcome_window[-1]
        exit_raw = exit_bar.close

    exit_fill = exit_raw * (1 - policy.slippage_rate)
    net_multiple = exit_fill * (1 - policy.fee_rate) / (
        entry_fill * (1 + policy.fee_rate)
    )
    benchmark_return = _benchmark_return(market_closes, entry_bar.date, exit_bar.date)
    mfe = max(bar.high for bar in outcome_window) / entry_fill - 1
    mae = min(bar.low for bar in outcome_window) / entry_fill - 1
    net_return = net_multiple - 1
    return EdgeOutcome(
        strategy=spec.key,
        code=signal.code,
        signal_date=signal.signal_date,
        entry_date=entry_bar.date,
        exit_date=exit_bar.date,
        entry_fill=round(entry_fill, 4),
        exit_fill=round(exit_fill, 4),
        net_return_pct=round(net_return * 100, 4),
        benchmark_return_pct=round(benchmark_return * 100, 4),
        excess_return_pct=round((net_return - benchmark_return) * 100, 4),
        maximum_favorable_excursion_pct=round(mfe * 100, 4),
        maximum_adverse_excursion_pct=round(mae * 100, 4),
        exit_reason=reason,
    )


def evaluate_signals(
    *,
    signals: list[EdgeSignal],
    by_code: dict[str, list[EdgeBar]],
    market_closes: dict[dt.date, float],
    spec: EdgeSpec,
    policy: ExecutionPolicy = DEFAULT_EXECUTION_POLICY,
) -> list[EdgeOutcome]:
    outcomes = []
    for signal in signals:
        outcome = evaluate_signal(
            signal=signal,
            bars=by_code[signal.code],
            market_closes=market_closes,
            spec=spec,
            policy=policy,
        )
        if outcome is not None:
            outcomes.append(outcome)
    return outcomes


def split_outcomes(
    outcomes: list[EdgeOutcome],
    *,
    train_end: dt.date,
    validation_end: dt.date,
) -> dict[str, list[EdgeOutcome]]:
    """Chronological splits with an outcome embargo at each boundary."""

    return {
        "train": [
            item
            for item in outcomes
            if item.signal_date < train_end and item.exit_date < train_end
        ],
        "validation": [
            item
            for item in outcomes
            if train_end <= item.signal_date < validation_end
            and item.exit_date < validation_end
        ],
        "test": [item for item in outcomes if item.signal_date >= validation_end],
    }


def _cluster_bootstrap_mean_ci(
    outcomes: list[EdgeOutcome],
    *,
    iterations: int = 1_000,
    seed: int = 19,
) -> tuple[float | None, float | None]:
    if len(outcomes) < 8:
        return None, None
    clusters: dict[dt.date, list[float]] = defaultdict(list)
    for outcome in outcomes:
        clusters[outcome.signal_date].append(outcome.excess_return_pct)
    dates = sorted(clusters)
    if len(dates) < 5:
        return None, None
    rng = random.Random(seed)
    means = []
    for _ in range(iterations):
        values = []
        for _ in dates:
            values.extend(clusters[rng.choice(dates)])
        means.append(statistics.fmean(values))
    means.sort()
    return means[int(iterations * 0.025)], means[int(iterations * 0.975) - 1]


def summarize_outcomes(outcomes: list[EdgeOutcome]) -> OutcomeSummary:
    if not outcomes:
        return OutcomeSummary(
            observations=0,
            mean_return_pct=None,
            median_return_pct=None,
            win_rate_pct=None,
            mean_excess_return_pct=None,
            median_excess_return_pct=None,
            profit_factor=None,
            median_mfe_pct=None,
            median_mae_pct=None,
            mean_excess_ci_low_pct=None,
            mean_excess_ci_high_pct=None,
        )
    returns = [item.net_return_pct for item in outcomes]
    excess = [item.excess_return_pct for item in outcomes]
    gains = sum(value for value in returns if value > 0)
    losses = abs(sum(value for value in returns if value <= 0))
    ci_low, ci_high = _cluster_bootstrap_mean_ci(outcomes)
    return OutcomeSummary(
        observations=len(outcomes),
        mean_return_pct=round(statistics.fmean(returns), 3),
        median_return_pct=round(statistics.median(returns), 3),
        win_rate_pct=round(100 * sum(value > 0 for value in returns) / len(returns), 2),
        mean_excess_return_pct=round(statistics.fmean(excess), 3),
        median_excess_return_pct=round(statistics.median(excess), 3),
        profit_factor=round(gains / losses, 3) if losses > 0 else None,
        median_mfe_pct=round(
            statistics.median(
                item.maximum_favorable_excursion_pct for item in outcomes
            ),
            3,
        ),
        median_mae_pct=round(
            statistics.median(item.maximum_adverse_excursion_pct for item in outcomes),
            3,
        ),
        mean_excess_ci_low_pct=round(ci_low, 3) if ci_low is not None else None,
        mean_excess_ci_high_pct=round(ci_high, 3) if ci_high is not None else None,
    )


def _portfolio_drawdown(values: list[float]) -> float:
    peak = values[0]
    maximum = 0.0
    for value in values:
        peak = max(peak, value)
        maximum = max(maximum, 1 - value / peak)
    return maximum


def simulate_portfolio(
    *,
    signals: list[EdgeSignal],
    valid_outcomes: list[EdgeOutcome],
    by_code: dict[str, list[EdgeBar]],
    market_closes: dict[dt.date, float],
    spec: EdgeSpec,
    policy: ExecutionPolicy = DEFAULT_EXECUTION_POLICY,
    maximum_positions: int = 10,
) -> PortfolioSummary:
    """Simulate an equal-risk DSE book with integer shares and T+2 sell settlement."""

    if maximum_positions <= 0:
        raise ValueError("maximum_positions must be positive")
    valid_keys = {(item.code, item.signal_date) for item in valid_outcomes}
    eligible_signals = [
        signal for signal in signals if (signal.code, signal.signal_date) in valid_keys
    ]
    if not eligible_signals:
        return PortfolioSummary(
            start_date=None,
            end_date=None,
            total_return_pct=0.0,
            benchmark_return_pct=0.0,
            excess_return_pct=0.0,
            maximum_drawdown_pct=0.0,
            trades=0,
            win_rate_pct=None,
            profit_factor=None,
            fees_paid=0.0,
            capacity_rejections=0,
            slot_rejections=0,
        )

    bar_maps = {
        code: {bar.date: bar for bar in sorted(bars, key=lambda item: item.date)}
        for code, bars in by_code.items()
    }
    last_prices: dict[str, float] = {}
    signals_by_entry: dict[dt.date, list[EdgeSignal]] = defaultdict(list)
    for signal in eligible_signals:
        signals_by_entry[signal.entry_date].append(signal)
    for same_day in signals_by_entry.values():
        same_day.sort(key=lambda item: (-item.score, item.code))

    start_date = min(signal.entry_date for signal in eligible_signals)
    latest_exit_by_key = {
        (item.code, item.signal_date): item.exit_date for item in valid_outcomes
    }
    end_date = max(
        latest_exit_by_key[(signal.code, signal.signal_date)]
        for signal in eligible_signals
    )
    axis = sorted(
        {
            date
            for bars in bar_maps.values()
            for date in bars
            if start_date <= date <= end_date
        }
        | {date for date in market_closes if start_date <= date <= end_date}
    )
    axis_index = {date: index for index, date in enumerate(axis)}
    cash = policy.assumed_capital
    pending_cash: list[tuple[dt.date, float]] = []
    positions: dict[str, _OpenPosition] = {}
    completed: list[PortfolioTrade] = []
    nav_curve: list[float] = []
    fees_paid = 0.0
    capacity_rejections = 0
    slot_rejections = 0

    for date in axis:
        matured = [item for item in pending_cash if item[0] <= date]
        cash += sum(value for _, value in matured)
        pending_cash = [item for item in pending_cash if item[0] > date]

        for code in positions:
            bar = bar_maps[code].get(date)
            if bar is not None:
                last_prices[code] = bar.open
        opening_nav = (
            cash
            + sum(value for _, value in pending_cash)
            + sum(
                position.shares * last_prices.get(code, position.entry_fill)
                for code, position in positions.items()
            )
        )

        for signal in signals_by_entry.get(date, []):
            if signal.code in positions:
                continue
            if len(positions) >= maximum_positions:
                slot_rejections += 1
                continue
            bar = bar_maps[signal.code].get(date)
            signal_bar = bar_maps[signal.code].get(signal.signal_date)
            if bar is None or signal_bar is None or limit_locked_entry(signal_bar, bar):
                capacity_rejections += 1
                continue
            desired_value = opening_nav * policy.target_position_weight
            capacity_value = signal.trailing_value * policy.maximum_adv_participation
            if capacity_value < desired_value * 0.50:
                capacity_rejections += 1
                continue
            fill = bar.open * (1 + policy.slippage_rate)
            budget = min(desired_value, capacity_value, cash)
            shares = int(budget / (fill * (1 + policy.fee_rate)))
            if shares <= 0:
                capacity_rejections += 1
                continue
            gross = shares * fill
            fee = gross * policy.fee_rate
            cash -= gross + fee
            fees_paid += fee
            positions[signal.code] = _OpenPosition(
                code=signal.code,
                shares=shares,
                entry_date=date,
                entry_fill=fill,
                stop_price=fill * (1 + spec.stop_loss),
                target_price=fill * (1 + spec.take_profit),
            )
            last_prices[signal.code] = bar.close

        for code, position in list(positions.items()):
            bar = bar_maps[code].get(date)
            if bar is None:
                continue
            position.sessions += 1
            exit_raw: float | None = None
            reason: Literal["stop", "target", "time"] = "time"
            if bar.open <= position.stop_price:
                exit_raw = bar.open
                reason = "stop"
            elif bar.open >= position.target_price:
                exit_raw = bar.open
                reason = "target"
            elif bar.low <= position.stop_price:
                exit_raw = position.stop_price
                reason = "stop"
            elif bar.high >= position.target_price:
                exit_raw = position.target_price
                reason = "target"
            elif position.sessions >= spec.holding_sessions:
                exit_raw = bar.close
                reason = "time"
            if exit_raw is None:
                last_prices[code] = bar.close
                continue

            fill = exit_raw * (1 - policy.slippage_rate)
            gross = position.shares * fill
            fee = gross * policy.fee_rate
            proceeds = gross - fee
            fees_paid += fee
            settlement_index = min(axis_index[date] + 2, len(axis) - 1)
            pending_cash.append((axis[settlement_index], proceeds))
            net_return = fill * (1 - policy.fee_rate) / (
                position.entry_fill * (1 + policy.fee_rate)
            ) - 1
            completed.append(
                PortfolioTrade(
                    code=code,
                    entry_date=position.entry_date,
                    exit_date=date,
                    net_return_pct=round(net_return * 100, 4),
                    exit_reason=reason,
                )
            )
            positions.pop(code)
            last_prices.pop(code, None)

        for code in positions:
            bar = bar_maps[code].get(date)
            if bar is not None:
                last_prices[code] = bar.close
        nav_curve.append(
            cash
            + sum(value for _, value in pending_cash)
            + sum(
                position.shares * last_prices.get(code, position.entry_fill)
                for code, position in positions.items()
            )
        )

    final_nav = nav_curve[-1] if nav_curve else policy.assumed_capital
    benchmark_return = _benchmark_return(market_closes, start_date, end_date)
    returns = [item.net_return_pct for item in completed]
    gains = sum(value for value in returns if value > 0)
    losses = abs(sum(value for value in returns if value <= 0))
    total_return = final_nav / policy.assumed_capital - 1
    return PortfolioSummary(
        start_date=start_date,
        end_date=end_date,
        total_return_pct=round(total_return * 100, 3),
        benchmark_return_pct=round(benchmark_return * 100, 3),
        excess_return_pct=round((total_return - benchmark_return) * 100, 3),
        maximum_drawdown_pct=round(_portfolio_drawdown(nav_curve) * 100, 3),
        trades=len(completed),
        win_rate_pct=(
            round(100 * sum(value > 0 for value in returns) / len(returns), 2)
            if returns
            else None
        ),
        profit_factor=round(gains / losses, 3) if losses > 0 else None,
        fees_paid=round(fees_paid, 2),
        capacity_rejections=capacity_rejections,
        slot_rejections=slot_rejections,
    )


def promotion_decision(
    *,
    base_splits: dict[str, OutcomeSummary],
    stressed_splits: dict[str, OutcomeSummary],
) -> PromotionDecision:
    """Require independent holdouts and stressed-cost survival before forward paper trading."""

    failed: list[str] = []
    minimum_observations = {"train": 20, "validation": 15, "test": 15}
    for label in ("train", "validation", "test"):
        base = base_splits[label]
        stressed = stressed_splits[label]
        if base.observations < minimum_observations[label]:
            failed.append(
                f"{label}: fewer than {minimum_observations[label]} "
                "independent executable outcomes"
            )
        if base.mean_excess_return_pct is None or base.mean_excess_return_pct <= 0:
            failed.append(f"{label}: mean excess return is not positive")
        if base.median_return_pct is None or base.median_return_pct <= 0:
            failed.append(f"{label}: median net return is not positive")
        if base.profit_factor is None or base.profit_factor <= 1.10:
            failed.append(f"{label}: profit factor does not exceed 1.10")
        if stressed.mean_return_pct is None or stressed.mean_return_pct <= 0:
            failed.append(f"{label}: return does not survive stressed slippage")
    return PromotionDecision(
        eligible_for_forward_paper=not failed,
        failed_gates=tuple(failed),
    )
