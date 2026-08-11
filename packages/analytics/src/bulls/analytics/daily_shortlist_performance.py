"""Point-in-time performance evidence for the DSE daily research shortlist.

The shortlist is created after a completed close. Selection-close returns therefore measure
follow-through, not an executable trade. A separate next-open series is provided as a gross
execution proxy, with obviously limit-locked entries excluded. All horizons use exchange session
dates rather than a ticker's next observed bar so suspensions cannot silently stretch "1 session"
into several market days.
"""

from __future__ import annotations

import datetime as dt
import random
import statistics
from bisect import bisect_right
from collections import defaultdict
from dataclasses import dataclass, replace

HORIZONS = (1, 3, 5, 10)
EPISODE_COOLDOWN_SESSIONS = 10
SUSPICIOUS_CLOSE_JUMP = 0.35


@dataclass(frozen=True, slots=True)
class ShortlistAppearance:
    code: str
    as_of: dt.date
    close: float
    rank: int
    evidence_mode: str


@dataclass(frozen=True, slots=True)
class ShortlistPriceBar:
    code: str
    date: dt.date
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0


@dataclass(frozen=True, slots=True)
class BenchmarkClose:
    date: dt.date
    close: float


@dataclass(frozen=True, slots=True)
class ArchiveIntegrity:
    rows: int
    sessions: int
    matched_selection_closes: int
    missing_selection_bars: int
    close_mismatches: int
    matched_selection_moves: int
    missing_move_inputs: int
    move_mismatches: int
    incomplete_sessions: int
    invalid_rank_sessions: int
    methodology_versions: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class HorizonPerformance:
    sessions: int
    matured_appearances: int
    observations: int
    benchmark_observations: int
    pending_appearances: int
    missing_bar_appearances: int
    suspicious_price_paths: int
    coverage_pct: float | None
    mean_return_pct: float | None
    median_return_pct: float | None
    positive_rate_pct: float | None
    mean_benchmark_return_pct: float | None
    mean_excess_return_pct: float | None
    median_excess_return_pct: float | None
    excess_ci_low_pct: float | None
    excess_ci_high_pct: float | None
    next_open_observations: int
    limit_locked_entries: int
    next_open_mean_return_pct: float | None
    next_open_median_return_pct: float | None
    next_open_positive_rate_pct: float | None


@dataclass(frozen=True, slots=True)
class PerformanceCohort:
    key: str
    appearances: int
    selection_sessions: int
    first_selection_date: dt.date | None
    last_selection_date: dt.date | None
    horizons: tuple[HorizonPerformance, ...]


@dataclass(frozen=True, slots=True)
class ShortlistPerformanceReport:
    as_of: dt.date | None
    all_appearances: int
    forward_appearances: int
    reconstructed_appearances: int
    independent_episodes: int
    cohorts: tuple[PerformanceCohort, ...]


@dataclass(frozen=True, slots=True)
class MatchedControlHorizon:
    sessions: int
    selection_sessions: int
    shortlist_mean_return_pct: float | None
    control_mean_return_pct: float | None
    shortlist_minus_control_pct: float | None
    daily_difference_median_pct: float | None
    shortlist_outperformed_rate_pct: float | None
    difference_ci_low_pct: float | None
    difference_ci_high_pct: float | None
    next_open_shortlist_mean_pct: float | None
    next_open_control_mean_pct: float | None
    next_open_difference_pct: float | None
    next_open_ci_low_pct: float | None
    next_open_ci_high_pct: float | None


@dataclass(frozen=True, slots=True)
class MatchedControlReport:
    control: str
    selection_sessions: int
    horizons: tuple[MatchedControlHorizon, ...]


