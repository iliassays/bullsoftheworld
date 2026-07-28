"""Run the preregistered bullish 20/50 moving-average crossover diagnostic.

Read-only by construction. The command queries daily bars in bounded code chunks, writes one JSON
artifact, and never creates an Atlas strategy, Agent Decision, target, paper order, or UI state.

Usage:

    uv run python scripts/moving_average_crossover_research.py \
        --market DSE --output /tmp/dse-bullish-ma20-50-v1.json
"""

# ruff: noqa: E402

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import math
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np
from sqlalchemy import select, text

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from research.edge_discovery.moving_average_crossover import (
    MovingAverageBar,
    MovingAverageCrossoverSpec,
    MovingAverageCrossoverTrade,
    moving_average_bar_issue,
    scan_bullish_crossover_trades,
)

from bulls.core.db import dispose_engine, get_sessionmaker
from bulls.core.models import CompanyProfile, DailyBar, MarketSummary, SecurityMaster, Symbol

RNG_SEED = 20260728
BOOTSTRAP_DRAWS = 2_000
CHUNK_SIZE = 200


def _spec(market: str) -> MovingAverageCrossoverSpec:
    is_dse = market == "DSE"
    return MovingAverageCrossoverSpec(
        key="dse_bullish_ma20_50_v1" if is_dse else "us_bullish_ma20_50_v1",
        minimum_price=5.0 if is_dse else 1.0,
        minimum_average_turnover=5_000_000.0 if is_dse else 1_000_000.0,
        maximum_close_jump=0.35 if is_dse else None,
    )


def _costs(market: str) -> tuple[float, float]:
    return (0.0065, 0.0100) if market == "DSE" else (0.0030, 0.0060)


def _window(market: str, signal_date: dt.date) -> str:
    if market == "DSE":
        if signal_date <= dt.date(2025, 6, 30):
            return "discovery"
        if signal_date <= dt.date(2025, 12, 31):
            return "validation"
        return "holdout"
    if signal_date <= dt.date(2022, 12, 31):
        return "discovery"
    if signal_date <= dt.date(2024, 12, 31):
        return "validation"
    return "holdout"


