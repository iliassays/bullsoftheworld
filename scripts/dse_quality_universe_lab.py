"""Audit the Atlas DSE quality universe before testing strategies inside it.

This command is read-only.  It does not create a signal, target, shadow book, or database row.

    uv run python scripts/dse_quality_universe_lab.py
"""

from __future__ import annotations

import asyncio
import datetime as dt
from collections import Counter, defaultdict

from sqlalchemy import select, text

from bulls.analytics.dse_edge_backtest import (
    evaluate_signals,
    promotion_decision,
    simulate_portfolio,
    split_outcomes,
    summarize_outcomes,
)
from bulls.analytics.dse_edges import SPECS, EdgeBar, ExecutionPolicy, generate_signals
from bulls.analytics.dse_quality_portfolio import (
    QualityPortfolioPolicy,
    build_quality_rebalances,
    simulate_quality_portfolio,
)
from bulls.analytics.dse_quality_universe import (
    QualityDividend,
    QualityFinancial,
    QualityUniversePolicy,
    filter_signals_to_quality_universe,
    quality_universe_at_date,
)
from bulls.core.db import get_sessionmaker
from bulls.core.models import (
    AnnualFinancial,
    CompanyProfile,
    DailyBar,
    DividendRecord,
    MarketSummary,
    Symbol,
)

TRAIN_END = dt.date(2025, 7, 1)
VALIDATION_END = dt.date(2026, 1, 1)
BASE_EXECUTION = ExecutionPolicy(
    assumed_capital=10_000_000,
    target_position_weight=0.085,
)
STRESSED_EXECUTION = ExecutionPolicy(
    assumed_capital=10_000_000,
    target_position_weight=0.085,
    slippage_rate=0.0075,
)
QUALITY_POLICY = QualityUniversePolicy()
PORTFOLIO_POLICY = QualityPortfolioPolicy()
CAPACITY_AWARE_PORTFOLIO_POLICY = QualityPortfolioPolicy(
    target_positions=20,
    minimum_positions=10,
    gross_target_weight=0.85,
    capacity_aware_targets=True,
    maximum_position_weight=0.10,
    maximum_sector_weight=0.25,
)


async def _load():
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        await session.execute(text("SET LOCAL statement_timeout = '5min'"))
        eligible_rows = (
            await session.execute(
                select(Symbol.code, Symbol.sector)
                .join(
                    CompanyProfile,
                    (CompanyProfile.market == Symbol.market) & (CompanyProfile.code == Symbol.code),
                )
                .where(
                    Symbol.market == "DSE",
                    Symbol.is_active.is_(True),
                    Symbol.is_hidden.is_(False),
                    Symbol.data_status == "ready",
                    Symbol.research_status.in_(("ready", "partial")),
                    Symbol.category != "Z",
                    CompanyProfile.instrument_type == "Equity",
                )
            )
        ).all()
        eligible_codes = {code for code, _sector in eligible_rows}
        sectors = {code: sector or "Unclassified" for code, sector in eligible_rows}
        bars = list(
            await session.scalars(
                select(DailyBar)
                .where(DailyBar.market == "DSE", DailyBar.code.in_(eligible_codes))
                .order_by(DailyBar.code, DailyBar.date)
            )
        )
        market_rows = list(
            await session.scalars(
                select(MarketSummary)
                .where(MarketSummary.market == "DSE", MarketSummary.dsex.is_not(None))
                .order_by(MarketSummary.date)
            )
        )
        financial_rows = list(
            await session.scalars(
                select(AnnualFinancial).where(
                    AnnualFinancial.market == "DSE",
                    AnnualFinancial.code.in_(eligible_codes),
                )
            )
        )
        dividend_rows = list(
            await session.scalars(
                select(DividendRecord).where(
                    DividendRecord.market == "DSE",
                    DividendRecord.code.in_(eligible_codes),
                )
            )
        )

    by_code: dict[str, list[EdgeBar]] = defaultdict(list)
    for bar in bars:
        by_code[bar.code].append(
            EdgeBar(
                date=bar.date,
                open=bar.open,
                high=bar.high,
                low=bar.low,
                close=bar.close,
                volume=bar.volume,
            )
        )
    financials: dict[str, list[QualityFinancial]] = defaultdict(list)
    for item in financial_rows:
        financials[item.code].append(
            QualityFinancial(
                fiscal_year=item.fiscal_year,
                eps=item.eps,
                nav_per_share=item.nav_per_share,
            )
        )
    dividends: dict[str, list[QualityDividend]] = defaultdict(list)
    for item in dividend_rows:
        dividends[item.code].append(QualityDividend(year=item.year, cash_pct=item.cash_pct))
    market_closes = {item.date: item.dsex for item in market_rows if item.dsex}
    return dict(by_code), market_closes, dict(financials), dict(dividends), sectors