@dataclass(frozen=True, slots=True)
class ShortlistPortfolioPolicy:
    """Frozen execution assumptions for one shortlist portfolio diagnostic."""

    key: str
    holding_sessions: int = 3
    included_ranks: tuple[int, ...] = (1,)
    initial_capital: float = 1_000_000.0
    target_position_weight: float = 0.10
    maximum_positions: int = 10
    fee_rate: float = 0.004
    slippage_rate: float = 0.0025
    maximum_adv_participation: float = 0.02
    minimum_target_fill: float = 0.50
    settlement_sessions: int = 2

    def __post_init__(self) -> None:
        if self.holding_sessions <= 0:
            raise ValueError("holding_sessions must be positive")
        if not self.included_ranks or min(self.included_ranks) <= 0:
            raise ValueError("included_ranks must contain positive ranks")
        if self.initial_capital <= 0:
            raise ValueError("initial_capital must be positive")
        if not 0 < self.target_position_weight <= 1:
            raise ValueError("target_position_weight must be in (0, 1]")
        if self.maximum_positions <= 0:
            raise ValueError("maximum_positions must be positive")
        if min(self.fee_rate, self.slippage_rate, self.maximum_adv_participation) < 0:
            raise ValueError("cost and participation rates cannot be negative")
        if not 0 <= self.minimum_target_fill <= 1:
            raise ValueError("minimum_target_fill must be in [0, 1]")
        if self.settlement_sessions < 0:
            raise ValueError("settlement_sessions cannot be negative")


@dataclass(frozen=True, slots=True)
class ShortlistPortfolioTrade:
    code: str
    rank: int
    evidence_mode: str
    signal_date: dt.date
    entry_date: dt.date
    exit_date: dt.date
    entry_fill: float
    exit_fill: float
    shares: int
    net_return_pct: float


@dataclass(frozen=True, slots=True)
class ShortlistPortfolioReport:
    policy: ShortlistPortfolioPolicy
    evidence_scope: str
    start_date: dt.date | None
    end_date: dt.date | None
    signals_considered: int
    entries: int
    completed_trades: int
    open_positions: int
    total_return_pct: float
    benchmark_return_pct: float
    maximum_drawdown_pct: float
    average_gross_exposure_pct: float
    win_rate_pct: float | None
    profit_factor: float | None
    fees_paid: float
    missing_entry_rejections: int
    limit_locked_rejections: int
    capacity_rejections: int
    slot_rejections: int
    duplicate_position_rejections: int
    cash_rejections: int
    delayed_suspension_exits: int
    trades: tuple[ShortlistPortfolioTrade, ...]


@dataclass(slots=True)
class _PortfolioPosition:
    code: str
    rank: int
    evidence_mode: str
    signal_date: dt.date
    entry_date: dt.date
    entry_fill: float
    shares: int
    planned_exit_index: int
    exit_was_delayed: bool = False


@dataclass(frozen=True, slots=True)
class _Observation:
    selection_date: dt.date
    return_pct: float
    benchmark_return_pct: float | None
    excess_return_pct: float | None
    next_open_return_pct: float | None
    limit_locked: bool


def _rounded(value: float | None, digits: int = 3) -> float | None:
    return round(value, digits) if value is not None else None


def _portfolio_drawdown(values: list[float]) -> float:
    if not values:
        return 0.0
    peak = values[0]
    maximum = 0.0
    for value in values:
        peak = max(peak, value)
        if peak > 0:
            maximum = max(maximum, 1.0 - value / peak)
    return maximum


def _benchmark_period_return(
    benchmark_by_date: dict[dt.date, float],
    *,
    start_date: dt.date,
    end_date: dt.date,
) -> float:
    dates = [
        date
        for date in sorted(benchmark_by_date)
        if start_date <= date <= end_date and benchmark_by_date[date] > 0
    ]
    if len(dates) < 2:
        return 0.0
    return benchmark_by_date[dates[-1]] / benchmark_by_date[dates[0]] - 1.0


def _trailing_average_traded_value(
    code_bars: dict[dt.date, ShortlistPriceBar],
    *,
    through: dt.date,
    sessions: int = 20,
) -> float:
    history = [
        bar.close * bar.volume
        for date, bar in sorted(code_bars.items())
        if date <= through and bar.close > 0 and bar.volume > 0
    ][-sessions:]
    return statistics.fmean(history) if history else 0.0


