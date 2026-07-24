"""Independent controls for the Atlas portfolio engine and research data inputs.

These checks do not certify a strategy's alpha. They establish that deterministic portfolio
accounting produces known answers and that a research dataset carries the minimum evidence needed
before a result can be considered for promotion.
"""

from __future__ import annotations

import datetime as dt
from collections import Counter
from typing import Any, Literal

from pydantic import BaseModel, Field

from bulls.analytics.research_strategy import (
    ENGINE_VERSION,
    BenchmarkPoint,
    BenchmarkSeries,
    PortfolioRiskPolicy,
    StrategyBar,
    StrategySecurity,
    run_backtest,
)


class CertificationCheck(BaseModel):
    key: str
    category: Literal["engine", "data"]
    passed: bool
    critical: bool = True
    actual: Any
    requirement: str


class CertificationReport(BaseModel):
    subject: str
    version: str
    passed: bool
    checks: list[CertificationCheck]


class DataFoundationAttestation(BaseModel):
    """Claims that must be backed by a dated dataset manifest or audit artifact."""

    evidence_reference: str = Field(min_length=1)
    inactive_and_delisted_history_complete: bool = False
    historical_universe_membership_complete: bool = False
    point_in_time_fundamentals_complete: bool = False
    corporate_action_adjustments_complete: bool = False
    stable_security_identifiers_complete: bool = False


def _bar(date: dt.date, price: float, *, volume: int = 1_000_000) -> StrategyBar:
    return StrategyBar(
        date=date,
        open=price,
        high=price,
        low=price,
        close=price,
        volume=volume,
    )


def _security(code: str, prices: list[float]) -> StrategySecurity:
    start = dt.date(2025, 1, 6)
    return StrategySecurity(
        code=code,
        sector="Certification",
        cap_tier="test",
        bars=[_bar(start + dt.timedelta(days=index), price) for index, price in enumerate(prices)],
    )


def _benchmark(prices: list[float]) -> BenchmarkSeries:
    start = dt.date(2025, 1, 6)
    return BenchmarkSeries(
        key="certification_control",
        label="Certification control series",
        points=[
            BenchmarkPoint(
                date=start + dt.timedelta(days=index),
                close=price,
            )
            for index, price in enumerate(prices)
        ],
    )


def _policy(*, fee_rate: float = 0.0) -> PortfolioRiskPolicy:
    return PortfolioRiskPolicy(
        market="US",
        minimum_average_daily_value_mn=0.0,
        max_adv_participation=1.0,
        max_position_weight=1.0,
        max_sector_weight=1.0,
        max_gross_exposure=1.0,
        target_annualized_volatility=1.0,
        position_stop_loss=0.99,
        portfolio_drawdown_brake=0.99,
        fee_rate=fee_rate,
        slippage_rate=0.0,
    )