def _cell(value: float | None) -> str:
    return "n/a" if value is None else f"{value:+.2f}%"


def _print_outcomes(label: str, outcomes) -> None:
    summary = summarize_outcomes(outcomes)
    print(
        f"    {label:<10} n={summary.observations:>3} "
        f"mean/median={_cell(summary.mean_return_pct)}/{_cell(summary.median_return_pct)} "
        f"excess={_cell(summary.mean_excess_return_pct)} PF={summary.profit_factor or 0:.2f}"
    )


def _print_event_book(label: str, book) -> None:
    print(
        f"    {label:<10} {book.total_return_pct:+.2f}% vs DSEX "
        f"{book.benchmark_return_pct:+.2f}% (excess {book.excess_return_pct:+.2f}%), "
        f"maxDD {book.maximum_drawdown_pct:.2f}%, trades {book.trades}"
    )


def _print_target_book(label: str, book) -> None:
    print(
        f"    {label:<10} {book.total_return_pct:+.2f}% vs 85% DSEX/cash "
        f"{book.cash_adjusted_benchmark_return_pct:+.2f}% "
        f"(excess {book.cash_adjusted_excess_return_pct:+.2f}%; full DSEX "
        f"{book.benchmark_return_pct:+.2f}%), "
        f"maxDD {book.maximum_drawdown_pct:.2f}%, avg/end gross "
        f"{book.average_gross_exposure_pct:.1f}%/{book.ending_gross_exposure_pct:.1f}%, "
        f"buys/sells {book.buys}/{book.sells}, capacity shortfalls "
        f"{book.capacity_shortfalls}, fees BDT {book.fees_paid:,.0f}"
    )