def simulate_shortlist_portfolio(
    *,
    appearances: list[ShortlistAppearance],
    bars: list[ShortlistPriceBar],
    benchmark: list[BenchmarkClose],
    policy: ShortlistPortfolioPolicy,
    market_dates: list[dt.date] | None = None,
    evidence_scope: str = "all_archived",
) -> ShortlistPortfolioReport:
    """Simulate a capital-constrained, next-open shortlist book.

    The shortlist forms after a completed close. Entries therefore occur only at the next market
    session's open. Planned exits use that market's session index; a suspended name remains open
    until a later bar exists. Gross exposure is marked to completed closes, while sale proceeds are
    unavailable for new entries until the configured settlement delay has elapsed.
    """

    sessions = sorted(set(market_dates or [bar.date for bar in bars]))
    eligible = sorted(
        (item for item in appearances if item.rank in policy.included_ranks),
        key=lambda item: (item.as_of, item.rank, item.code),
    )
    if not sessions or not eligible:
        return ShortlistPortfolioReport(
            policy=policy,
            evidence_scope=evidence_scope,
            start_date=None,
            end_date=None,
            signals_considered=len(eligible),
            entries=0,
            completed_trades=0,
            open_positions=0,
            total_return_pct=0.0,
            benchmark_return_pct=0.0,
            maximum_drawdown_pct=0.0,
            average_gross_exposure_pct=0.0,
            win_rate_pct=None,
            profit_factor=None,
            fees_paid=0.0,
            missing_entry_rejections=0,
            limit_locked_rejections=0,
            capacity_rejections=0,
            slot_rejections=0,
            duplicate_position_rejections=0,
            cash_rejections=0,
            delayed_suspension_exits=0,
            trades=(),
        )

    date_index = {date: index for index, date in enumerate(sessions)}
    bars_by_code: dict[str, dict[dt.date, ShortlistPriceBar]] = defaultdict(dict)
    for bar in bars:
        bars_by_code[bar.code][bar.date] = bar
    benchmark_by_date = {item.date: item.close for item in benchmark if item.close > 0}

    entries_by_date: dict[dt.date, list[ShortlistAppearance]] = defaultdict(list)
    pending_signals = 0
    for appearance in eligible:
        signal_index = date_index.get(appearance.as_of)
        if signal_index is None or signal_index + 1 >= len(sessions):
            pending_signals += 1
            continue
        entries_by_date[sessions[signal_index + 1]].append(appearance)
    for same_day in entries_by_date.values():
        same_day.sort(key=lambda item: (item.rank, item.code))

    if not entries_by_date:
        empty = simulate_shortlist_portfolio(
            appearances=[],
            bars=bars,
            benchmark=benchmark,
            policy=policy,
            market_dates=sessions,
            evidence_scope=evidence_scope,
        )
        return replace(
            empty,
            signals_considered=len(eligible),
            missing_entry_rejections=pending_signals,
        )

    start_date = min(entries_by_date)
    start_index = date_index[start_date]
    end_date = sessions[-1]
    cash = policy.initial_capital
    pending_cash: list[tuple[int, float]] = []
    positions: dict[str, _PortfolioPosition] = {}
    last_prices: dict[str, float] = {}
    completed: list[ShortlistPortfolioTrade] = []
    nav_curve = [policy.initial_capital]
    exposure_curve: list[float] = []
    fees_paid = 0.0
    entries = 0
    missing_entry_rejections = pending_signals
    limit_locked_rejections = 0
    capacity_rejections = 0
    slot_rejections = 0
    duplicate_position_rejections = 0
    cash_rejections = 0
    delayed_suspension_exits = 0

    for session_index in range(start_index, len(sessions)):
        date = sessions[session_index]
        matured = [item for item in pending_cash if item[0] <= session_index]
        cash += sum(value for _, value in matured)
        pending_cash = [item for item in pending_cash if item[0] > session_index]

        opening_positions_value = sum(
            position.shares * last_prices.get(code, position.entry_fill)
            for code, position in positions.items()
        )
        opening_nav = cash + sum(value for _, value in pending_cash) + opening_positions_value

        for appearance in entries_by_date.get(date, []):
            if appearance.code in positions:
                duplicate_position_rejections += 1
                continue
            if len(positions) >= policy.maximum_positions:
                slot_rejections += 1
                continue
            code_bars = bars_by_code.get(appearance.code, {})
            entry_bar = code_bars.get(date)
            selection_bar = code_bars.get(appearance.as_of)
            if entry_bar is None or selection_bar is None or entry_bar.open <= 0:
                missing_entry_rejections += 1
                continue
            if _limit_locked_entry(appearance.close, entry_bar):
                limit_locked_rejections += 1
                continue
            desired_value = opening_nav * policy.target_position_weight
            capacity_value = (
                _trailing_average_traded_value(code_bars, through=appearance.as_of)
                * policy.maximum_adv_participation
            )
            if capacity_value < desired_value * policy.minimum_target_fill:
                capacity_rejections += 1
                continue
            entry_fill = entry_bar.open * (1.0 + policy.slippage_rate)
            budget = min(desired_value, capacity_value, cash)
            shares = int(budget / (entry_fill * (1.0 + policy.fee_rate)))
            if shares <= 0:
                cash_rejections += 1
                continue
            gross = shares * entry_fill
            fee = gross * policy.fee_rate
            cash -= gross + fee
            fees_paid += fee
            signal_index = date_index[appearance.as_of]
            positions[appearance.code] = _PortfolioPosition(
                code=appearance.code,
                rank=appearance.rank,
                evidence_mode=appearance.evidence_mode,
                signal_date=appearance.as_of,
                entry_date=date,
                entry_fill=entry_fill,
                shares=shares,
                planned_exit_index=signal_index + policy.holding_sessions,
            )
            last_prices[appearance.code] = entry_bar.close
            entries += 1

        for code, position in list(positions.items()):
            bar = bars_by_code.get(code, {}).get(date)
            if bar is not None and bar.close > 0:
                last_prices[code] = bar.close
            if session_index < position.planned_exit_index:
                continue
            if bar is None or bar.close <= 0:
                position.exit_was_delayed = True
                continue
            exit_fill = bar.close * (1.0 - policy.slippage_rate)
            gross = position.shares * exit_fill
            fee = gross * policy.fee_rate
            fees_paid += fee
            settlement_index = min(
                session_index + policy.settlement_sessions,
                len(sessions) - 1,
            )
            pending_cash.append((settlement_index, gross - fee))
            net_multiple = (
                exit_fill
                * (1.0 - policy.fee_rate)
                / (position.entry_fill * (1.0 + policy.fee_rate))
            )
            completed.append(
                ShortlistPortfolioTrade(
                    code=code,
                    rank=position.rank,
                    evidence_mode=position.evidence_mode,
                    signal_date=position.signal_date,
                    entry_date=position.entry_date,
                    exit_date=date,
                    entry_fill=round(position.entry_fill, 4),
                    exit_fill=round(exit_fill, 4),
                    shares=position.shares,
                    net_return_pct=round((net_multiple - 1.0) * 100.0, 4),
                )
            )
            if position.exit_was_delayed:
                delayed_suspension_exits += 1
            positions.pop(code)
            last_prices.pop(code, None)

        position_value = sum(
            position.shares * last_prices.get(code, position.entry_fill)
            for code, position in positions.items()
        )
        nav = cash + sum(value for _, value in pending_cash) + position_value
        nav_curve.append(nav)
        exposure_curve.append(position_value / nav if nav > 0 else 0.0)

    final_nav = nav_curve[-1]
    returns = [trade.net_return_pct for trade in completed]
    gains = sum(value for value in returns if value > 0)
    losses = abs(sum(value for value in returns if value <= 0))
    benchmark_return = _benchmark_period_return(
        benchmark_by_date,
        start_date=start_date,
        end_date=end_date,
    )
    return ShortlistPortfolioReport(
        policy=policy,
        evidence_scope=evidence_scope,
        start_date=start_date,
        end_date=end_date,
        signals_considered=len(eligible),
        entries=entries,
        completed_trades=len(completed),
        open_positions=len(positions),
        total_return_pct=round((final_nav / policy.initial_capital - 1.0) * 100.0, 3),
        benchmark_return_pct=round(benchmark_return * 100.0, 3),
        maximum_drawdown_pct=round(_portfolio_drawdown(nav_curve) * 100.0, 3),
        average_gross_exposure_pct=round(
            statistics.fmean(exposure_curve) * 100.0 if exposure_curve else 0.0,
            3,
        ),
        win_rate_pct=(
            round(100.0 * sum(value > 0 for value in returns) / len(returns), 2)
            if returns
            else None
        ),
        profit_factor=round(gains / losses, 3) if losses > 0 else None,
        fees_paid=round(fees_paid, 2),
        missing_entry_rejections=missing_entry_rejections,
        limit_locked_rejections=limit_locked_rejections,
        capacity_rejections=capacity_rejections,
        slot_rejections=slot_rejections,
        duplicate_position_rejections=duplicate_position_rejections,
        cash_rejections=cash_rejections,
        delayed_suspension_exits=delayed_suspension_exits,
        trades=tuple(completed),
    )


