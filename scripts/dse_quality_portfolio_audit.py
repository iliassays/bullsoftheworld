"""Replay DSE quality portfolio policies from a read-only mixed CSV export."""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import TextIO

from bulls.analytics.dse_edges import EdgeBar, ExecutionPolicy
from bulls.analytics.dse_quality_portfolio import (
    QualityPortfolioPolicy,
    build_quality_rebalances,
    simulate_quality_portfolio,
)
from bulls.analytics.dse_quality_universe import (
    QualityDividend,
    QualityFinancial,
    QualityUniversePolicy,
)

TRAIN_END = dt.date(2025, 7, 1)
VALIDATION_END = dt.date(2026, 1, 1)


def _input(path: str) -> TextIO:
    return sys.stdin if path == "-" else Path(path).open(encoding="utf-8", newline="")


def _book_summary(book) -> dict:
    return {
        "start_date": book.start_date,
        "end_date": book.end_date,
        "total_return_pct": book.total_return_pct,
        "dsex_return_pct": book.benchmark_return_pct,
        "target_gross_dsex_cash_return_pct": book.cash_adjusted_benchmark_return_pct,
        "target_gross_excess_return_pct": book.cash_adjusted_excess_return_pct,
        "maximum_drawdown_pct": book.maximum_drawdown_pct,
        "average_gross_exposure_pct": book.average_gross_exposure_pct,
        "ending_gross_exposure_pct": book.ending_gross_exposure_pct,
        "buys": book.buys,
        "sells": book.sells,
        "capacity_shortfalls": book.capacity_shortfalls,
        "capacity_rejections": book.capacity_rejections,
        "locked_rejections": book.locked_rejections,
        "fees_paid": book.fees_paid,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("csv_path", nargs="?", default="-")
    args = parser.parse_args()
    bars: dict[str, list[EdgeBar]] = defaultdict(list)
    financials: dict[str, list[QualityFinancial]] = defaultdict(list)
    dividends: dict[str, list[QualityDividend]] = defaultdict(list)
    market_closes: dict[dt.date, float] = {}
    sectors: dict[str, str] = {}
    handle = _input(args.csv_path)
    try:
        for row in csv.DictReader(handle):
            kind = row["record_kind"]
            code = row["code"]
            if code:
                sectors[code] = row["sector"] or "Unclassified"
            if kind == "bar":
                bars[code].append(
                    EdgeBar(
                        date=dt.date.fromisoformat(row["date"]),
                        open=float(row["open"]),
                        high=float(row["high"]),
                        low=float(row["low"]),
                        close=float(row["close"]),
                        volume=int(row["volume"]),
                    )
                )
            elif kind == "market":
                market_closes[dt.date.fromisoformat(row["date"])] = float(row["dsex"])
            elif kind == "financial":
                financials[code].append(
                    QualityFinancial(
                        fiscal_year=int(row["fiscal_year"]),
                        eps=float(row["eps"]) if row["eps"] else None,
                        nav_per_share=(
                            float(row["nav_per_share"]) if row["nav_per_share"] else None
                        ),
                    )
                )
            elif kind == "dividend":
                dividends[code].append(
                    QualityDividend(
                        year=int(row["dividend_year"]),
                        cash_pct=float(row["cash_pct"]) if row["cash_pct"] else None,
                    )
                )
    finally:
        if handle is not sys.stdin:
            handle.close()

    execution = ExecutionPolicy(
        assumed_capital=10_000_000,
        target_position_weight=0.085,
    )
    stressed = ExecutionPolicy(
        assumed_capital=10_000_000,
        target_position_weight=0.085,
        slippage_rate=0.0075,
    )
    quality = QualityUniversePolicy()
    legacy_policy = QualityPortfolioPolicy()
    capacity_policy = QualityPortfolioPolicy(
        target_positions=20,
        minimum_positions=10,
        gross_target_weight=0.85,
        capacity_aware_targets=True,
        maximum_position_weight=0.10,
        maximum_sector_weight=0.25,
    )

    def evaluate(policy: QualityPortfolioPolicy) -> tuple[list, dict]:
        rebalances = build_quality_rebalances(
            by_code=dict(bars),
            market_closes=market_closes,
            financials=dict(financials),
            dividends=dict(dividends),
            quality_policy=quality,
            execution_policy=execution,
            portfolio_policy=policy,
            sectors=sectors,
        )
        base = simulate_quality_portfolio(
            rebalances=rebalances,
            by_code=dict(bars),
            market_closes=market_closes,
            execution_policy=execution,
            portfolio_policy=policy,
        )
        stress = simulate_quality_portfolio(
            rebalances=rebalances,
            by_code=dict(bars),
            market_closes=market_closes,
            execution_policy=stressed,
            portfolio_policy=policy,
        )
        details = {
            "rebalances": len(rebalances),
            "eligible_counts": [item.eligible_count for item in rebalances],
            "target_counts": [len(item.targets) for item in rebalances],
            "feasible_target_gross_pct": [
                round(sum(weight for _code, weight in item.target_weights) * 100, 3)
                for item in rebalances
            ],
            "base": _book_summary(base),
            "stressed": _book_summary(stress),
            "windows": {
                label: _book_summary(
                    simulate_quality_portfolio(
                        rebalances=rebalances,
                        by_code=dict(bars),
                        market_closes=market_closes,
                        execution_policy=execution,
                        portfolio_policy=policy,
                        signal_start=start,
                        signal_end=end,
                    )
                )
                for label, start, end in (
                    ("train", None, TRAIN_END),
                    ("validation", TRAIN_END, VALIDATION_END),
                    ("test", VALIDATION_END, None),
                )
            },
        }
        return rebalances, details

    _legacy_rebalances, legacy = evaluate(legacy_policy)
    _capacity_rebalances, capacity = evaluate(capacity_policy)
    output = {
        "diagnostic_only": True,
        "security_count": len(bars),
        "market_sessions": len(market_closes),
        "first_session": min(market_closes, default=None),
        "last_session": max(market_closes, default=None),
        "limitations": [
            "Current active universe creates survivorship bias.",
            "DSE closes are unadjusted for corporate actions.",
            "Historical filing publication timestamps are unavailable.",
            "Dividend income is excluded because ex-date and payment lineage are unavailable.",
            "Approximately two years of daily history is insufficient for promotion.",
        ],
        "legacy_equal_target_policy": legacy,
        "capacity_sector_aware_policy": capacity,
    }
    print(json.dumps(output, indent=2, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
