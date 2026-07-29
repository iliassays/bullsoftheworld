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
from collections import defaultdict
from dataclasses import dataclass

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
class _Observation:
    selection_date: dt.date
    return_pct: float
    benchmark_return_pct: float | None
    excess_return_pct: float | None
    next_open_return_pct: float | None
    limit_locked: bool


def _rounded(value: float | None, digits: int = 3) -> float | None:
    return round(value, digits) if value is not None else None


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

    date_means = {
        date: statistics.fmean(clusters[date])
        for date in dates
    }
    rng = random.Random(seed)
    means = [
        statistics.fmean(date_means[rng.choice(dates)] for _ in dates)
        for _ in range(iterations)
    ]
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
        if previous_close is not None and abs(bar.close / previous_close - 1.0) > SUSPICIOUS_CLOSE_JUMP:
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
        locked = (
            entry_bar is not None
            and _limit_locked_entry(appearance.close, entry_bar)
        )
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
                    return_pct - benchmark_return_pct
                    if benchmark_return_pct is not None
                    else None
                ),
                next_open_return_pct=next_open_return,
                limit_locked=locked,
            )
        )

    returns = [item.return_pct for item in observations]
    benchmarks = [
        item.benchmark_return_pct
        for item in observations
        if item.benchmark_return_pct is not None
    ]
    excess = [
        item.excess_return_pct
        for item in observations
        if item.excess_return_pct is not None
    ]
    next_open = [
        item.next_open_return_pct
        for item in observations
        if item.next_open_return_pct is not None
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
    benchmark_by_date = {
        item.date: item.close
        for item in benchmark
        if item.close > 0
    }
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
            item.evidence_mode == "reconstructed"
            for item in appearances
        ),
        independent_episodes=len(episodes),
        cohorts=cohorts,
    )