def _mean(values: list[float]) -> float | None:
    return statistics.fmean(values) if values else None


def _median(values: list[float]) -> float | None:
    return statistics.median(values) if values else None


def _positive_rate(values: list[float]) -> float | None:
    return 100.0 * sum(value > 0 for value in values) / len(values) if values else None


def _cluster_bootstrap_mean_ci(
    observations: list[_Observation],
    *,
    iterations: int = 1_000,
    seed: int = 29,
) -> tuple[float | None, float | None]:
    """Bootstrap equal-weight selection-date baskets so five same-day names are one cluster."""
    clusters: dict[dt.date, list[float]] = defaultdict(list)
    for observation in observations:
        if observation.excess_return_pct is not None:
            clusters[observation.selection_date].append(observation.excess_return_pct)
    dates = sorted(clusters)
    if len(dates) < 8:
        return None, None

    date_means = {date: statistics.fmean(clusters[date]) for date in dates}
    rng = random.Random(seed)
    means = [
        statistics.fmean(date_means[rng.choice(dates)] for _ in dates) for _ in range(iterations)
    ]
    means.sort()
    return means[int(iterations * 0.025)], means[int(iterations * 0.975) - 1]


def _block_bootstrap_mean_ci(
    values: list[float],
    *,
    block_length: int,
    iterations: int = 2_000,
    seed: int = 29,
) -> tuple[float | None, float | None]:
    """Circular block bootstrap for overlapping forward-return session baskets."""
    if len(values) < max(8, block_length * 2):
        return None, None
    rng = random.Random(seed)
    sample_size = len(values)
    means: list[float] = []
    for _ in range(iterations):
        sample: list[float] = []
        while len(sample) < sample_size:
            start = rng.randrange(sample_size)
            sample.extend(values[(start + offset) % sample_size] for offset in range(block_length))
        means.append(statistics.fmean(sample[:sample_size]))
    means.sort()
    return means[int(iterations * 0.025)], means[int(iterations * 0.975) - 1]


