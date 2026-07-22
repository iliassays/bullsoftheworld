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

from sqlalchemy import select

from bulls.analytics.deflated_sharpe import deflated_sharpe_ratio
from bulls.analytics.factor_sleeve import (
    FundamentalFact,
    PricePoint,
    SecurityFactorInputs,
    SleevePolicy,
    compute_factor_scores,
    equal_weight_null,
    point_in_time_fundamentals,
    rank_universe,
    single_factor_null,
    sleeve_weights,
)
from bulls.analytics.research_strategy import (
    RISK_POLICIES,
    StrategyBar,
    StrategySecurity,
    run_backtest,
)
from bulls.core.db import get_sessionmaker
from bulls.core.models import DailyBar, SecFinancialFact, Symbol

_FACTOR_METRICS = ("equity", "net_income", "shares_outstanding")
# Rebalance monthly (Phase 12: "refresh monthly"), measured in trading sessions.
_REBALANCE_SESSIONS = 21


async def _load(max_symbols: int) -> tuple[dict[str, list[DailyBar]], list[FundamentalFact]]:
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        codes = list(
            await session.scalars(
                select(Symbol.code)
                .where(Symbol.market == "US", Symbol.data_status == "ready")
                .order_by(Symbol.code)
                .limit(max_symbols)
            )
        )
        bars_rows = list(
            await session.execute(
                select(DailyBar.code, DailyBar.date, DailyBar.open, DailyBar.high,
                       DailyBar.low, DailyBar.close, DailyBar.volume)
                .where(DailyBar.market == "US", DailyBar.code.in_(codes))
                .order_by(DailyBar.code, DailyBar.date)
            )
        )
        fact_rows = list(
            await session.execute(
                select(SecFinancialFact.code, SecFinancialFact.metric, SecFinancialFact.value,
                       SecFinancialFact.period_end, SecFinancialFact.filed_at)
                .where(
                    SecFinancialFact.market == "US",
                    SecFinancialFact.code.in_(codes),
                    SecFinancialFact.metric.in_(_FACTOR_METRICS),
                )
            )
        )

    bars: dict[str, list[DailyBar]] = {}
    for code, date, open_, high, low, close, volume in bars_rows:
        if min(open_ or 0, high or 0, low or 0, close or 0) <= 0:
            continue
        bars.setdefault(code, []).append(
            StrategyBar(date=date, open=open_, high=high, low=low, close=close,
                        volume=int(volume or 0))
        )
    facts = [
        FundamentalFact(code=c, metric=m, value=v, period_end=pe, filed_at=fa)
        for c, m, v, pe, fa in fact_rows
    ]
    return bars, facts


def _build_schedule(
    bars: dict[str, list[StrategyBar]],
    facts: list[FundamentalFact],
    sessions: list[dt.date],
    policy: SleevePolicy,
) -> tuple[dict[dt.date, dict[str, float]], dict[str, Any]]:
    """Monthly rebalances, each using only what was knowable on that date."""
    schedule: dict[dt.date, dict[str, float]] = {}
    diagnostics = {"rebalances": 0, "avg_ranked": 0.0, "avg_selected": 0.0, "coverage": {}}
    ranked_counts: list[int] = []
    selected_counts: list[int] = []
    null_schedule: dict[dt.date, dict[str, float]] = {}
    momentum_schedule: dict[dt.date, dict[str, float]] = {}

    for index, as_of in enumerate(sessions):
        if index < 252 or index % _REBALANCE_SESSIONS != 0:
            continue
        current = point_in_time_fundamentals(facts, as_of=as_of)
        prior = point_in_time_fundamentals(facts, as_of=as_of - dt.timedelta(days=365))
        scores = []
        for code, history in bars.items():
            window = [b for b in history if b.date <= as_of]
            if len(window) < 253:
                continue
            scores.append(
                compute_factor_scores(
                    SecurityFactorInputs(
                        code=code,
                        prices=[PricePoint(date=b.date, close=b.close) for b in window],
                        fundamentals=current.get(code, {}),
                        prior_fundamentals=prior.get(code, {}),
                    )
                )
            )
        if not scores:
            continue
        ranked = rank_universe(scores, policy)
        if not ranked:
            continue
        weights = sleeve_weights(ranked, policy)
        schedule[as_of] = weights
        null_schedule[as_of] = equal_weight_null([r.code for r in ranked[: policy.target_positions]])
        momentum_schedule[as_of] = single_factor_null(scores, "momentum", policy)
        ranked_counts.append(len(ranked))
        selected_counts.append(len(weights))
        diagnostics["rebalances"] += 1

    if ranked_counts:
        diagnostics["avg_ranked"] = round(sum(ranked_counts) / len(ranked_counts), 1)
        diagnostics["avg_selected"] = round(sum(selected_counts) / len(selected_counts), 1)
    return schedule, {**diagnostics, "null": null_schedule, "momentum": momentum_schedule}


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
    bars, facts = await _load(args.max_symbols)
    if not bars:
        return {"error": "no price history available for the selected universe"}
    sessions = sorted({b.date for history in bars.values() for b in history if b.date >= args.start})
    policy = SleevePolicy(target_positions=args.positions)
    schedule, diagnostics = _build_schedule(bars, facts, sessions, policy)
    if not schedule:
        return {
            "error": "no rebalance produced a ranked universe",
            "hint": "needs >=252 sessions of history plus published fundamentals",
            "sessions": len(sessions),
        }

    securities = [
        StrategySecurity(code=code, sector="Unclassified", cap_tier="unclassified",
                         bars=[b for b in history if b.date >= args.start])
        for code, history in bars.items()
    ]
    common = dict(
        market="US", strategy_key="us_factor_sleeve_v1", securities=securities,
        risk_policy=RISK_POLICIES["US"],
    )
    # The sleeve, then the two nulls it must beat, all through the same engine (13.3.4).
    sleeve = run_backtest(**common, weight_schedule=schedule)
    null_1n = run_backtest(**common, weight_schedule=diagnostics["null"])
    momentum = run_backtest(**common, weight_schedule=diagnostics["momentum"])

    report = {
        "universe_symbols": len(bars),
        "sessions": len(sessions),
        "rebalances": diagnostics["rebalances"],
        "avg_ranked_per_rebalance": diagnostics["avg_ranked"],
        "avg_positions_held": diagnostics["avg_selected"],
        "books": [
            _score(sleeve, "System C four-factor sleeve", args.trials),
            _score(null_1n, "NULL: 1/N over the same names", 1),
            _score(momentum, "NULL: naive momentum only", 1),
        ],
    }
    sleeve_excess = report["books"][0]["excess_pct"]
    beats_1n = report["books"][0]["net_return_pct"] > report["books"][1]["net_return_pct"]
    beats_naive = report["books"][0]["net_return_pct"] > report["books"][2]["net_return_pct"]
    report["verdict"] = {
        "beats_equal_weight_null": beats_1n,
        "beats_naive_single_factor": beats_naive,
        "beats_universe_benchmark": sleeve_excess > 0,
        "reading": (
            "The composite earns its complexity only if it beats BOTH nulls after costs. "
            "Failing that is a valid preregistered result, not a bug."
        ),
    }
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", type=dt.date.fromisoformat, default=dt.date(2023, 1, 1))
    parser.add_argument("--max-symbols", type=int, default=400)
    parser.add_argument("--positions", type=int, default=40)
    parser.add_argument(
        "--trials", type=int, default=1,
        help="specifications tried in this family; raises the overfitting bar",
    )
    args = parser.parse_args()
    json.dump(asyncio.run(main_async(args)), sys.stdout, indent=2, default=str)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
