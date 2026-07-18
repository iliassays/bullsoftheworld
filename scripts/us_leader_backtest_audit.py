"""Run a diagnostic Leader Capture replay from a mixed bar/fact CSV stream."""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import TextIO

from bulls.analytics.leader_capture import LeaderFinancialFact, build_leader_evidence
from bulls.analytics.research_strategy import StrategyBar, StrategySecurity, run_backtest


def _input(path: str) -> TextIO:
    return sys.stdin if path == "-" else Path(path).open(encoding="utf-8", newline="")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("csv_path", nargs="?", default="-")
    parser.add_argument("--initial-capital", type=float, default=1_000_000)
    args = parser.parse_args()
    bars: dict[str, list[StrategyBar]] = defaultdict(list)
    metadata: dict[str, tuple[str, str]] = {}
    facts: list[LeaderFinancialFact] = []
    handle = _input(args.csv_path)
    try:
        for row in csv.DictReader(handle):
            code = row["code"].upper()
            metadata[code] = (
                row["sector"] or "Unclassified",
                row["cap_tier"] or "unclassified",
            )
            if row["record_kind"] == "bar":
                close = float(row["close"])
                adjusted_close = float(row["adjusted_close"] or close)
                adjustment = adjusted_close / close if close > 0 else 1.0
                bars[code].append(
                    StrategyBar(
                        date=row["date"],
                        open=float(row["open"]) * adjustment,
                        high=float(row["high"]) * adjustment,
                        low=float(row["low"]) * adjustment,
                        close=adjusted_close,
                        volume=int(row["volume"]),
                    )
                )
                continue
            facts.append(
                LeaderFinancialFact(
                    code=code,
                    metric=row["metric"],
                    value=float(row["value"]),
                    period_start=row["period_start"] or None,
                    period_end=row["period_end"],
                    period_type=row["period_type"],
                    form=row["form"],
                    accession_number=row["accession_number"],
                    source_url=row["source_url"],
                    known_at=dt.datetime.fromisoformat(row["known_at"]),
                    normalization_version=row["normalization_version"],
                )
            )
    finally:
        if handle is not sys.stdin:
            handle.close()

    evidence = build_leader_evidence(facts)
    securities = [
        StrategySecurity(
            code=code,
            sector=metadata[code][0],
            cap_tier=metadata[code][1],
            bars=sorted(values, key=lambda bar: bar.date),
            evidence=evidence.get(code, []),
        )
        for code, values in sorted(bars.items())
    ]
    result = run_backtest(
        market="US",
        strategy_key="us_leader_capture_v1",
        securities=securities,
        initial_capital=args.initial_capital,
        inactive_security_history_complete=False,
        point_in_time_inputs_complete=False,
    )
    full = result.metrics[0]
    output = {
        "diagnostic_only": True,
        "engine_version": result.engine_version,
        "security_count": len(securities),
        "securities_with_evidence": sum(bool(security.evidence) for security in securities),
        "evidence_observations": sum(len(security.evidence) for security in securities),
        "start_date": result.start_date,
        "end_date": result.end_date,
        "initial_capital": result.initial_capital,
        "final_nav": result.final_nav,
        "benchmark_final": result.benchmark_final,
        "total_return_pct": full.total_return_pct,
        "annualized_return_pct": full.annualized_return_pct,
        "sharpe": full.sharpe,
        "max_drawdown_pct": full.max_drawdown_pct,
        "trades": len(result.trades),
        "traded_codes": sorted({trade.code for trade in result.trades}),
        "fees_paid": result.fees_paid,
        "turnover_pct": result.turnover_pct,
        "validation_status": result.validation_status,
        "failed_gates": result.failed_gates,
    }
    print(json.dumps(output, indent=2, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