def _limit_locked_entry(selection_close: float, entry: ShortlistPriceBar) -> bool:
    if selection_close <= 0 or entry.open <= 0:
        return False
    gap = entry.open / selection_close - 1.0
    intraday_range = (entry.high - entry.low) / entry.open
    return gap >= 0.075 and intraday_range <= 0.002


def _has_suspicious_jump(
    *,
    code_bars: dict[dt.date, ShortlistPriceBar],
    market_dates: list[dt.date],
    start_index: int,
    end_index: int,
) -> bool:
    previous_close: float | None = None
    if start_index > 0:
        prior = code_bars.get(market_dates[start_index - 1])
        previous_close = prior.close if prior is not None and prior.close > 0 else None
    for date in market_dates[start_index : end_index + 1]:
        bar = code_bars.get(date)
        if bar is None or bar.close <= 0:
            continue
        if (
            previous_close is not None
            and abs(bar.close / previous_close - 1.0) > SUSPICIOUS_CLOSE_JUMP
        ):
            return True
        previous_close = bar.close
    return False


def independent_episodes(
    appearances: list[ShortlistAppearance],
    market_dates: list[dt.date],
    *,
    cooldown_sessions: int = EPISODE_COOLDOWN_SESSIONS,
) -> list[ShortlistAppearance]:
    """Keep the first appearance in each ticker episode; repeats within the cooldown are one idea."""
    date_index = {date: index for index, date in enumerate(market_dates)}
    last_seen: dict[str, int] = {}
    kept: list[ShortlistAppearance] = []
    for appearance in sorted(appearances, key=lambda item: (item.as_of, item.rank, item.code)):
        index = date_index.get(appearance.as_of)
        if index is None:
            continue
        prior_index = last_seen.get(appearance.code)
        if prior_index is None or index - prior_index > cooldown_sessions:
            kept.append(appearance)
        last_seen[appearance.code] = index
    return kept


def eligible_universe_by_date(
    bars: list[ShortlistPriceBar],
    *,
    selection_dates: list[dt.date],
    eligible_codes: set[str],
    min_bars: int = 260,
    min_average_volume: float = 5_000.0,
) -> dict[dt.date, tuple[str, ...]]:
    """Reconstruct the shortlist's liquidity/seasoning universe without future inputs."""
    bars_by_code: dict[str, list[ShortlistPriceBar]] = defaultdict(list)
    for bar in bars:
        if bar.code in eligible_codes:
            bars_by_code[bar.code].append(bar)
    for series in bars_by_code.values():
        series.sort(key=lambda item: item.date)
    dates_by_code = {code: [bar.date for bar in series] for code, series in bars_by_code.items()}

    result: dict[dt.date, tuple[str, ...]] = {}
    for selection_date in sorted(set(selection_dates)):
        eligible: list[str] = []
        for code, series in bars_by_code.items():
            dates = dates_by_code[code]
            end = bisect_right(dates, selection_date)
            if end < min_bars:
                continue
            window = series[end - min_bars : end]
            if not window or window[-1].date != selection_date or window[-1].close <= 0:
                continue
            recent = window[-20:]
            if not recent or statistics.fmean(bar.volume for bar in recent) < min_average_volume:
                continue
            eligible.append(code)
        result[selection_date] = tuple(sorted(eligible))
    return result


