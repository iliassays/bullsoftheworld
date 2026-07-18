"""Run pre-registered daily DSE factor candidates without writing or activating a strategy."""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
from collections import defaultdict

from sqlalchemy import select, text

from bulls.analytics.dse_daily_factors import (
    FACTOR_SPECS,
    DividendPoint,
    FundamentalRecord,
    generate_factor_signals,
)
from bulls.analytics.dse_edge_backtest import (
    evaluate_signals,
    promotion_decision,
    simulate_portfolio,
    split_outcomes,
    summarize_outcomes,
)
from bulls.analytics.dse_edges import EdgeBar, ExecutionPolicy
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
BASE_POLICY = ExecutionPolicy(
    assumed_capital=10_000_000,
    target_position_weight=0.085,
)
STRESSED_POLICY = ExecutionPolicy(
    assumed_capital=10_000_000,
    target_position_weight=0.085,
    slippage_rate=0.0075,
)


async def _load(*, include_z: bool):
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        await session.execute(text("SET LOCAL statement_timeout = '5min'"))
        eligibility = [
            Symbol.market == "DSE",
            Symbol.is_active.is_(True),
            Symbol.is_hidden.is_(False),
            Symbol.data_status == "ready",
            CompanyProfile.instrument_type == "Equity",
        ]
        if not include_z:
            eligibility.append(Symbol.category != "Z")
        eligible_codes = set(
            await session.scalars(
                select(Symbol.code)
                .join(
                    CompanyProfile,
                    (CompanyProfile.market == Symbol.market)
                    & (CompanyProfile.code == Symbol.code),
                )
                .where(*eligibility)
            )
        )
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
    financials: dict[str, list[FundamentalRecord]] = defaultdict(list)
    for row in financial_rows:
        financials[row.code].append(
            FundamentalRecord(
                fiscal_year=row.fiscal_year,
                eps=row.eps,
                nav_per_share=row.nav_per_share,
            )
        )
    dividends: dict[str, list[DividendPoint]] = defaultdict(list)
    for row in dividend_rows:
        dividends[row.code].append(DividendPoint(year=row.year, cash_pct=row.cash_pct))
    market_closes = {row.date: row.dsex for row in market_rows if row.dsex}
    return dict(by_code), market_closes, dict(financials), dict(dividends)


def _cell(value: float | None) -> str:
    return "n/a" if value is None else f"{value:+.2f}%"


def _print_summary(label: str, summary) -> None:
    ci = (
        "n/a"
        if summary.mean_excess_ci_low_pct is None
        else f"[{summary.mean_excess_ci_low_pct:+.2f}, {summary.mean_excess_ci_high_pct:+.2f}]"
    )
    print(
        f"  {label:<11} n={summary.observations:>3} "
        f"net mean/median={_cell(summary.mean_return_pct)}/{_cell(summary.median_return_pct)} "
        f"win={_cell(summary.win_rate_pct)} PF={summary.profit_factor or 0:.2f} "
        f"excess={_cell(summary.mean_excess_return_pct)} CI95={ci}"
    )


async def _run(*, include_z: bool) -> None:
    by_code, market_closes, financials, dividends = await _load(include_z=include_z)
    first_date = min(bar.date for bars in by_code.values() for bar in bars)
    last_date = max(bar.date for bars in by_code.values() for bar in bars)
    print(
        f"DSE daily factor lab: {len(by_code)} active "
        f"{'all-category' if include_z else 'non-Z'} equities, {first_date} to {last_date}\n"
        "Sparse instruments require 126 observations, an immediate next-session bar, and BDT 5m "
        "trailing median traded value.\n"
        f"Signal after close; next-open fill; BDT {BASE_POLICY.assumed_capital:,.0f} account; "
        f"fee/slippage {BASE_POLICY.fee_rate:.2%}/{BASE_POLICY.slippage_rate:.2%}; "
        f"stress slippage {STRESSED_POLICY.slippage_rate:.2%}; 2% ADV capacity; T+2 sells.\n"
        f"Splits: train < {TRAIN_END}; validation < {VALIDATION_END}; test thereafter.\n"
    )
    eligible = []
    for spec in FACTOR_SPECS.values():
        signals = generate_factor_signals(
            by_code=by_code,
            market_closes=market_closes,
            financials=financials,
            dividends=dividends,
            spec=spec,
            policy=BASE_POLICY,
        )
        base = evaluate_signals(
            signals=signals,
            by_code=by_code,
            market_closes=market_closes,
            spec=spec.exit_spec,
            policy=BASE_POLICY,
        )
        stressed = evaluate_signals(
            signals=signals,
            by_code=by_code,
            market_closes=market_closes,
            spec=spec.exit_spec,
            policy=STRESSED_POLICY,
        )
        base_parts = split_outcomes(base, train_end=TRAIN_END, validation_end=VALIDATION_END)
        stressed_parts = split_outcomes(
            stressed,
            train_end=TRAIN_END,
            validation_end=VALIDATION_END,
        )
        summaries = {label: summarize_outcomes(items) for label, items in base_parts.items()}
        stressed_summaries = {
            label: summarize_outcomes(items) for label, items in stressed_parts.items()
        }
        decision = promotion_decision(
            base_splits=summaries,
            stressed_splits=stressed_summaries,
        )
        print(f"{spec.name} ({spec.key})")
        print(f"  selected={len(signals)} executable={len(base)}")
        _print_summary("full", summarize_outcomes(base))
        for label in ("train", "validation", "test"):
            _print_summary(label, summaries[label])
        print(
            "  stressed holdout means: "
            f"validation={_cell(stressed_summaries['validation'].mean_return_pct)} "
            f"test={_cell(stressed_summaries['test'].mean_return_pct)}"
        )
        portfolio = simulate_portfolio(
            signals=signals,
            valid_outcomes=base,
            by_code=by_code,
            market_closes=market_closes,
            spec=spec.exit_spec,
            policy=BASE_POLICY,
        )
        print(
            f"  portfolio: {portfolio.total_return_pct:+.2f}% vs DSEX "
            f"{portfolio.benchmark_return_pct:+.2f}% (excess {portfolio.excess_return_pct:+.2f}%), "
            f"maxDD {portfolio.maximum_drawdown_pct:.2f}%, trades {portfolio.trades}, "
            f"fees BDT {portfolio.fees_paid:,.0f}, capacity/slot rejects "
            f"{portfolio.capacity_rejections}/{portfolio.slot_rejections}"
        )
        print(
            "  verdict: "
            + (
                "ELIGIBLE FOR FORWARD PAPER"
                if decision.eligible_for_forward_paper
                else "REJECT/KEEP DIAGNOSTIC"
            )
        )
        for gate in decision.failed_gates:
            print(f"    - {gate}")
        print()
        if decision.eligible_for_forward_paper:
            eligible.append(spec.key)
    print("Eligible daily factors:", ", ".join(eligible) if eligible else "none")
    print(
        "\nStructural limits: only two years, current-symbol survivorship, no adjusted closes, "
        "and one dominant market regime. Quality-value also uses a deliberately conservative "
        "two-year fiscal-information lag because exact publication timestamps are unavailable."
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--include-z",
        action="store_true",
        help="include active Z-category equities that still pass history, liquidity, and capacity gates",
    )
    asyncio.run(_run(include_z=parser.parse_args().include_z))
