"""Published-factor reproduction controls for the Atlas US research foundation.

This module implements the daily U.S. momentum construction documented by Kenneth French:
NYSE size and prior-return breakpoints, six size-by-momentum portfolios, value weighting from
lagged market equity, and ``Mom = 1/2(Small High + Big High) - 1/2(Small Low + Big Low)``.

It is a validation control, not an Atlas strategy. A local reproduction should correlate with the
official reference series before factor research built from the same data foundation is trusted.
"""

from __future__ import annotations

import bisect
import datetime as dt
import math
import statistics
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class FactorPricePoint(BaseModel):
    date: dt.date
    adjusted_close: float = Field(gt=0)
    market_equity: float = Field(gt=0)


class FactorSecurityHistory(BaseModel):
    security_id: str = Field(min_length=1)
    exchange: Literal["NYSE", "NASDAQ", "AMEX"]
    points: list[FactorPricePoint]

    @model_validator(mode="after")
    def unique_dates(self) -> FactorSecurityHistory:
        dates = [point.date for point in self.points]
        if len(dates) != len(set(dates)):
            raise ValueError("factor history points must contain unique dates")
        return self


class FactorReturnPoint(BaseModel):
    date: dt.date
    return_decimal: float
    eligible_securities: int
    populated_portfolios: int


class FactorReproductionResult(BaseModel):
    factor_key: Literal["mom_daily_us"]
    methodology: str
    points: list[FactorReturnPoint]
    skipped_sessions: int
    warnings: list[str]


class ReferenceComparison(BaseModel):
    factor_key: str
    overlapping_sessions: int
    correlation: float | None
    mean_local_return_pct: float | None
    mean_reference_return_pct: float | None
    mean_difference_bps: float | None
    tracking_error_annualized_pct: float | None
    sign_agreement_pct: float | None
    passed: bool
    failed_gates: list[str]


def _percentile(values: list[float], probability: float) -> float:
    """Linear percentile with deterministic endpoints."""

    if not values:
        raise ValueError("cannot calculate a percentile of an empty sample")
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] * (1 - fraction) + ordered[upper] * fraction


def _weighted_return(rows: list[tuple[float, float]]) -> float | None:
    gross = sum(weight for weight, _ in rows)
    if gross <= 0:
        return None
    return sum(weight * value for weight, value in rows) / gross


def reproduce_daily_momentum(
    histories: list[FactorSecurityHistory],
) -> FactorReproductionResult:
    """Reproduce the published daily Mom construction from point-in-time security histories.

    Histories must include inactive securities, split/distribution-adjusted closes, and lagged
    market equity. The function refuses partial lookback paths rather than treating missing prices
    as zero returns.
    """

    security_ids = [history.security_id for history in histories]
    if len(security_ids) != len(set(security_ids)):
        raise ValueError("factor histories must contain unique security identifiers")
    by_security: dict[str, dict[dt.date, FactorPricePoint]] = {}
    dates_by_security: dict[str, list[dt.date]] = {}
    for history in histories:
        ordered = sorted(history.points, key=lambda item: item.date)
        by_security[history.security_id] = {point.date: point for point in ordered}
        dates_by_security[history.security_id] = [point.date for point in ordered]
    exchange = {history.security_id: history.exchange for history in histories}
    sessions = sorted({point.date for history in histories for point in history.points})
    output: list[FactorReturnPoint] = []
    skipped = 0
    for index in range(251, len(sessions)):
        date = sessions[index]
        prior_date = sessions[index - 1]
        momentum_recent_date = sessions[index - 21]
        momentum_old_date = sessions[index - 251]
        candidates: list[tuple[str, float, float, float]] = []
        for security_id, points in by_security.items():
            security_dates = dates_by_security[security_id]
            old_position = bisect.bisect_left(security_dates, momentum_old_date)
            recent_position = bisect.bisect_left(security_dates, momentum_recent_date)
            if (
                old_position >= len(security_dates)
                or recent_position >= len(security_dates)
                or security_dates[old_position] != momentum_old_date
                or security_dates[recent_position] != momentum_recent_date
                or recent_position - old_position != 230
                or prior_date not in points
                or date not in points
            ):
                continue
            previous = points[prior_date]
            current = points[date]
            recent = points[momentum_recent_date]
            old = points[momentum_old_date]
            momentum = recent.adjusted_close / old.adjusted_close - 1.0
            daily_return = current.adjusted_close / previous.adjusted_close - 1.0
            candidates.append((security_id, previous.market_equity, momentum, daily_return))
        nyse = [row for row in candidates if exchange[row[0]] == "NYSE"]
        if len(nyse) < 3:
            skipped += 1
            continue
        size_break = statistics.median(row[1] for row in nyse)
        momentum_low = _percentile([row[2] for row in nyse], 0.30)
        momentum_high = _percentile([row[2] for row in nyse], 0.70)
        portfolios: dict[tuple[str, str], list[tuple[float, float]]] = {}
        for _, market_equity, momentum, daily_return in candidates:
            size = "small" if market_equity <= size_break else "big"
            momentum_bucket = (
                "low"
                if momentum <= momentum_low
                else "high"
                if momentum >= momentum_high
                else "neutral"
            )
            portfolios.setdefault((size, momentum_bucket), []).append((market_equity, daily_return))
        required = (
            ("small", "high"),
            ("big", "high"),
            ("small", "low"),
            ("big", "low"),
        )
        returns = {key: _weighted_return(portfolios.get(key, [])) for key in required}
        if any(returns[key] is None for key in required):
            skipped += 1
            continue
        mom = 0.5 * (float(returns[("small", "high")]) + float(returns[("big", "high")])) - 0.5 * (
            float(returns[("small", "low")]) + float(returns[("big", "low")])
        )
        output.append(
            FactorReturnPoint(
                date=date,
                return_decimal=mom,
                eligible_securities=len(candidates),
                populated_portfolios=sum(bool(rows) for rows in portfolios.values()),
            )
        )
    return FactorReproductionResult(
        factor_key="mom_daily_us",
        methodology="Kenneth French daily Mom: NYSE 2x3 breakpoints, lagged-ME value weights",
        points=output,
        skipped_sessions=skipped,
        warnings=[
            "Certification requires inactive/delisted histories and stable security identifiers.",
            "This control is not the investable return of Atlas System C.",
        ],
    )