def _gross_returns(
    *,
    codes: set[str],
    selection_close_by_code: dict[str, float],
    selection_index: int,
    horizon: int,
    market_dates: list[dt.date],
    bars_by_code: dict[str, dict[dt.date, ShortlistPriceBar]],
) -> tuple[list[float], list[float]]:
    """Return selection-close and next-open gross outcomes for one equal-weight basket."""
    entry_date = market_dates[selection_index + 1]
    target_date = market_dates[selection_index + horizon]
    close_returns: list[float] = []
    next_open_returns: list[float] = []
    for code in codes:
        selection_close = selection_close_by_code.get(code)
        code_bars = bars_by_code.get(code, {})
        target = code_bars.get(target_date)
        if selection_close is None or selection_close <= 0 or target is None or target.close <= 0:
            continue
        if _has_suspicious_jump(
            code_bars=code_bars,
            market_dates=market_dates,
            start_index=selection_index,
            end_index=selection_index + horizon,
        ):
            continue
        close_returns.append((target.close / selection_close - 1.0) * 100.0)

        entry = code_bars.get(entry_date)
        if entry is not None and entry.open > 0 and not _limit_locked_entry(selection_close, entry):
            next_open_returns.append((target.close / entry.open - 1.0) * 100.0)
    return close_returns, next_open_returns


def evaluate_matched_eligible_control(
    *,
    appearances: list[ShortlistAppearance],
    bars: list[ShortlistPriceBar],
    market_dates: list[dt.date],
    eligible_by_date: dict[dt.date, tuple[str, ...]],
) -> MatchedControlReport:
    """Compare each daily slate with the same date's non-selected eligible universe.

    Each date contributes one equal-weight shortlist return and one equal-weight control return.
    This avoids treating five names exposed to one market session as five independent regimes.
    Circular block bootstrap intervals preserve some dependence from overlapping horizons.
    """
    sessions = sorted(set(market_dates))
    date_index = {date: index for index, date in enumerate(sessions)}
    bars_by_code: dict[str, dict[dt.date, ShortlistPriceBar]] = defaultdict(dict)
    for bar in bars:
        bars_by_code[bar.code][bar.date] = bar
    appearances_by_date: dict[dt.date, list[ShortlistAppearance]] = defaultdict(list)
    for appearance in appearances:
        appearances_by_date[appearance.as_of].append(appearance)

    horizon_reports: list[MatchedControlHorizon] = []
    for horizon in HORIZONS:
        shortlist_baskets: list[float] = []
        control_baskets: list[float] = []
        differences: list[float] = []
        shortlist_open_baskets: list[float] = []
        control_open_baskets: list[float] = []
        open_differences: list[float] = []

        for selection_date in sorted(appearances_by_date):
            selection_index = date_index.get(selection_date)
            if selection_index is None or selection_index + horizon >= len(sessions):
                continue
            selected = appearances_by_date[selection_date]
            selected_close = {item.code: item.close for item in selected}
            selected_codes = set(selected_close)
            control_codes = set(eligible_by_date.get(selection_date, ())) - selected_codes
            control_close = {
                code: bar.close
                for code in control_codes
                if (bar := bars_by_code.get(code, {}).get(selection_date)) is not None
                and bar.close > 0
            }

            shortlist_returns, shortlist_open_returns = _gross_returns(
                codes=selected_codes,
                selection_close_by_code=selected_close,
                selection_index=selection_index,
                horizon=horizon,
                market_dates=sessions,
                bars_by_code=bars_by_code,
            )
            control_returns, control_open_returns = _gross_returns(
                codes=control_codes,
                selection_close_by_code=control_close,
                selection_index=selection_index,
                horizon=horizon,
                market_dates=sessions,
                bars_by_code=bars_by_code,
            )
            shortlist_return = _mean(shortlist_returns)
            control_return = _mean(control_returns)
            if shortlist_return is None or control_return is None:
                continue
            shortlist_baskets.append(shortlist_return)
            control_baskets.append(control_return)
            differences.append(shortlist_return - control_return)

            shortlist_open = _mean(shortlist_open_returns)
            control_open = _mean(control_open_returns)
            if shortlist_open is not None and control_open is not None:
                shortlist_open_baskets.append(shortlist_open)
                control_open_baskets.append(control_open)
                open_differences.append(shortlist_open - control_open)

        ci_low, ci_high = _block_bootstrap_mean_ci(
            differences,
            block_length=horizon,
        )
        open_ci_low, open_ci_high = _block_bootstrap_mean_ci(
            open_differences,
            block_length=horizon,
        )
        horizon_reports.append(
            MatchedControlHorizon(
                sessions=horizon,
                selection_sessions=len(differences),
                shortlist_mean_return_pct=_rounded(_mean(shortlist_baskets)),
                control_mean_return_pct=_rounded(_mean(control_baskets)),
                shortlist_minus_control_pct=_rounded(_mean(differences)),
                daily_difference_median_pct=_rounded(_median(differences)),
                shortlist_outperformed_rate_pct=_rounded(
                    _positive_rate(differences),
                    2,
                ),
                difference_ci_low_pct=_rounded(ci_low),
                difference_ci_high_pct=_rounded(ci_high),
                next_open_shortlist_mean_pct=_rounded(_mean(shortlist_open_baskets)),
                next_open_control_mean_pct=_rounded(_mean(control_open_baskets)),
                next_open_difference_pct=_rounded(_mean(open_differences)),
                next_open_ci_low_pct=_rounded(open_ci_low),
                next_open_ci_high_pct=_rounded(open_ci_high),
            )
        )

    return MatchedControlReport(
        control=("Same-date liquid, seasoned, active non-Z universe excluding shortlisted names"),
        selection_sessions=len(appearances_by_date),
        horizons=tuple(horizon_reports),
    )