def run_engine_certification() -> CertificationReport:
    """Run deterministic known-answer cases against the production accounting engine."""

    checks: list[CertificationCheck] = []
    dates = [point.date for point in _benchmark([100.0, 100.0, 110.0]).points]

    exact = run_backtest(
        market="US",
        strategy_key="us_factor_sleeve_v1",
        securities=[_security("KNOWN", [10.0, 10.0, 12.0])],
        initial_capital=1_000.0,
        risk_policy=_policy(),
        weight_schedule={dates[0]: {"KNOWN": 0.5}},
        execution_timing="next_close",
        half_spread_bps=0.0,
        benchmark_series=_benchmark([100.0, 100.0, 110.0]),
    )
    checks.extend(
        [
            CertificationCheck(
                key="next_session_execution",
                category="engine",
                passed=bool(exact.trades) and exact.trades[0].date == dates[1],
                actual=str(exact.trades[0].date) if exact.trades else None,
                requirement=f"A target decided on {dates[0]} must not fill before {dates[1]}.",
            ),
            CertificationCheck(
                key="known_answer_nav",
                category="engine",
                passed=exact.final_nav == 1_100.0,
                actual=exact.final_nav,
                requirement="A 50% position rising from 10 to 12 with zero costs ends at 1,100.",
            ),
            CertificationCheck(
                key="independent_benchmark",
                category="engine",
                passed=exact.benchmark_valid and exact.benchmark_final == 1_100.0,
                actual={
                    "final": exact.benchmark_final,
                    "key": exact.benchmark_key,
                    "valid": exact.benchmark_valid,
                },
                requirement="The explicit 100-to-110 control series compounds independently to 1,100.",
            ),
        ]
    )

    costed = run_backtest(
        market="US",
        strategy_key="us_factor_sleeve_v1",
        securities=[_security("COST", [10.0, 10.0, 10.0])],
        initial_capital=1_000.0,
        risk_policy=_policy(fee_rate=0.01),
        weight_schedule={dates[0]: {"COST": 0.5}},
        execution_timing="next_close",
        half_spread_bps=100.0,
        benchmark_series=_benchmark([100.0, 100.0, 100.0]),
    )
    expected_fee = 5.05
    expected_nav = 989.95
    checks.append(
        CertificationCheck(
            key="cost_accounting",
            category="engine",
            passed=(
                costed.fees_paid == expected_fee
                and costed.final_nav == expected_nav
                and costed.trades[0].fill_price == 10.1
            ),
            actual={
                "fee": costed.fees_paid,
                "fill": costed.trades[0].fill_price,
                "nav": costed.final_nav,
            },
            requirement=(
                "A 50-share buy at 10 with 100 bps half-spread and 1% fee must fill at "
                "10.10, charge 5.05, and mark to 989.95."
            ),
        )
    )

    funded = run_backtest(
        market="US",
        strategy_key="us_factor_sleeve_v1",
        securities=[
            _security("A_BUY", [10.0, 10.0, 10.0, 10.0]),
            _security("Z_SELL", [10.0, 10.0, 10.0, 10.0]),
        ],
        initial_capital=1_000.0,
        risk_policy=_policy(),
        weight_schedule={
            dates[0]: {"Z_SELL": 1.0},
            dates[1]: {"A_BUY": 1.0},
        },
        execution_timing="next_close",
        half_spread_bps=0.0,
        benchmark_series=_benchmark([100.0, 100.0, 100.0, 100.0]),
    )
    switch_trades = [trade for trade in funded.trades if trade.date == dates[2]]
    checks.append(
        CertificationCheck(
            key="sell_before_buy_funding",
            category="engine",
            passed=(
                [trade.side for trade in switch_trades] == ["sell", "buy"]
                and [trade.code for trade in switch_trades] == ["Z_SELL", "A_BUY"]
                and not any(
                    item.rule == "cash_limit" and item.date == dates[2]
                    for item in funded.risk_interventions
                )
            ),
            actual=[
                {"side": trade.side, "code": trade.code, "quantity": trade.quantity}
                for trade in switch_trades
            ],
            requirement="Position reductions must settle before replacement buys are funded.",
        )
    )

    implicit = run_backtest(
        market="US",
        strategy_key="us_factor_sleeve_v1",
        securities=[_security("IMPLICIT", [10.0, 10.0, 10.0])],
        risk_policy=_policy(),
        weight_schedule={},
    )
    checks.append(
        CertificationCheck(
            key="implicit_benchmark_blocks_promotion",
            category="engine",
            passed=not implicit.benchmark_valid
            and implicit.validation_status == "diagnostic"
            and any(
                "explicit independent market benchmark" in gate for gate in implicit.failed_gates
            ),
            actual={
                "method": implicit.benchmark_method,
                "valid": implicit.benchmark_valid,
                "status": implicit.validation_status,
            },
            requirement="A current-universe baseline cannot qualify as an independent benchmark.",
        )
    )

    return CertificationReport(
        subject="Atlas portfolio engine known-answer certification",
        version=ENGINE_VERSION,
        passed=all(check.passed for check in checks if check.critical),
        checks=checks,
    )


