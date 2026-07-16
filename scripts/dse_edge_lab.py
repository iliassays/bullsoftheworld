"""Run the registered DSE edge hypotheses against the local research database.

This is a diagnostic research command. It never writes to the database or activates an agent.

    .venv/bin/python scripts/dse_edge_lab.py
"""

from __future__ import annotations

import asyncio
import datetime as dt
from collections import defaultdict
from dataclasses import replace

from sqlalchemy import select, text

from bulls.analytics.dse_edge_backtest import (
    evaluate_signals,
    promotion_decision,
    simulate_portfolio,
    split_outcomes,
    summarize_outcomes,
)
from bulls.analytics.dse_edges import (
    SPECS,
    EdgeBar,
    ExecutionPolicy,
    SignalPolicy,
    generate_signals,
)
from bulls.core.db import get_sessionmaker
from bulls.core.models import CompanyProfile, DailyBar, MarketSummary, Symbol

TRAIN_END = dt.date(2025, 7, 1)
VALIDATION_END = dt.date(2026, 1, 1)
BASE_POLICY = ExecutionPolicy()
STRESSED_POLICY = ExecutionPolicy(slippage_rate=0.0075)


async def _load() -> tuple[dict[str, list[EdgeBar]], dict[dt.date, float]]:
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        await session.execute(text("SET LOCAL statement_timeout = '5min'"))
        eligible_codes = set(
            await session.scalars(
                select(Symbol.code)
                .join(
                    CompanyProfile,
                    (CompanyProfile.market == Symbol.market)
                    & (CompanyProfile.code == Symbol.code),
                )
                .where(
                    Symbol.market == "DSE",
                    Symbol.is_active.is_(True),
                    Symbol.is_hidden.is_(False),
                    Symbol.data_status == "ready",
                    Symbol.category != "Z",
                    CompanyProfile.instrument_type == "Equity",
                )
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
    market_closes = {row.date: row.dsex for row in market_rows if row.dsex}
    return dict(by_code), market_closes


def _cell(value: float | None, *, suffix: str = "%") -> str:
    return "n/a" if value is None else f"{value:+.2f}{suffix}"


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
        f"excess={_cell(summary.mean_excess_return_pct)} CI95={ci} "
        f"MFE/MAE={_cell(summary.median_mfe_pct)}/{_cell(summary.median_mae_pct)}"
    )


async def _run() -> None:
    by_code, market_closes = await _load()
    first_date = min(bar.date for bars in by_code.values() for bar in bars)
    last_date = max(bar.date for bars in by_code.values() for bar in bars)
    print(
        f"DSE edge lab: {len(by_code)} active non-Z equities, {first_date} to {last_date}\n"
        f"Signal after close; next-open fill; base fee/slippage "
        f"{BASE_POLICY.fee_rate:.2%}/{BASE_POLICY.slippage_rate:.2%} each side; "
        f"stress slippage {STRESSED_POLICY.slippage_rate:.2%} each side.\n"
        f"Splits: train < {TRAIN_END}; validation < {VALIDATION_END}; test thereafter.\n"
    )

    eligible = []
    for spec in SPECS.values():
        signals = generate_signals(
            by_code=by_code,
            market_closes=market_closes,
            spec=spec,
            policy=BASE_POLICY,
        )
        base = evaluate_signals(
            signals=signals,
            by_code=by_code,
            market_closes=market_closes,
            spec=spec,
            policy=BASE_POLICY,
        )
        stressed = evaluate_signals(
            signals=signals,
            by_code=by_code,
            market_closes=market_closes,
            spec=spec,
            policy=STRESSED_POLICY,
        )
        base_partitions = split_outcomes(
            base,
            train_end=TRAIN_END,
            validation_end=VALIDATION_END,
        )
        stressed_partitions = split_outcomes(
            stressed,
            train_end=TRAIN_END,
            validation_end=VALIDATION_END,
        )
        base_summaries = {
            label: summarize_outcomes(items) for label, items in base_partitions.items()
        }
        stressed_summaries = {
            label: summarize_outcomes(items) for label, items in stressed_partitions.items()
        }
        decision = promotion_decision(
            base_splits=base_summaries,
            stressed_splits=stressed_summaries,
        )

        print(f"{spec.name} ({spec.key})")
        print(f"  generated={len(signals)} executable={len(base)}")
        _print_summary("full", summarize_outcomes(base))
        for label in ("train", "validation", "test"):
            _print_summary(label, base_summaries[label])
        print(
            "  stressed holdout means: "
            f"validation={_cell(stressed_summaries['validation'].mean_return_pct)} "
            f"test={_cell(stressed_summaries['test'].mean_return_pct)}"
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
        portfolio = simulate_portfolio(
            signals=signals,
            valid_outcomes=base,
            by_code=by_code,
            market_closes=market_closes,
            spec=spec,
            policy=BASE_POLICY,
        )
        print(
            f"  portfolio: {portfolio.total_return_pct:+.2f}% vs DSEX "
            f"{portfolio.benchmark_return_pct:+.2f}% (excess {portfolio.excess_return_pct:+.2f}%), "
            f"maxDD {portfolio.maximum_drawdown_pct:.2f}%, trades {portfolio.trades}, "
            f"win {portfolio.win_rate_pct or 0:.1f}%, PF {portfolio.profit_factor or 0:.2f}, "
            f"capacity/slot rejects {portfolio.capacity_rejections}/{portfolio.slot_rejections}"
        )
        for label in ("validation", "test"):
            split_portfolio = simulate_portfolio(
                signals=signals,
                valid_outcomes=base_partitions[label],
                by_code=by_code,
                market_closes=market_closes,
                spec=spec,
                policy=BASE_POLICY,
            )
            print(
                f"    {label:<10} book {split_portfolio.total_return_pct:+.2f}% vs DSEX "
                f"{split_portfolio.benchmark_return_pct:+.2f}%, maxDD "
                f"{split_portfolio.maximum_drawdown_pct:.2f}%, trades "
                f"{split_portfolio.trades}"
            )
        print()
        if decision.eligible_for_forward_paper:
            eligible.append(spec.key)

    print("Deep-reclaim threshold sensitivity (diagnostic only; not a promotion search):")
    sensitivity = (
        ("strict", SignalPolicy(maximum_drawdown=-0.45, maximum_range_position=0.12)),
        ("base", SignalPolicy()),
        ("broad", SignalPolicy(maximum_drawdown=-0.35, maximum_range_position=0.20)),
    )
    for label, signal_policy in sensitivity:
        spec = replace(SPECS["deep_reclaim"], key="deep_reclaim")
        signals = generate_signals(
            by_code=by_code,
            market_closes=market_closes,
            spec=spec,
            policy=BASE_POLICY,
            signal_policy=signal_policy,
        )
        outcomes = evaluate_signals(
            signals=signals,
            by_code=by_code,
            market_closes=market_closes,
            spec=spec,
            policy=BASE_POLICY,
        )
        partitions = split_outcomes(
            outcomes,
            train_end=TRAIN_END,
            validation_end=VALIDATION_END,
        )
        validation = summarize_outcomes(partitions["validation"])
        test = summarize_outcomes(partitions["test"])
        print(
            f"  {label:<7} signals={len(signals):>3} "
            f"validation n/mean/median={validation.observations:>2}/"
            f"{_cell(validation.mean_return_pct)}/{_cell(validation.median_return_pct)} "
            f"test n/mean/median={test.observations:>2}/"
            f"{_cell(test.mean_return_pct)}/{_cell(test.median_return_pct)}"
        )
    print()

    print("Eligible strategies:", ", ".join(eligible) if eligible else "none")
    print(
        "\nStructural limits: current-symbol survivorship, no inactive/delisted history, only two "
        "years, raw prices without corporate-action adjustments, and one dominant DSE regime. "
        "Eligibility here permits forward paper evidence only, never live capital."
    )


if __name__ == "__main__":
    asyncio.run(_run())