def _summarize_horizon(
    appearances: list[ShortlistAppearance],
    *,
    horizon: int,
    market_dates: list[dt.date],
    benchmark_by_date: dict[dt.date, float],
    bars_by_code: dict[str, dict[dt.date, ShortlistPriceBar]],
) -> HorizonPerformance:
    date_index = {date: index for index, date in enumerate(market_dates)}
    observations: list[_Observation] = []
    matured = 0
    pending = 0
    missing = 0
    suspicious = 0
    limit_locked = 0

    for appearance in appearances:
        selection_index = date_index.get(appearance.as_of)
        if selection_index is None or selection_index + horizon >= len(market_dates):
            pending += 1
            continue
        target_date = market_dates[selection_index + horizon]
        matured += 1
        code_bars = bars_by_code.get(appearance.code, {})
        target_bar = code_bars.get(target_date)
        if target_bar is None or target_bar.close <= 0 or appearance.close <= 0:
            missing += 1
            continue
        if _has_suspicious_jump(
            code_bars=code_bars,
            market_dates=market_dates,
            start_index=selection_index,
            end_index=selection_index + horizon,
        ):
            suspicious += 1
            continue

        return_pct = (target_bar.close / appearance.close - 1.0) * 100.0
        selection_benchmark = benchmark_by_date.get(appearance.as_of)
        target_benchmark = benchmark_by_date.get(target_date)
        benchmark_return_pct = (
            (target_benchmark / selection_benchmark - 1.0) * 100.0
            if selection_benchmark is not None
            and selection_benchmark > 0
            and target_benchmark is not None
            and target_benchmark > 0
            else None
        )
        entry_date = market_dates[selection_index + 1]
        entry_bar = code_bars.get(entry_date)
        locked = entry_bar is not None and _limit_locked_entry(appearance.close, entry_bar)
        if locked:
            limit_locked += 1
        next_open_return = (
            (target_bar.close / entry_bar.open - 1.0) * 100.0
            if entry_bar is not None and entry_bar.open > 0 and not locked
            else None
        )
        observations.append(
            _Observation(
                selection_date=appearance.as_of,
                return_pct=return_pct,
                benchmark_return_pct=benchmark_return_pct,
                excess_return_pct=(
                    return_pct - benchmark_return_pct if benchmark_return_pct is not None else None
                ),
                next_open_return_pct=next_open_return,
                limit_locked=locked,
            )
        )

    returns = [item.return_pct for item in observations]
    benchmarks = [
        item.benchmark_return_pct for item in observations if item.benchmark_return_pct is not None
    ]
    excess = [item.excess_return_pct for item in observations if item.excess_return_pct is not None]
    next_open = [
        item.next_open_return_pct for item in observations if item.next_open_return_pct is not None
    ]
    ci_low, ci_high = _cluster_bootstrap_mean_ci(observations)
    return HorizonPerformance(
        sessions=horizon,
        matured_appearances=matured,
        observations=len(observations),
        benchmark_observations=len(excess),
        pending_appearances=pending,
        missing_bar_appearances=missing,
        suspicious_price_paths=suspicious,
        coverage_pct=_rounded(100.0 * len(observations) / matured if matured else None, 2),
        mean_return_pct=_rounded(_mean(returns)),
        median_return_pct=_rounded(_median(returns)),
        positive_rate_pct=_rounded(_positive_rate(returns), 2),
        mean_benchmark_return_pct=_rounded(_mean(benchmarks)),
        mean_excess_return_pct=_rounded(_mean(excess)),
        median_excess_return_pct=_rounded(_median(excess)),
        excess_ci_low_pct=_rounded(ci_low),
        excess_ci_high_pct=_rounded(ci_high),
        next_open_observations=len(next_open),
        limit_locked_entries=limit_locked,
        next_open_mean_return_pct=_rounded(_mean(next_open)),
        next_open_median_return_pct=_rounded(_median(next_open)),
        next_open_positive_rate_pct=_rounded(_positive_rate(next_open), 2),
    )