async def _run() -> None:
    by_code, market_closes, financials, dividends, sectors = await _load()
    dates = sorted(market_closes)
    print(
        "ATLAS DSE QUALITY-UNIVERSE LAB — READ ONLY\n"
        f"Security-master input: {len(by_code)} current active, research-ready/partial, non-Z "
        f"equities; DSEX calendar {dates[0]} to {dates[-1]}.\n"
        "Gate is applied before strategy logic: 126 observations; BDT 5m trailing traded value; "
        "three consecutive profitable known FYs; positive NAV; "
        "ROE >=10%; P/E <=25; P/B <=4; EPS retention >=50%; cash dividends in >=2/3 FYs.\n"
        "Known fundamentals use FY <= signal year - 2 because publication timestamps are absent. "
        "Full 8.5% capacity at 2% participation is a separate portfolio constraint.\n"
    )

    rebalances = build_quality_rebalances(
        by_code=by_code,
        market_closes=market_closes,
        financials=financials,
        dividends=dividends,
        quality_policy=QUALITY_POLICY,
        execution_policy=BASE_EXECUTION,
        portfolio_policy=PORTFOLIO_POLICY,
        sectors=sectors,
    )
    print("QUALITY FUNNEL BY PREDECLARED QUARTERLY REVIEW")
    failure_counts: Counter[str] = Counter()
    observations = 0
    for rebalance in rebalances:
        audit = quality_universe_at_date(
            signal_date=rebalance.signal_date,
            next_market_date=rebalance.execution_date,
            by_code=by_code,
            financials=financials,
            dividends=dividends,
            quality_policy=QUALITY_POLICY,
            execution_policy=BASE_EXECUTION,
            sectors=sectors,
        )
        observations += len(audit)
        failure_counts.update(reason for item in audit.values() for reason in item.failures)
        full_size_count = sum(item.full_target_capacity for item in audit.values() if item.passes)
        print(
            f"  {rebalance.signal_date}: observed {len(audit):>3} -> quality+tradability "
            f"{rebalance.eligible_count:>2} -> full-size capable {full_size_count:>2} -> "
            f"targets {len(rebalance.targets):>2} "
            f"[{', '.join(rebalance.targets) if rebalance.targets else 'ABSTAIN'}]"
        )
    print(f"  Aggregate audit observations: {observations} (a company can fail multiple gates)")
    for reason, count in failure_counts.most_common():
        print(f"    {reason:<30} {count:>4}")

    print("\nEXPERIMENT 1 — REGISTERED DEEP RECLAIM, QUALITY UNIVERSE ONLY")
    spec = SPECS["deep_reclaim"]
    broad_signals = generate_signals(
        by_code=by_code,
        market_closes=market_closes,
        spec=spec,
        policy=BASE_EXECUTION,
    )
    quality_signals, signal_audit = filter_signals_to_quality_universe(
        signals=broad_signals,
        by_code=by_code,
        market_closes=market_closes,
        financials=financials,
        dividends=dividends,
        quality_policy=QUALITY_POLICY,
        execution_policy=BASE_EXECUTION,
        sectors=sectors,
    )
    broad_outcomes = evaluate_signals(
        signals=broad_signals,
        by_code=by_code,
        market_closes=market_closes,
        spec=spec,
        policy=BASE_EXECUTION,
    )
    quality_outcomes = evaluate_signals(
        signals=quality_signals,
        by_code=by_code,
        market_closes=market_closes,
        spec=spec,
        policy=BASE_EXECUTION,
    )
    stressed_outcomes = evaluate_signals(
        signals=quality_signals,
        by_code=by_code,
        market_closes=market_closes,
        spec=spec,
        policy=STRESSED_EXECUTION,
    )
    print(
        f"  Raw price signals {len(broad_signals)}; passed quality gate {len(quality_signals)}; "
        f"executable quality outcomes {len(quality_outcomes)}."
    )
    rejected_signal_reasons = Counter(
        reason for item in signal_audit.values() if not item.passes for reason in item.failures
    )
    for reason, count in rejected_signal_reasons.most_common():
        print(f"    rejected by {reason:<26} {count:>3}")
    quality_parts = split_outcomes(
        quality_outcomes,
        train_end=TRAIN_END,
        validation_end=VALIDATION_END,
    )
    stressed_parts = split_outcomes(
        stressed_outcomes,
        train_end=TRAIN_END,
        validation_end=VALIDATION_END,
    )
    print("  Outcome distribution (quality-gated):")
    for label in ("train", "validation", "test"):
        _print_outcomes(label, quality_parts[label])
    decision = promotion_decision(
        base_splits={label: summarize_outcomes(items) for label, items in quality_parts.items()},
        stressed_splits={
            label: summarize_outcomes(items) for label, items in stressed_parts.items()
        },
    )
    broad_book = simulate_portfolio(
        signals=broad_signals,
        valid_outcomes=broad_outcomes,
        by_code=by_code,
        market_closes=market_closes,
        spec=spec,
        policy=BASE_EXECUTION,
    )
    quality_book = simulate_portfolio(
        signals=quality_signals,
        valid_outcomes=quality_outcomes,
        by_code=by_code,
        market_closes=market_closes,
        spec=spec,
        policy=BASE_EXECUTION,
    )
    print("  Portfolio comparison:")
    _print_event_book("broad", broad_book)
    _print_event_book("quality", quality_book)
    for label in ("validation", "test"):
        _print_event_book(
            label,
            simulate_portfolio(
                signals=quality_signals,
                valid_outcomes=quality_parts[label],
                by_code=by_code,
                market_closes=market_closes,
                spec=spec,
                policy=BASE_EXECUTION,
            ),
        )
    print(
        "  Admission: "
        + ("eligible for forward paper" if decision.eligible_for_forward_paper else "REJECT")
    )
    for failure in decision.failed_gates:
        print(f"    - {failure}")

    print("\nEXPERIMENT 2 — QUARTERLY QUALITY AT A REASONABLE PRICE TARGET BOOK")
    print(
        "  Top 10 inside the quality universe; 85% gross; quarterly review; next-open target "
        "changes; no swing stop/target; 0.40% fees; 0.25% slippage; T+2 sell cash."
    )
    full_book = simulate_quality_portfolio(
        rebalances=rebalances,
        by_code=by_code,
        market_closes=market_closes,
        execution_policy=BASE_EXECUTION,
        portfolio_policy=PORTFOLIO_POLICY,
    )
    stressed_book = simulate_quality_portfolio(
        rebalances=rebalances,
        by_code=by_code,
        market_closes=market_closes,
        execution_policy=STRESSED_EXECUTION,
        portfolio_policy=PORTFOLIO_POLICY,
    )
    _print_target_book("full", full_book)
    _print_target_book("stress", stressed_book)
    for label, start, end in (
        ("train", None, TRAIN_END),
        ("validation", TRAIN_END, VALIDATION_END),
        ("test", VALIDATION_END, None),
    ):
        _print_target_book(
            label,
            simulate_quality_portfolio(
                rebalances=rebalances,
                by_code=by_code,
                market_closes=market_closes,
                execution_policy=BASE_EXECUTION,
                portfolio_policy=PORTFOLIO_POLICY,
                signal_start=start,
                signal_end=end,
            ),
        )

    print("\nEXPERIMENT 3 — CAPACITY- AND SECTOR-AWARE DSE QUALITY CORE")
    print(
        "  Same frozen quality/value evidence; up to 20 names; 10% name cap; 25% sector cap; "
        "weights cannot exceed one-session 2% trailing-value capacity; batched settled-cash buys."
    )
    capacity_rebalances = build_quality_rebalances(
        by_code=by_code,
        market_closes=market_closes,
        financials=financials,
        dividends=dividends,
        quality_policy=QUALITY_POLICY,
        execution_policy=BASE_EXECUTION,
        portfolio_policy=CAPACITY_AWARE_PORTFOLIO_POLICY,
        sectors=sectors,
    )
    for rebalance in capacity_rebalances:
        target_gross = sum(weight for _code, weight in rebalance.target_weights) * 100
        print(
            f"  {rebalance.signal_date}: eligible {rebalance.eligible_count:>2}, "
            f"targets {len(rebalance.targets):>2}, feasible gross {target_gross:>5.1f}%"
        )
    capacity_full = simulate_quality_portfolio(
        rebalances=capacity_rebalances,
        by_code=by_code,
        market_closes=market_closes,
        execution_policy=BASE_EXECUTION,
        portfolio_policy=CAPACITY_AWARE_PORTFOLIO_POLICY,
    )
    capacity_stress = simulate_quality_portfolio(
        rebalances=capacity_rebalances,
        by_code=by_code,
        market_closes=market_closes,
        execution_policy=STRESSED_EXECUTION,
        portfolio_policy=CAPACITY_AWARE_PORTFOLIO_POLICY,
    )
    _print_target_book("full", capacity_full)
    _print_target_book("stress", capacity_stress)
    for label, start, end in (
        ("train", None, TRAIN_END),
        ("validation", TRAIN_END, VALIDATION_END),
        ("test", VALIDATION_END, None),
    ):
        _print_target_book(
            label,
            simulate_quality_portfolio(
                rebalances=capacity_rebalances,
                by_code=by_code,
                market_closes=market_closes,
                execution_policy=BASE_EXECUTION,
                portfolio_policy=CAPACITY_AWARE_PORTFOLIO_POLICY,
                signal_start=start,
                signal_end=end,
            ),
        )

    print(
        "\nRESEARCH BOUNDARY: current-security-master survivorship remains; annual-report "
        "publication timestamps and adjusted closes are absent; inactive/delisted coverage is "
        "incomplete; dividend income is not credited because ex/payment dates are unavailable; "
        "and two years is too short for admission. Results are diagnostic, never live authority."
    )


if __name__ == "__main__":
    asyncio.run(_run())