def compare_to_reference(
    local: FactorReproductionResult,
    reference: dict[dt.date, float],
    *,
    minimum_sessions: int = 252,
    minimum_correlation: float = 0.80,
    maximum_mean_gap_bps: float = 5.0,
) -> ReferenceComparison:
    """Compare local decimal returns with an official decimal-return reference series."""

    local_by_date = {point.date: point.return_decimal for point in local.points}
    dates = sorted(set(local_by_date) & set(reference))
    local_returns = [local_by_date[date] for date in dates]
    reference_returns = [reference[date] for date in dates]
    correlation = (
        statistics.correlation(local_returns, reference_returns)
        if len(dates) >= 2
        and statistics.pstdev(local_returns) > 0
        and statistics.pstdev(reference_returns) > 0
        else None
    )
    differences = [
        local_return - reference_return
        for local_return, reference_return in zip(local_returns, reference_returns, strict=True)
    ]
    mean_gap_bps = statistics.fmean(differences) * 10_000 if differences else None
    tracking_error = (
        statistics.stdev(differences) * math.sqrt(252) * 100 if len(differences) >= 2 else None
    )
    sign_agreement = (
        sum(
            (local_return >= 0) == (reference_return >= 0)
            for local_return, reference_return in zip(local_returns, reference_returns, strict=True)
        )
        / len(dates)
        * 100
        if dates
        else None
    )
    failed_gates: list[str] = []
    if len(dates) < minimum_sessions:
        failed_gates.append(
            f"Only {len(dates)} overlapping sessions; at least {minimum_sessions} are required."
        )
    if correlation is None or correlation < minimum_correlation:
        failed_gates.append(f"Return correlation must be at least {minimum_correlation:.2f}.")
    if mean_gap_bps is None or abs(mean_gap_bps) > maximum_mean_gap_bps:
        failed_gates.append(
            f"Absolute mean return gap must be no greater than {maximum_mean_gap_bps:.1f} bps."
        )
    return ReferenceComparison(
        factor_key=local.factor_key,
        overlapping_sessions=len(dates),
        correlation=round(correlation, 6) if correlation is not None else None,
        mean_local_return_pct=(
            round(statistics.fmean(local_returns) * 100, 6) if local_returns else None
        ),
        mean_reference_return_pct=(
            round(statistics.fmean(reference_returns) * 100, 6) if reference_returns else None
        ),
        mean_difference_bps=round(mean_gap_bps, 6) if mean_gap_bps is not None else None,
        tracking_error_annualized_pct=(
            round(tracking_error, 6) if tracking_error is not None else None
        ),
        sign_agreement_pct=round(sign_agreement, 3) if sign_agreement is not None else None,
        passed=not failed_gates,
        failed_gates=failed_gates,
    )


def parse_french_daily_momentum_csv(payload: str) -> dict[dt.date, float]:
    """Parse a Kenneth French daily Mom CSV payload into decimal returns.

    Header, notes, annual summaries, and documented missing-value sentinels are ignored.
    """

    parsed: dict[dt.date, float] = {}
    for raw_line in payload.splitlines():
        columns = [column.strip() for column in raw_line.split(",")]
        if len(columns) < 2 or len(columns[0]) != 8 or not columns[0].isdigit():
            continue
        try:
            value_pct = float(columns[1])
            date = dt.datetime.strptime(columns[0], "%Y%m%d").date()
        except ValueError:
            continue
        if value_pct <= -99.0:
            continue
        parsed[date] = value_pct / 100.0
    return parsed
