"""Point-in-time quality-universe primitives for DSE strategy research.

Raw exchange coverage is inventory, not an investable universe.  This module applies the durable
company, valuation, history, data-integrity, liquidity, and capacity gates *before* a strategy can
inspect a security.  It has no database access and never substitutes today's company profile for
historical financial knowledge.

The source dataset does not retain annual-report publication timestamps.  The conservative
contract therefore treats only fiscal years no later than ``signal year - 2`` as knowable.  That
costs freshness but prevents a December result from silently appearing in a January backtest.
"""

from __future__ import annotations

import datetime as dt
import statistics
from dataclasses import dataclass
from typing import Literal

from bulls.analytics.dse_edges import EdgeBar, EdgeSignal, ExecutionPolicy

QualityFailure = Literal[
    "insufficient_history",
    "missing_next_session",
    "suspicious_price_gap",
    "insufficient_liquidity",
    "insufficient_capacity",
    "missing_financial_history",
    "not_consistently_profitable",
    "non_positive_book_value",
    "low_roe",
    "expensive_earnings",
    "expensive_book_value",
    "eps_collapse",
    "inconsistent_cash_dividend",
]


@dataclass(frozen=True)
class QualityFinancial:
    fiscal_year: int
    eps: float | None
    nav_per_share: float | None


@dataclass(frozen=True)
class QualityDividend:
    year: int
    cash_pct: float | None


@dataclass(frozen=True)
class QualityUniversePolicy:
    """Predeclared quality and investability thresholds.

    ``minimum_trailing_value`` removes non-tradable noise.  Full target-position capacity is
    reported separately because company quality and portfolio size are different facts.  The
    execution layer may size down or reject an otherwise qualified company.
    """

    minimum_history: int = 126
    liquidity_window: int = 20
    minimum_trailing_value: float = 5_000_000
    require_full_target_capacity: bool = False
    profitable_years: int = 3
    minimum_roe_pct: float = 10.0
    maximum_pe: float = 25.0
    maximum_pb: float = 4.0
    minimum_eps_retention: float = 0.50
    minimum_cash_dividend_years: int = 2
    maximum_close_gap: float = 0.35


@dataclass(frozen=True)
class QualitySnapshot:
    code: str
    signal_date: dt.date
    passes: bool
    failures: tuple[QualityFailure, ...]
    fiscal_year: int | None
    trailing_value: float | None
    required_trailing_value: float
    full_target_capacity: bool
    pe: float | None
    pb: float | None
    roe_pct: float | None
    eps_retention: float | None
    cash_dividend_years: int | None
    sector: str = "Unclassified"


def _recent_gap_is_suspicious(
    bars: list[EdgeBar],
    index: int,
    *,
    maximum_gap: float,
    window: int = 20,
) -> bool:
    start = max(1, index - window + 1)
    for cursor in range(start, index + 1):
        previous = bars[cursor - 1].close
        if previous > 0 and abs(bars[cursor].close / previous - 1) > maximum_gap:
            return True
    return False


def _required_trailing_value(
    *,
    quality_policy: QualityUniversePolicy,
    execution_policy: ExecutionPolicy,
) -> float:
    target_value = execution_policy.assumed_capital * execution_policy.target_position_weight
    capacity_requirement = target_value / execution_policy.maximum_adv_participation
    return max(quality_policy.minimum_trailing_value, capacity_requirement)