def _cohort(
    key: str,
    appearances: list[ShortlistAppearance],
    *,
    market_dates: list[dt.date],
    benchmark_by_date: dict[dt.date, float],
    bars_by_code: dict[str, dict[dt.date, ShortlistPriceBar]],
) -> PerformanceCohort:
    ordered = sorted(appearances, key=lambda item: (item.as_of, item.rank, item.code))
    return PerformanceCohort(
        key=key,
        appearances=len(ordered),
        selection_sessions=len({item.as_of for item in ordered}),
        first_selection_date=ordered[0].as_of if ordered else None,
        last_selection_date=ordered[-1].as_of if ordered else None,
        horizons=tuple(
            _summarize_horizon(
                ordered,
                horizon=horizon,
                market_dates=market_dates,
                benchmark_by_date=benchmark_by_date,
                bars_by_code=bars_by_code,
            )
            for horizon in HORIZONS
        ),
    )


def evaluate_shortlist_performance(
    *,
    appearances: list[ShortlistAppearance],
    bars: list[ShortlistPriceBar],
    benchmark: list[BenchmarkClose],
    market_dates: list[dt.date] | None = None,
) -> ShortlistPerformanceReport:
    benchmark_by_date = {item.date: item.close for item in benchmark if item.close > 0}
    sessions = sorted(set(market_dates)) if market_dates is not None else sorted(benchmark_by_date)
    bars_by_code: dict[str, dict[dt.date, ShortlistPriceBar]] = defaultdict(dict)
    for bar in bars:
        bars_by_code[bar.code][bar.date] = bar

    episodes = independent_episodes(appearances, sessions)
    forward = [item for item in appearances if item.evidence_mode == "forward"]
    forward_episodes = independent_episodes(forward, sessions)
    cohorts = (
        _cohort(
            "independent_episodes",
            episodes,
            market_dates=sessions,
            benchmark_by_date=benchmark_by_date,
            bars_by_code=bars_by_code,
        ),
        _cohort(
            "all_appearances",
            appearances,
            market_dates=sessions,
            benchmark_by_date=benchmark_by_date,
            bars_by_code=bars_by_code,
        ),
        _cohort(
            "forward_only",
            forward_episodes,
            market_dates=sessions,
            benchmark_by_date=benchmark_by_date,
            bars_by_code=bars_by_code,
        ),
    )
    return ShortlistPerformanceReport(
        as_of=sessions[-1] if sessions else None,
        all_appearances=len(appearances),
        forward_appearances=len(forward),
        reconstructed_appearances=sum(
            item.evidence_mode == "reconstructed" for item in appearances
        ),
        independent_episodes=len(episodes),
        cohorts=cohorts,
    )