async def _codes(market: str) -> list[str]:
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        if market == "DSE":
            rows = await session.scalars(
                select(Symbol.code)
                .join(
                    CompanyProfile,
                    (CompanyProfile.market == Symbol.market) & (CompanyProfile.code == Symbol.code),
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
        else:
            rows = await session.scalars(
                select(SecurityMaster.symbol).where(
                    SecurityMaster.market == "US",
                    SecurityMaster.is_active.is_(True),
                    SecurityMaster.is_product_eligible.is_(True),
                    SecurityMaster.instrument_type.in_(("common_stock", "adr")),
                )
            )
        return sorted(set(rows))


async def _benchmark(market: str) -> dict[dt.date, float]:
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        if market == "DSE":
            rows = (
                await session.execute(
                    select(MarketSummary.date, MarketSummary.dsex)
                    .where(MarketSummary.market == "DSE", MarketSummary.dsex.is_not(None))
                    .order_by(MarketSummary.date)
                )
            ).all()
            return {row.date: float(row.dsex) for row in rows if row.dsex and row.dsex > 0}
        rows = (
            await session.execute(
                select(DailyBar.date, DailyBar.close, DailyBar.adjusted_close)
                .where(DailyBar.market == "US", DailyBar.code == "SPY")
                .order_by(DailyBar.date)
            )
        ).all()
        return {
            row.date: float(row.adjusted_close or row.close)
            for row in rows
            if (row.adjusted_close or row.close) and (row.adjusted_close or row.close) > 0
        }


async def _bars_for_chunk(
    market: str,
    codes: list[str],
) -> tuple[dict[str, list[MovingAverageBar]], dict[str, Any]]:
    load_start = dt.date(2017, 1, 1) if market == "US" else dt.date(2024, 1, 1)
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        await session.execute(text("SET LOCAL statement_timeout = '10min'"))
        rows = (
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
                .where(
                    DailyBar.market == market,
                    DailyBar.code.in_(codes),
                    DailyBar.date >= load_start,
                )
                .order_by(DailyBar.code, DailyBar.date)
            )
        ).all()

    grouped: dict[str, list[MovingAverageBar]] = defaultdict(list)
    quarantined_codes: set[str] = set()
    quarantine_reasons: dict[str, int] = defaultdict(int)
    for row in rows:
        if min(row.open or 0, row.high or 0, row.low or 0, row.close or 0) <= 0:
            quarantined_codes.add(row.code)
            quarantine_reasons["non_positive"] += 1
            continue
        if market == "US":
            if row.adjusted_close is None or row.adjusted_close <= 0:
                quarantined_codes.add(row.code)
                quarantine_reasons["missing_adjusted_close"] += 1
                continue
            factor = float(row.adjusted_close) / float(row.close)
        else:
            factor = 1.0
        bar = MovingAverageBar(
            date=row.date,
            open=float(row.open) * factor,
            high=float(row.high) * factor,
            low=float(row.low) * factor,
            close=float(row.close) * factor,
            raw_close=float(row.close),
            volume=float(row.volume or 0),
        )
        issue = moving_average_bar_issue(bar)
        if issue is not None:
            quarantined_codes.add(row.code)
            quarantine_reasons[issue] += 1
            continue
        grouped[row.code].append(bar)
    return dict(grouped), {
        "quarantined_rows": sum(quarantine_reasons.values()),
        "quarantined_codes": quarantined_codes,
        "quarantine_reasons": quarantine_reasons,
    }


async def _trades(
    market: str,
    codes: list[str],
    spec: MovingAverageCrossoverSpec,
) -> tuple[list[MovingAverageCrossoverTrade], dict[str, Any]]:
    trades: list[MovingAverageCrossoverTrade] = []
    normal_cost, stressed_cost = _costs(market)
    quality: dict[str, Any] = {
        "quarantined_rows": 0,
        "quarantined_codes": set(),
        "quarantine_reasons": defaultdict(int),
    }
    chunks = [codes[index : index + CHUNK_SIZE] for index in range(0, len(codes), CHUNK_SIZE)]
    for number, chunk in enumerate(chunks, start=1):
        grouped, chunk_quality = await _bars_for_chunk(market, chunk)
        quality["quarantined_rows"] += chunk_quality["quarantined_rows"]
        quality["quarantined_codes"].update(chunk_quality["quarantined_codes"])
        for reason, count in chunk_quality["quarantine_reasons"].items():
            quality["quarantine_reasons"][reason] += count
        for code, bars in grouped.items():
            trades.extend(
                scan_bullish_crossover_trades(
                    code,
                    bars,
                    spec=spec,
                    normal_one_way_cost=normal_cost,
                    stressed_one_way_cost=stressed_cost,
                )
            )
        if number % 5 == 0 or number == len(chunks):
            print(f"{market} chunks {number}/{len(chunks)}: {len(trades):,} completed trades")
    return trades, {
        "quarantined_rows": quality["quarantined_rows"],
        "quarantined_codes": len(quality["quarantined_codes"]),
        "quarantine_reasons": dict(sorted(quality["quarantine_reasons"].items())),
        "policy": "invalid rows excluded without mutation; omissions remain visible",
    }


def _benchmark_return(
    benchmark: dict[dt.date, float],
    entry_date: dt.date,
    exit_date: dt.date,
) -> float | None:
    entry = benchmark.get(entry_date)
    exit_value = benchmark.get(exit_date)
    if entry is None or exit_value is None or entry <= 0:
        return None
    return exit_value / entry - 1.0


def _bootstrap(values: np.ndarray, block: int = 63) -> tuple[float | None, float | None]:
    if values.size < 5:
        return None, None
    block = max(1, min(block, values.size))
    blocks = math.ceil(values.size / block)
    rng = np.random.default_rng(RNG_SEED)
    starts = rng.integers(0, values.size, size=(BOOTSTRAP_DRAWS, blocks))
    offsets = np.arange(block)
    indices = (starts[:, :, None] + offsets).reshape(BOOTSTRAP_DRAWS, -1) % values.size
    means = values[indices[:, : values.size]].mean(axis=1)
    low, high = np.percentile(means, [2.5, 97.5])
    return float(low), float(high)


def _rounded(value: float | None, digits: int = 4) -> float | None:
    return None if value is None or not math.isfinite(value) else round(value, digits)


def _summary(
    trades: list[MovingAverageCrossoverTrade],
    benchmark: dict[dt.date, float],
) -> dict[str, Any]:
    observations: list[tuple[MovingAverageCrossoverTrade, float, float]] = []
    for trade in trades:
        market_return = _benchmark_return(benchmark, trade.entry_date, trade.exit_date)
        if market_return is not None:
            observations.append((trade, market_return, trade.normal_return - market_return))
    if not observations:
        return {"trades": 0, "signal_dates": 0, "codes": 0}

    normal = [row[0].normal_return for row in observations]
    stressed = [row[0].stressed_return for row in observations]
    excess = [row[2] for row in observations]
    gains = sum(value for value in normal if value > 0)
    losses = abs(sum(value for value in normal if value < 0))
    per_date: dict[dt.date, list[tuple[float, float, float]]] = defaultdict(list)
    for trade, _, relative in observations:
        per_date[trade.signal_date].append((trade.normal_return, trade.stressed_return, relative))
    cohort_normal = np.asarray(
        [statistics.fmean(row[0] for row in values) for _, values in sorted(per_date.items())]
    )
    cohort_stressed = np.asarray(
        [statistics.fmean(row[1] for row in values) for _, values in sorted(per_date.items())]
    )
    cohort_excess = np.asarray(
        [statistics.fmean(row[2] for row in values) for _, values in sorted(per_date.items())]
    )
    ci_low, ci_high = _bootstrap(cohort_excess)
    normal_ex_top2 = statistics.fmean(sorted(normal)[:-2]) if len(normal) > 2 else None
    return {
        "trades": len(observations),
        "signal_dates": len(per_date),
        "codes": len({row[0].code for row in observations}),
        "mean_gross_pct": _rounded(
            statistics.fmean(row[0].gross_return for row in observations) * 100
        ),
        "mean_net_pct": _rounded(statistics.fmean(normal) * 100),
        "median_net_pct": _rounded(statistics.median(normal) * 100),
        "mean_stressed_pct": _rounded(statistics.fmean(stressed) * 100),
        "median_stressed_pct": _rounded(statistics.median(stressed) * 100),
        "win_rate_pct": _rounded(sum(value > 0 for value in normal) / len(normal) * 100),
        "profit_factor": _rounded(gains / losses if losses > 0 else None),
        "mean_benchmark_pct": _rounded(
            statistics.fmean(row[1] for row in observations) * 100
        ),
        "mean_excess_pct": _rounded(statistics.fmean(excess) * 100),
        "median_excess_pct": _rounded(statistics.median(excess) * 100),
        "cohort_mean_net_pct": _rounded(float(cohort_normal.mean()) * 100),
        "cohort_mean_stressed_pct": _rounded(float(cohort_stressed.mean()) * 100),
        "cohort_mean_excess_pct": _rounded(float(cohort_excess.mean()) * 100),
        "cohort_excess_ci_low_pct": _rounded(None if ci_low is None else ci_low * 100),
        "cohort_excess_ci_high_pct": _rounded(None if ci_high is None else ci_high * 100),
        "mean_net_excluding_top_two_pct": _rounded(
            None if normal_ex_top2 is None else normal_ex_top2 * 100
        ),
        "median_mfe_pct": _rounded(
            statistics.median(row[0].maximum_favorable_excursion for row in observations) * 100
        ),
        "median_mae_pct": _rounded(
            statistics.median(row[0].maximum_adverse_excursion for row in observations) * 100
        ),
        "median_holding_sessions": _rounded(
            statistics.median(row[0].holding_sessions for row in observations),
            2,
        ),
        "entry_gap_over_5pct_rate": _rounded(
            sum(abs(row[0].entry_gap) > 0.05 for row in observations) / len(observations) * 100
        ),
        "exit_reasons": {
            reason: sum(row[0].exit_reason == reason for row in observations)
            for reason in ("slow_average_break", "timeout")
        },
    }


def _gates(summary: dict[str, Any]) -> dict[str, bool]:
    return {
        "at_least_30_trades": summary.get("trades", 0) >= 30,
        "at_least_20_signal_dates": summary.get("signal_dates", 0) >= 20,
        "positive_median_net": (summary.get("median_net_pct") or 0) > 0,
        "positive_median_excess": (summary.get("median_excess_pct") or 0) > 0,
        "positive_stressed_cohort": (summary.get("cohort_mean_stressed_pct") or 0) > 0,
        "positive_excess_ci_floor": (summary.get("cohort_excess_ci_low_pct") or 0) > 0,
        "profit_factor_above_1_10": (summary.get("profit_factor") or 0) > 1.10,
        "positive_without_top_two": (summary.get("mean_net_excluding_top_two_pct") or 0) > 0,
    }


async def async_main(market: str, output: Path) -> None:
    try:
        codes = await _codes(market)
        benchmark = await _benchmark(market)
        spec = _spec(market)
        print(f"Scanning {len(codes):,} {market} securities")
        trades, quality = await _trades(market, codes, spec)
        results = {
            window: _summary(
                [trade for trade in trades if _window(market, trade.signal_date) == window],
                benchmark,
            )
            for window in ("discovery", "validation", "holdout")
        }
        gates = {window: _gates(results[window]) for window in ("validation", "holdout")}
        payload = {
            "registered_document": (
                "docs/research/moving-average-crossover-preregistration-2026-07-28.md"
            ),
            "market": market,
            "universe": {
                "codes": len(codes),
                "survivorship": "current active product universe; positive results are an upper bound",
                "price_basis": (
                    "raw DSE OHLC with >35% jump contamination filter"
                    if market == "DSE"
                    else "vendor-adjusted US OHLC; current survivors only"
                ),
            },
            "costs": {
                "normal_one_way": _costs(market)[0],
                "stressed_one_way": _costs(market)[1],
            },
            "data_quality": quality,
            "specification": spec.as_dict(),
            "results": results,
            "gates": {
                "by_window": gates,
                "eligible_for_portfolio_diagnostic": all(
                    all(window.values()) for window in gates.values()
                ),
            },
            "atlas_action": {
                "agent_decision": False,
                "paper_target": False,
                "public_idea": False,
                "reason": "Read-only historical diagnostic; admission requires every frozen gate.",
            },
        }
        output.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(output.write_text, json.dumps(payload, indent=2, default=str) + "\n")
        for window, result in results.items():
            print(
                f"{market} {window:10s} n={result.get('trades', 0):>5} "
                f"net={result.get('mean_net_pct')}% median={result.get('median_net_pct')}% "
                f"excess={result.get('cohort_mean_excess_pct')}% "
                f"stress={result.get('cohort_mean_stressed_pct')}% "
                f"CI=[{result.get('cohort_excess_ci_low_pct')}, "
                f"{result.get('cohort_excess_ci_high_pct')}]"
            )
        print(
            "Eligible for portfolio diagnostic: "
            f"{payload['gates']['eligible_for_portfolio_diagnostic']}"
        )
        print(f"Wrote {output}")
    finally:
        await dispose_engine()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--market", choices=("DSE", "US"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    asyncio.run(async_main(arguments.market, arguments.output))


if __name__ == "__main__":
    main()