def quality_snapshot_at(
    *,
    code: str,
    bars: list[EdgeBar],
    index: int,
    financials: dict[str, list[QualityFinancial]],
    dividends: dict[str, list[QualityDividend]],
    quality_policy: QualityUniversePolicy,
    execution_policy: ExecutionPolicy,
    next_market_date: dt.date | None = None,
    sector: str = "Unclassified",
) -> QualitySnapshot:
    """Evaluate one security using only information knowable at the completed signal close."""

    bars = sorted(bars, key=lambda item: item.date)
    if not 0 <= index < len(bars):
        raise IndexError("quality snapshot index is outside the supplied observation window")
    bar = bars[index]
    failures: list[QualityFailure] = []
    required_trailing_value = _required_trailing_value(
        quality_policy=quality_policy,
        execution_policy=execution_policy,
    )

    if index < quality_policy.minimum_history:
        failures.append("insufficient_history")
    if next_market_date is not None and (
        index + 1 >= len(bars) or bars[index + 1].date != next_market_date
    ):
        failures.append("missing_next_session")
    if _recent_gap_is_suspicious(
        bars,
        index,
        maximum_gap=quality_policy.maximum_close_gap,
    ):
        failures.append("suspicious_price_gap")

    trailing_value: float | None = None
    if index >= quality_policy.liquidity_window:
        trailing_value = statistics.median(
            item.close * item.volume
            for item in bars[index - quality_policy.liquidity_window : index]
        )
    if trailing_value is None or trailing_value < quality_policy.minimum_trailing_value:
        failures.append("insufficient_liquidity")
    full_target_capacity = trailing_value is not None and trailing_value >= required_trailing_value
    if quality_policy.require_full_target_capacity and not full_target_capacity:
        failures.append("insufficient_capacity")

    cutoff = bar.date.year - 2
    known = {
        item.fiscal_year: item for item in financials.get(code, []) if item.fiscal_year <= cutoff
    }
    fiscal_year = max(known) if known else None
    required_years = (
        [fiscal_year - offset for offset in range(quality_policy.profitable_years)]
        if fiscal_year is not None
        else []
    )
    records = [known.get(year) for year in required_years]
    if not records or any(item is None for item in records):
        failures.append("missing_financial_history")

    pe = pb = roe_pct = eps_retention = None
    cash_dividend_years: int | None = None
    if records and all(item is not None for item in records):
        complete_records = [item for item in records if item is not None]
        eps_values = [item.eps for item in complete_records]
        current = complete_records[0]
        if any(eps is None or eps <= 0 for eps in eps_values):
            failures.append("not_consistently_profitable")
        if current.nav_per_share is None or current.nav_per_share <= 0:
            failures.append("non_positive_book_value")
        if (
            all(eps is not None and eps > 0 for eps in eps_values)
            and current.nav_per_share is not None
            and current.nav_per_share > 0
            and bar.close > 0
        ):
            current_eps = float(current.eps)
            prior_average = statistics.fmean(float(eps) for eps in eps_values[1:])
            pe = bar.close / current_eps
            pb = bar.close / current.nav_per_share
            roe_pct = current_eps / current.nav_per_share * 100
            eps_retention = current_eps / prior_average if prior_average > 0 else None
            if roe_pct < quality_policy.minimum_roe_pct:
                failures.append("low_roe")
            if pe > quality_policy.maximum_pe:
                failures.append("expensive_earnings")
            if pb > quality_policy.maximum_pb:
                failures.append("expensive_book_value")
            if eps_retention is None or eps_retention < quality_policy.minimum_eps_retention:
                failures.append("eps_collapse")

        dividend_by_year = {
            item.year: item.cash_pct
            for item in dividends.get(code, [])
            if item.year in required_years
        }
        cash_dividend_years = sum(
            dividend_by_year.get(year) is not None and dividend_by_year[year] > 0
            for year in required_years
        )
        if cash_dividend_years < quality_policy.minimum_cash_dividend_years:
            failures.append("inconsistent_cash_dividend")

    return QualitySnapshot(
        code=code,
        signal_date=bar.date,
        passes=not failures,
        failures=tuple(dict.fromkeys(failures)),
        fiscal_year=fiscal_year,
        trailing_value=trailing_value,
        required_trailing_value=required_trailing_value,
        full_target_capacity=full_target_capacity,
        pe=pe,
        pb=pb,
        roe_pct=roe_pct,
        eps_retention=eps_retention,
        cash_dividend_years=cash_dividend_years,
        sector=sector,
    )


def filter_signals_to_quality_universe(
    *,
    signals: list[EdgeSignal],
    by_code: dict[str, list[EdgeBar]],
    market_closes: dict[dt.date, float],
    financials: dict[str, list[QualityFinancial]],
    dividends: dict[str, list[QualityDividend]],
    quality_policy: QualityUniversePolicy,
    execution_policy: ExecutionPolicy,
    sectors: dict[str, str] | None = None,
) -> tuple[list[EdgeSignal], dict[tuple[str, dt.date], QualitySnapshot]]:
    """Apply the quality gate to an already registered price signal without changing its rule."""

    market_dates = sorted(market_closes)
    next_dates = {date: market_dates[index + 1] for index, date in enumerate(market_dates[:-1])}
    sorted_bars = {code: sorted(bars, key=lambda item: item.date) for code, bars in by_code.items()}
    date_indexes = {
        code: {bar.date: index for index, bar in enumerate(bars)}
        for code, bars in sorted_bars.items()
    }
    selected: list[EdgeSignal] = []
    snapshots: dict[tuple[str, dt.date], QualitySnapshot] = {}
    for signal in signals:
        bars = sorted_bars.get(signal.code)
        index = date_indexes.get(signal.code, {}).get(signal.signal_date)
        if bars is None or index is None:
            continue
        snapshot = quality_snapshot_at(
            code=signal.code,
            bars=bars,
            index=index,
            financials=financials,
            dividends=dividends,
            quality_policy=quality_policy,
            execution_policy=execution_policy,
            next_market_date=next_dates.get(signal.signal_date),
            sector=(sectors or {}).get(signal.code, "Unclassified"),
        )
        snapshots[(signal.code, signal.signal_date)] = snapshot
        if snapshot.passes:
            selected.append(signal)
    return selected, snapshots


def quality_universe_at_date(
    *,
    signal_date: dt.date,
    next_market_date: dt.date,
    by_code: dict[str, list[EdgeBar]],
    financials: dict[str, list[QualityFinancial]],
    dividends: dict[str, list[QualityDividend]],
    quality_policy: QualityUniversePolicy,
    execution_policy: ExecutionPolicy,
    sectors: dict[str, str] | None = None,
) -> dict[str, QualitySnapshot]:
    """Return pass and rejection evidence for the complete supplied security-master universe."""

    result: dict[str, QualitySnapshot] = {}
    for code, unordered in by_code.items():
        bars = sorted(unordered, key=lambda item: item.date)
        index = next(
            (cursor for cursor, bar in enumerate(bars) if bar.date == signal_date),
            None,
        )
        if index is None:
            continue
        result[code] = quality_snapshot_at(
            code=code,
            bars=bars,
            index=index,
            financials=financials,
            dividends=dividends,
            quality_policy=quality_policy,
            execution_policy=execution_policy,
            next_market_date=next_market_date,
            sector=(sectors or {}).get(code, "Unclassified"),
        )
    return result