def certify_data_foundation(
    *,
    securities: list[StrategySecurity],
    benchmark: BenchmarkSeries | None,
    attestation: DataFoundationAttestation,
) -> CertificationReport:
    """Evaluate structural data integrity and evidence-backed point-in-time readiness."""

    checks: list[CertificationCheck] = []
    codes = [security.code for security in securities]
    duplicate_codes = sorted(code for code, count in Counter(codes).items() if count > 1)
    checks.append(
        CertificationCheck(
            key="unique_security_series",
            category="data",
            passed=not duplicate_codes,
            actual=duplicate_codes,
            requirement="Each stable security identifier appears once in the test universe.",
        )
    )

    duplicate_dates: dict[str, list[str]] = {}
    invalid_ohlc: dict[str, list[str]] = {}
    sessions: set[dt.date] = set()
    for security in securities:
        seen: set[dt.date] = set()
        for bar in security.bars:
            sessions.add(bar.date)
            if bar.date in seen:
                duplicate_dates.setdefault(security.code, []).append(str(bar.date))
            seen.add(bar.date)
            if bar.high < max(bar.open, bar.close, bar.low) or bar.low > min(
                bar.open, bar.close, bar.high
            ):
                invalid_ohlc.setdefault(security.code, []).append(str(bar.date))
    checks.extend(
        [
            CertificationCheck(
                key="unique_bar_keys",
                category="data",
                passed=not duplicate_dates,
                actual=duplicate_dates,
                requirement="A security can have at most one completed bar per session.",
            ),
            CertificationCheck(
                key="ohlc_integrity",
                category="data",
                passed=not invalid_ohlc,
                actual=invalid_ohlc,
                requirement="Every high/low must contain its open and close.",
            ),
        ]
    )

    benchmark_dates = {point.date for point in benchmark.points} if benchmark is not None else set()
    coverage = len(sessions & benchmark_dates) / len(sessions) * 100 if sessions else 0.0
    benchmark_ok = (
        benchmark is not None
        and bool(sessions)
        and coverage >= 98.0
        and min(sessions) in benchmark_dates
        and max(sessions) in benchmark_dates
    )
    checks.append(
        CertificationCheck(
            key="independent_benchmark_coverage",
            category="data",
            passed=benchmark_ok,
            actual={
                "key": benchmark.key if benchmark is not None else None,
                "coverage_pct": round(coverage, 3),
            },
            requirement="An explicit benchmark covers at least 98% plus both boundary sessions.",
        )
    )

    attestations = (
        (
            "inactive_and_delisted_history",
            attestation.inactive_and_delisted_history_complete,
            "Inactive, acquired, and delisted histories are included for the evaluation window.",
        ),
        (
            "historical_universe_membership",
            attestation.historical_universe_membership_complete,
            "Universe eligibility is reconstructed as of each historical decision date.",
        ),
        (
            "point_in_time_fundamentals",
            attestation.point_in_time_fundamentals_complete,
            "Fundamentals and revisions are available only from their publication timestamps.",
        ),
        (
            "corporate_action_adjustments",
            attestation.corporate_action_adjustments_complete,
            "Price histories have audited split and distribution adjustments.",
        ),
        (
            "stable_security_identifiers",
            attestation.stable_security_identifiers_complete,
            "Ticker changes and reused symbols resolve to stable security identities.",
        ),
    )
    for key, value, requirement in attestations:
        checks.append(
            CertificationCheck(
                key=key,
                category="data",
                passed=value,
                actual={
                    "attested": value,
                    "evidence_reference": attestation.evidence_reference,
                },
                requirement=requirement,
            )
        )

    return CertificationReport(
        subject="Atlas research data-foundation certification",
        version=attestation.evidence_reference,
        passed=all(check.passed for check in checks if check.critical),
        checks=checks,
    )
