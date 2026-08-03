"""Evaluate the supplied Oyster hypothesis on stored DSE or US completed daily bars.

The result is an event-study artifact, not a strategy, recommendation, Agent Decision or paper
trade.  It measures the first point-in-time retest state after a falling-resistance break and
keeps DSE and US conclusions separate.

Usage:

    uv run python scripts/oyster_pattern_research.py --market DSE --output /tmp/oyster-dse.json
    uv run python scripts/oyster_pattern_research.py --market US --output /tmp/oyster-us.json
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

from sqlalchemy import select, text

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from research.edge_discovery.oyster import (
    OysterResearchBar,
    OysterResearchEvent,
    OysterResearchSpec,
    scan_oyster_events,
)

from bulls.analytics.oyster import OysterConfig
from bulls.core.db import dispose_engine, get_sessionmaker
from bulls.core.models import CompanyProfile, DailyBar, MarketSummary, SecurityMaster, Symbol

CHUNK_SIZE = 200


def _spec(market: str) -> OysterResearchSpec:
    if market == "DSE":
        return OysterResearchSpec(
            key="dse_oyster_daily_v1",
            analysis_start=dt.date(2024, 6, 1),
            minimum_price=5.0,
            maximum_price=None,
            minimum_average_turnover=5_000_000.0,
            maximum_absolute_close_return=0.35,
            detector=OysterConfig(maximum_cross_return=0.15),
        )
    return OysterResearchSpec(
        key="us_oyster_daily_v1",
        analysis_start=dt.date(2023, 1, 1),
        minimum_price=0.25,
        maximum_price=10.0,
        minimum_average_turnover=1_000_000.0,
        maximum_absolute_close_return=None,
    )


def _load_start(market: str) -> dt.date:
    return dt.date(2024, 1, 1) if market == "DSE" else dt.date(2022, 7, 1)


def _window(market: str, signal_date: dt.date) -> str:
    if market == "DSE":
        if signal_date <= dt.date(2025, 6, 30):
            return "discovery"
        if signal_date <= dt.date(2025, 12, 31):
            return "validation"
        return "holdout"
    if signal_date <= dt.date(2024, 12, 31):
        return "discovery"
    if signal_date <= dt.date(2025, 12, 31):
        return "validation"
    return "holdout"


async def _codes(market: str) -> list[str]:
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        if market == "DSE":
            values = await session.scalars(
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
            values = await session.scalars(
                select(SecurityMaster.symbol).where(
                    SecurityMaster.market == "US",
                    SecurityMaster.is_active.is_(True),
                    SecurityMaster.is_product_eligible.is_(True),
                    SecurityMaster.instrument_type.in_(("common_stock", "adr")),
                )
            )
        return sorted(set(values))


async def _bars_for_chunk(
    market: str,
    codes: list[str],
) -> tuple[dict[str, list[OysterResearchBar]], dict[str, int]]:
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
                    DailyBar.date >= _load_start(market),
                )
                .order_by(DailyBar.code, DailyBar.date)
            )
        ).all()

    grouped: dict[str, list[OysterResearchBar]] = defaultdict(list)
    quality = {"invalid_ohlc": 0, "missing_us_adjusted_close": 0}
    for row in rows:
        if min(row.open or 0, row.high or 0, row.low or 0, row.close or 0) <= 0:
            quality["invalid_ohlc"] += 1
            continue
        if market == "US":
            if row.adjusted_close is None or row.adjusted_close <= 0:
                quality["missing_us_adjusted_close"] += 1
                continue
            factor = float(row.adjusted_close) / float(row.close)
        else:
            factor = 1.0
        grouped[row.code].append(
            OysterResearchBar(
                date=row.date,
                open=float(row.open) * factor,
                high=float(row.high) * factor,
                low=float(row.low) * factor,
                close=float(row.close) * factor,
                volume=float(row.volume or 0),
            )
        )
    return dict(grouped), quality


async def _events(
    market: str,
    codes: list[str],
    spec: OysterResearchSpec,
) -> tuple[list[OysterResearchEvent], dict[str, int]]:
    events: list[OysterResearchEvent] = []
    quality: dict[str, int] = defaultdict(int)
    chunks = [codes[index : index + CHUNK_SIZE] for index in range(0, len(codes), CHUNK_SIZE)]
    for number, chunk in enumerate(chunks, start=1):
        grouped, chunk_quality = await _bars_for_chunk(market, chunk)
        for key, count in chunk_quality.items():
            quality[key] += count
        for code, bars in grouped.items():
            events.extend(scan_oyster_events(code, bars, spec))
        if number % 5 == 0 or number == len(chunks):
            print(f"{market} chunks {number}/{len(chunks)}: {len(events):,} episodes")
    return sorted(events, key=lambda event: (event.signal_date, event.code)), dict(quality)


async def _benchmark(market: str) -> list[tuple[dt.date, float]]:
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
            return [(row.date, float(row.dsex)) for row in rows if row.dsex and row.dsex > 0]
        rows = (
            await session.execute(
                select(DailyBar.date, DailyBar.close, DailyBar.adjusted_close)
                .where(DailyBar.market == "US", DailyBar.code == "SPY")
                .order_by(DailyBar.date)
            )
        ).all()
        return [
            (row.date, float(row.adjusted_close or row.close))
            for row in rows
            if (row.adjusted_close or row.close) and (row.adjusted_close or row.close) > 0
        ]


def _benchmark_returns(
    rows: list[tuple[dt.date, float]],
    horizons: tuple[int, ...],
) -> dict[tuple[dt.date, int], float]:
    output: dict[tuple[dt.date, int], float] = {}
    for index, (date, value) in enumerate(rows):
        for horizon in horizons:
            if index + horizon < len(rows):
                output[(date, horizon)] = rows[index + horizon][1] / value - 1.0
    return output


def _rounded(value: float | None, digits: int = 4) -> float | None:
    return None if value is None or not math.isfinite(value) else round(value, digits)


def _summary(
    events: list[OysterResearchEvent],
    benchmark: dict[tuple[dt.date, int], float],
    spec: OysterResearchSpec,
) -> dict[str, Any]:
    output: dict[str, Any] = {
        "events": len(events),
        "codes": len({event.code for event in events}),
        "signal_dates": len({event.signal_date for event in events}),
        "median_turnover": _rounded(
            statistics.median(event.average_turnover for event in events) if events else None
        ),
        "median_strength": _rounded(
            statistics.median(event.strength_score for event in events) if events else None
        ),
        "horizons": {},
    }
    for horizon in spec.outcome_sessions:
        completed = [
            event for event in events if event.close_returns.get(horizon) is not None
        ]
        returns = [float(event.close_returns[horizon]) for event in completed]
        high_returns = [float(event.maximum_high_returns[horizon]) for event in completed]
        low_returns = [float(event.minimum_low_returns[horizon]) for event in completed]
        paired = [
            (float(event.close_returns[horizon]), benchmark[(event.signal_date, horizon)])
            for event in completed
            if (event.signal_date, horizon) in benchmark
        ]
        output["horizons"][str(horizon)] = {
            "completed": len(completed),
            "mean_close_return_pct": _rounded(
                statistics.fmean(returns) * 100 if returns else None
            ),
            "median_close_return_pct": _rounded(
                statistics.median(returns) * 100 if returns else None
            ),
            "positive_close_rate_pct": _rounded(
                sum(value > 0 for value in returns) / len(returns) * 100 if returns else None
            ),
            "median_maximum_high_pct": _rounded(
                statistics.median(high_returns) * 100 if high_returns else None
            ),
            "median_minimum_low_pct": _rounded(
                statistics.median(low_returns) * 100 if low_returns else None
            ),
            "mean_benchmark_excess_pct": _rounded(
                statistics.fmean(value - reference for value, reference in paired) * 100
                if paired
                else None
            ),
        }
    maximum_horizon = max(spec.outcome_sessions)
    for threshold in spec.opportunity_thresholds:
        key = f"{maximum_horizon}s_{round(threshold * 100):d}pct"
        values = [event.opportunities[key] for event in events if event.opportunities[key] is not None]
        output[f"opportunity_rate_{key}_pct"] = _rounded(
            sum(bool(value) for value in values) / len(values) * 100 if values else None
        )
    return output


def _payload(
    market: str,
    codes: list[str],
    events: list[OysterResearchEvent],
    quality: dict[str, int],
    benchmark_rows: list[tuple[dt.date, float]],
    spec: OysterResearchSpec,
) -> dict[str, Any]:
    benchmark = _benchmark_returns(benchmark_rows, spec.outcome_sessions)
    windows = {
        name: _summary(
            [event for event in events if _window(market, event.signal_date) == name],
            benchmark,
            spec,
        )
        for name in ("discovery", "validation", "holdout")
    }
    return {
        "experiment": spec.as_dict(),
        "market": market,
        "study_type": "causal completed-daily-bar event study; not an executable strategy",
        "data": {
            "eligible_current_symbols": len(codes),
            "load_start": _load_start(market),
            "quality_exclusions": quality,
            "survivorship": (
                "current listed/product-eligible universe only; positive results are an upper bound"
            ),
            "timeframe_mismatch": (
                "source deck uses two/four-hour bars; this study tests a daily approximation"
            ),
        },
        "windows": windows,
        "all": _summary(events, benchmark, spec),
        "recent_events": [
            {
                "code": event.code,
                "signal_date": event.signal_date,
                "cross_date": event.cross_date,
                "phase": event.phase,
                "signal_close": _rounded(event.signal_close),
                "strength": event.strength_score,
            }
            for event in events[-50:]
        ],
        "admission_rule": (
            "Do not label as predictive or create a strategy from this artifact. Promotion requires "
            "a separate matched-control test, stable validation/holdout lift, executable entry and "
            "exit rules, costs, capacity, and survivorship-complete data."
        ),
    }


async def _run(args: argparse.Namespace) -> None:
    market = args.market.upper()
    spec = _spec(market)
    codes = await _codes(market)
    events, quality = await _events(market, codes, spec)
    benchmark = await _benchmark(market)
    payload = _payload(market, codes, events, quality, benchmark, spec)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps(payload["all"], indent=2))
    print(f"wrote {args.output}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--market", choices=("DSE", "US"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        asyncio.run(_run(args))
    finally:
        asyncio.run(dispose_engine())


if __name__ == "__main__":
    main()
