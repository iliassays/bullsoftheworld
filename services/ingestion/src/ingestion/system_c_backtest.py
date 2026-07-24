"""Run System C (the factor sleeve) end to end against real recorded data.

Assembles the whole chain the institutional study asks for and prints the verdict:

  point-in-time fundamentals -> factor scores -> composite ranks -> vol-scaled sleeve
    -> monthly weight schedule -> the shared execution engine at measured + stressed costs
      -> deflated Sharpe -> comparison against the nulls it has to beat

Everything here is read-only. No order is placed, no shadow book is created, nothing is
persisted: this reports what the evidence says, and the honest expected outcome is that a
four-factor composite does *not* clearly beat an equal-weight book (Phase 12 is explicit that
System C's null is "nearly unbeatable" and that measuring this is the book's actual job).

Usage::

    python -m ingestion.system_c_backtest --start 2024-01-01 --max-symbols 400
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import sys
from typing import Any

from sqlalchemy import desc, func, select

from bulls.analytics.deflated_sharpe import deflated_sharpe_ratio
from bulls.analytics.factor_sleeve import (
    FundamentalObservation,
    SleevePolicy,
)
from bulls.analytics.institutional_schedules import build_factor_schedules
from bulls.analytics.research_strategy import (
    RISK_POLICIES,
    BenchmarkPoint,
    BenchmarkSeries,
    StrategyBar,
    StrategySecurity,
    run_backtest,
    run_cost_tiered_backtest,
)
from bulls.core.db import get_sessionmaker
from bulls.core.models import DailyBar, SecFinancialFactObservation, SecurityMaster
from bulls.market_data.providers.sec_edgar import METRIC_SPECS

_FACTOR_METRICS = ("equity", "net_income", "shares_outstanding")
_CONCEPT_PRIORITY = {
    (spec.metric, concept.taxonomy, concept.concept): priority
    for spec in METRIC_SPECS
    for priority, concept in enumerate(spec.concepts)
}


async def _load(
    max_symbols: int, start: dt.date
) -> tuple[dict[str, list[StrategyBar]], list[FundamentalObservation]]:
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        # Select the research universe from liquidity observable before the test begins. Current
        # active-symbol state and alphabetical truncation both introduce survivorship/selection
        # bias. Delisted names remain eligible when their historical bars exist.
        liquidity = (
            select(
                DailyBar.code,
                func.avg(DailyBar.close * DailyBar.volume).label("average_dollar_volume"),
            )
            .join(
                SecurityMaster,
                (SecurityMaster.market == DailyBar.market)
                & (SecurityMaster.symbol == DailyBar.code),
            )
            .where(
                DailyBar.market == "US",
                SecurityMaster.instrument_type.in_(("common_stock", "adr")),
                DailyBar.date < start,
                DailyBar.date >= start - dt.timedelta(days=180),
            )
            .group_by(DailyBar.code)
            .order_by(desc("average_dollar_volume"), DailyBar.code)
        )
        if max_symbols > 0:
            liquidity = liquidity.limit(max_symbols)
        codes = [code for code, _ in (await session.execute(liquidity)).all()]
        if not codes:
            return {}, []
        bars_rows = list(
            await session.execute(
                select(
                    DailyBar.code,
                    DailyBar.date,
                    DailyBar.open,
                    DailyBar.high,
                    DailyBar.low,
                    DailyBar.close,
                    DailyBar.volume,
                    DailyBar.adjusted_close,
                )
                .where(DailyBar.market == "US", DailyBar.code.in_(codes))
                .order_by(DailyBar.code, DailyBar.date)
            )
        )
        fact_rows = list(
            await session.execute(
                select(
                    SecFinancialFactObservation.code,
                    SecFinancialFactObservation.metric,
                    SecFinancialFactObservation.value,
                    SecFinancialFactObservation.unit,
                    SecFinancialFactObservation.period_start,
                    SecFinancialFactObservation.period_end,
                    SecFinancialFactObservation.period_type,
                    SecFinancialFactObservation.known_at,
                    SecFinancialFactObservation.accession_number,
                    SecFinancialFactObservation.taxonomy,
                    SecFinancialFactObservation.source_concept,
                ).where(
                    SecFinancialFactObservation.market == "US",
                    SecFinancialFactObservation.code.in_(codes),
                    SecFinancialFactObservation.metric.in_(_FACTOR_METRICS),
                )
            )
        )

    bars: dict[str, list[StrategyBar]] = {}
    for code, date, open_, high, low, close, volume, adjusted_close in bars_rows:
        if min(open_ or 0, high or 0, low or 0, close or 0) <= 0:
            continue
        adjustment = adjusted_close / close if adjusted_close is not None and close > 0 else 1.0
        bars.setdefault(code, []).append(
            StrategyBar(
                date=date,
                open=open_ * adjustment,
                high=high * adjustment,
                low=low * adjustment,
                close=close * adjustment,
                volume=int(volume or 0),
            )
        )
    facts = [
        FundamentalObservation(
            code=row.code,
            metric=row.metric,
            value=row.value,
            unit=row.unit,
            period_start=row.period_start,
            period_end=row.period_end,
            period_type=row.period_type,
            known_at=row.known_at,
            accession_number=row.accession_number,
            concept_priority=_CONCEPT_PRIORITY.get(
                (row.metric, row.taxonomy, row.source_concept),
                len(METRIC_SPECS),
            ),
        )
        for row in fact_rows
    ]
    return bars, facts


async def _load_benchmark(start: dt.date) -> BenchmarkSeries | None:
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        rows = (
            await session.execute(
                select(DailyBar.date, DailyBar.close, DailyBar.adjusted_close)
                .where(
                    DailyBar.market == "US",
                    DailyBar.code == "SPY",
                    DailyBar.date >= start,
                )
                .order_by(DailyBar.date)
            )
        ).all()
    points = [
        BenchmarkPoint(
            date=row.date,
            close=float(row.adjusted_close if row.adjusted_close is not None else row.close),
        )
        for row in rows
        if (row.adjusted_close if row.adjusted_close is not None else row.close) > 0
    ]
    return (
        BenchmarkSeries(key="spy_total_return_proxy", label="SPY adjusted close", points=points)
        if points
        else None
    )


def _build_schedule(
    bars: dict[str, list[StrategyBar]],
    facts: list[FundamentalObservation],
    sessions: list[dt.date],
    policy: SleevePolicy,
    max_half_spread_bps: float,
) -> tuple[dict[dt.date, dict[str, float]], dict[str, Any]]:
    bundle = build_factor_schedules(
        bars=bars,
        observations=facts,
        sessions=sessions,
        policy=policy,
        max_half_spread_bps=max_half_spread_bps,
    )
    return bundle.strategy, {
        **bundle.diagnostics,
        "avg_ranked": bundle.diagnostics["average_ranked"],
        "avg_selected": bundle.diagnostics["average_selected"],
        "null": bundle.equal_weight_null,
        "momentum": bundle.momentum_null,
        "cap_weight": bundle.cap_weighted_null,
    }


def _score(result, label: str, trials: int) -> dict[str, Any]:
    navs = [p.nav for p in result.equity_curve]
    returns = [navs[i] / navs[i - 1] - 1 for i in range(1, len(navs)) if navs[i - 1] > 0]
    dsr = deflated_sharpe_ratio(returns, num_trials=trials)
    full = result.metrics[0]
    benchmark = (result.benchmark_final / result.initial_capital - 1) * 100
    net = (result.final_nav / result.initial_capital - 1) * 100
    return {
        "book": label,
        "net_return_pct": round(net, 2),
        "benchmark_return_pct": round(benchmark, 2),
        "excess_pct": round(net - benchmark, 2),
        "sharpe": full.sharpe,
        "max_drawdown_pct": full.max_drawdown_pct,
        "trades": len(result.trades),
        "deflated_sharpe": round(dsr.deflated_sharpe, 4) if dsr else None,
        "clears_overfitting_bar": dsr.passes if dsr else None,
    }


async def main_async(args: argparse.Namespace) -> dict[str, Any]:
    bars, facts = await _load(args.max_symbols, args.start)
    if not bars:
        return {"error": "no point-in-time universe existed before the requested start date"}
    sessions = sorted(
        {b.date for history in bars.values() for b in history if b.date >= args.start}
    )
    policy = SleevePolicy(target_positions=args.positions, minimum_factors=4)
    schedule, diagnostics = _build_schedule(
        bars,
        facts,
        sessions,
        policy,
        args.max_half_spread_bps,
    )
    if not schedule:
        return {
            "error": "no rebalance produced a ranked universe",
            "hint": "needs >=252 sessions of history plus published fundamentals",
            "sessions": len(sessions),
        }

    securities = [
        StrategySecurity(
            code=code,
            sector="Unclassified",
            cap_tier="unclassified",
            bars=[b for b in history if b.date >= args.start],
        )
        for code, history in bars.items()
    ]
    benchmark = await _load_benchmark(args.start)
    common = dict(
        market="US",
        strategy_key="us_factor_sleeve_v1",
        securities=securities,
        risk_policy=RISK_POLICIES["US"],
        execution_timing="next_close",
        benchmark_series=benchmark,
    )
    cost_tiered = run_cost_tiered_backtest(
        **common,
        weight_schedule=schedule,
    )
    sleeve = cost_tiered.primary
    # The sleeve, then all three nulls it must beat, through the identical execution engine.
    null_1n = run_backtest(
        **common,
        weight_schedule=diagnostics["null"],
        use_point_in_time_spread=True,
    )
    momentum = run_backtest(
        **common,
        weight_schedule=diagnostics["momentum"],
        use_point_in_time_spread=True,
    )
    cap_weight = run_backtest(
        **common,
        weight_schedule=diagnostics["cap_weight"],
        use_point_in_time_spread=True,
    )

    report = {
        "universe_symbols": len(bars),
        "universe_selection": "pre-start trailing dollar volume; includes inactive historical bars",
        "universe_truncated": args.max_symbols > 0,
        "rejected_by_point_in_time_spread_gate": diagnostics["rejected_by_spread"],
        "median_half_spread_bps": diagnostics["median_half_spread_bps"],
        "sessions": len(sessions),
        "rebalances": diagnostics["rebalances"],
        "avg_ranked_per_rebalance": diagnostics["avg_ranked"],
        "avg_positions_held": diagnostics["avg_selected"],
        "books": [
            _score(sleeve, "System C four-factor sleeve", args.trials),
            _score(null_1n, "NULL: 1/N over the eligible universe", 1),
            _score(momentum, "NULL: naive momentum only", 1),
            _score(cap_weight, "NULL: cap-weighted eligible universe", 1),
        ],
        "cost_stress": cost_tiered.model_dump(mode="json", exclude={"primary"}),
    }
    sleeve_excess = report["books"][0]["excess_pct"]
    beats_1n = report["books"][0]["net_return_pct"] > report["books"][1]["net_return_pct"]
    beats_naive = report["books"][0]["net_return_pct"] > report["books"][2]["net_return_pct"]
    beats_cap_weight = report["books"][0]["net_return_pct"] > report["books"][3]["net_return_pct"]
    report["verdict"] = {
        "beats_equal_weight_null": beats_1n,
        "beats_naive_single_factor": beats_naive,
        "beats_cap_weighted_null": beats_cap_weight,
        "beats_engine_diagnostic_benchmark": sleeve_excess > 0,
        "reading": (
            "The composite earns its complexity only if it beats every preregistered null after costs. "
            "Failing that is a valid preregistered result, not a bug."
        ),
    }
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", type=dt.date.fromisoformat, default=dt.date(2023, 1, 1))
    parser.add_argument(
        "--max-symbols",
        type=int,
        default=400,
        help="point-in-time liquidity-ranked cap; use 0 for all symbols and promotion-grade work",
    )
    parser.add_argument("--positions", type=int, default=40)
    parser.add_argument(
        "--max-half-spread-bps",
        type=float,
        default=50.0,
        help="tradeable gate: exclude names whose measured half-spread exceeds this",
    )
    parser.add_argument(
        "--trials",
        type=int,
        default=1,
        help="specifications tried in this family; raises the overfitting bar",
    )
    args = parser.parse_args()
    json.dump(asyncio.run(main_async(args)), sys.stdout, indent=2, default=str)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
