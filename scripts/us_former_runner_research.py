"""Evaluate the STAK-like former-runner watch state on stored US EOD history.

This is an opportunity study, not a trade backtest. Atlas has no US intraday bars, so the script
cannot know whether a previous-day-high trigger held above session VWAP or whether a stop happened
before or after the trigger inside a daily candle.

Usage:

    uv run python scripts/us_former_runner_research.py \
        --output /tmp/us-former-runner-reactivation-v1.json
"""

# ruff: noqa: E402

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import statistics
import sys
from collections import defaultdict
from dataclasses import asdict
from pathlib import Path
from typing import Any

from sqlalchemy import select, text

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from research.edge_discovery.former_runner import (
    ControlObservation,
    FormerRunnerEvent,
    FormerRunnerSpec,
    RunnerBar,
    control_observations,
    scan_former_runner,
)

from bulls.core.db import dispose_engine, get_sessionmaker
from bulls.core.models import DailyBar, SecurityMaster

ANALYSIS_START = dt.date(2023, 1, 1)
LOAD_START = dt.date(2022, 10, 1)
DISCOVERY_END = dt.date(2024, 12, 31)
VALIDATION_END = dt.date(2025, 12, 31)
CHUNK_SIZE = 200


async def _codes() -> list[str]:
    sessionmaker = get_sessionmaker()
    async with sessionmaker()() as session:
        return sorted(
            set(
                await session.scalars(
                    select(SecurityMaster.symbol).where(
                        SecurityMaster.market == "US",
                        SecurityMaster.instrument_type.in_(("common_stock", "adr")),
                    )
                )
            )
        )


async def _bars_for_chunk(codes: list[str]) -> dict[str, list[RunnerBar]]:
    sessionmaker = get_sessionmaker()
    async with sessionmaker()() as session:
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
                    DailyBar.market == "US",
                    DailyBar.code.in_(codes),
                    DailyBar.date >= LOAD_START,
                )
                .order_by(DailyBar.code, DailyBar.date)
            )
        ).all()
    grouped: dict[str, list[RunnerBar]] = defaultdict(list)
    for row in rows:
        if min(row.open or 0, row.high or 0, row.low or 0, row.close or 0) <= 0:
            continue
        if row.adjusted_close is None or row.adjusted_close <= 0:
            continue
        factor = float(row.adjusted_close) / float(row.close)
        grouped[row.code].append(
            RunnerBar(
                date=row.date,
                open=float(row.open) * factor,
                high=float(row.high) * factor,
                low=float(row.low) * factor,
                close=float(row.close) * factor,
                volume=float(row.volume or 0),
            )
        )
    return dict(grouped)


def _chunks(values: list[str]) -> list[list[str]]:
    return [values[index : index + CHUNK_SIZE] for index in range(0, len(values), CHUNK_SIZE)]


async def _find_events(
    codes: list[str],
    spec: FormerRunnerSpec,
) -> list[FormerRunnerEvent]:
    events: list[FormerRunnerEvent] = []
    chunks = _chunks(codes)
    for number, chunk in enumerate(chunks, start=1):
        grouped = await _bars_for_chunk(chunk)
        for code, bars in grouped.items():
            events.extend(
                event
                for event in scan_former_runner(code, bars, spec)
                if event.watch_date >= ANALYSIS_START
            )
        if number % 5 == 0 or number == len(chunks):
            print(f"event pass {number}/{len(chunks)}: {len(events)} watches")
    return sorted(events, key=lambda event: (event.watch_date, event.code))


async def _control_aggregates(
    codes: list[str],
    dates: set[dt.date],
    spec: FormerRunnerSpec,
) -> tuple[
    dict[tuple[dt.date, int, int], list[float]],
    dict[tuple[dt.date, int, int, str], list[float]],
]:
    aggregate: dict[tuple[dt.date, int, int], list[float]] = defaultdict(
        lambda: [0.0, 0.0, 0.0]
    )
    by_code: dict[tuple[dt.date, int, int, str], list[float]] = defaultdict(
        lambda: [0.0, 0.0, 0.0]
    )
    chunks = _chunks(codes)
    for number, chunk in enumerate(chunks, start=1):
        grouped = await _bars_for_chunk(chunk)
        for code, bars in grouped.items():
            for row in control_observations(code, bars, dates, spec):
                _accumulate_control(aggregate, by_code, row)
        if number % 5 == 0 or number == len(chunks):
            print(f"control pass {number}/{len(chunks)}")
    return dict(aggregate), dict(by_code)


def _accumulate_control(
    aggregate: dict[tuple[dt.date, int, int], list[float]],
    by_code: dict[tuple[dt.date, int, int, str], list[float]],
    row: ControlObservation,
) -> None:
    key = (row.date, row.liquidity_band, row.volatility_band)
    code_key = (*key, row.code)
    for target in (aggregate[key], by_code[code_key]):
        target[0] += 1
        target[1] += float(row.primary_success)
        target[2] += row.maximum_expansion


def _matched_control_rate(
    event: FormerRunnerEvent,
    aggregate: dict[tuple[dt.date, int, int], list[float]],
    by_code: dict[tuple[dt.date, int, int, str], list[float]],
) -> float | None:
    key = (event.watch_date, event.liquidity_band, event.volatility_band)
    total = aggregate.get(key)
    own = by_code.get((*key, event.code), [0.0, 0.0, 0.0])
    if total is None or total[0] - own[0] <= 0:
        return None
    return (total[1] - own[1]) / (total[0] - own[0])


def _window(date: dt.date) -> str:
    if date <= DISCOVERY_END:
        return "discovery_2023_2024"
    if date <= VALIDATION_END:
        return "validation_2025"
    return "retrospective_2026"


def _summary(
    events: list[FormerRunnerEvent],
    aggregate: dict[tuple[dt.date, int, int], list[float]],
    by_code: dict[tuple[dt.date, int, int, str], list[float]],
    *,
    exclude_code: str | None = None,
) -> dict[str, Any]:
    completed = [
        event
        for event in events
        if event.outcome_complete
        and event.primary_success is not None
        and (exclude_code is None or event.code != exclude_code)
    ]
    controls = [
        rate
        for event in completed
        if (
            rate := _matched_control_rate(event, aggregate, by_code)
        )
        is not None
    ]
    event_with_controls = [
        event
        for event in completed
        if _matched_control_rate(event, aggregate, by_code) is not None
    ]
    precision = (
        sum(bool(event.primary_success) for event in completed) / len(completed)
        if completed
        else None
    )
    secondary_precision = (
        sum(bool(event.secondary_success) for event in completed) / len(completed)
        if completed
        else None
    )
    matched_rate = statistics.fmean(controls) if controls else None
    expansions = [
        event.maximum_expansion
        for event in completed
        if event.maximum_expansion is not None
    ]
    per_event_lift = [
        float(event.primary_success)
        - float(_matched_control_rate(event, aggregate, by_code))
        for event in event_with_controls
    ]
    return {
        "completed_events": len(completed),
        "signal_dates": len({event.watch_date for event in completed}),
        "codes": len({event.code for event in completed}),
        "primary_opportunity_rate": precision,
        "secondary_opportunity_rate": secondary_precision,
        "matched_control_rate": matched_rate,
        "matched_lift_pp": (
            statistics.fmean(per_event_lift) * 100 if per_event_lift else None
        ),
        "median_maximum_expansion_pct": (
            statistics.median(expansions) * 100 if expansions else None
        ),
        "average_maximum_expansion_pct": (
            statistics.fmean(expansions) * 100 if expansions else None
        ),
    }


def _payload(
    events: list[FormerRunnerEvent],
    aggregate: dict[tuple[dt.date, int, int], list[float]],
    by_code: dict[tuple[dt.date, int, int, str], list[float]],
    spec: FormerRunnerSpec,
    code_count: int,
) -> dict[str, Any]:
    windows = {
        name: _summary(
            [event for event in events if _window(event.watch_date) == name],
            aggregate,
            by_code,
        )
        for name in ("discovery_2023_2024", "validation_2025", "retrospective_2026")
    }
    all_summary = _summary(events, aggregate, by_code)
    all_ex_stak = _summary(events, aggregate, by_code, exclude_code="STAK")
    stak = next(
        (
            event
            for event in events
            if event.code == "STAK" and event.watch_date == dt.date(2026, 7, 23)
        ),
        None,
    )
    return {
        "experiment": spec.as_dict(),
        "study_type": "EOD opportunity diagnostic; not a trade backtest",
        "data": {
            "analysis_start": ANALYSIS_START,
            "load_start": LOAD_START,
            "current_common_stock_and_adr_codes": code_count,
            "survivorship": (
                "total current-survivor universe; positive results are an upper bound"
            ),
            "us_intraday_rows": 0,
        },
        "windows": windows,
        "all_completed": all_summary,
        "all_completed_excluding_stak": all_ex_stak,
        "pending_or_early_resolved": [
            asdict(event) for event in events if not event.outcome_complete
        ],
        "stak_case": asdict(stak) if stak else None,
        "decision": {
            "paper_trade": False,
            "agent_decision": False,
            "reason": (
                "Daily bars can validate an overnight watch state only. Live ignition requires "
                "US intraday price/volume, session VWAP, spread and event ordering."
            ),
        },
    }


async def async_main(output: Path) -> None:
    try:
        spec = FormerRunnerSpec()
        codes = await _codes()
        print(f"Scanning {len(codes):,} current common-stock/ADR symbols")
        events = await _find_events(codes, spec)
        dates = {event.watch_date for event in events if event.outcome_complete}
        aggregate, by_code = await _control_aggregates(codes, dates, spec)
        payload = _payload(events, aggregate, by_code, spec, len(codes))
        output.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(
            output.write_text,
            json.dumps(payload, indent=2, default=str) + "\n",
        )
        print(json.dumps(payload["windows"], indent=2, default=str))
        print(f"STAK detected: {payload['stak_case'] is not None}")
        print(f"Wrote {output}")
    finally:
        await dispose_engine()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("/tmp/us-former-runner-reactivation-v1.json"),
    )
    args = parser.parse_args()
    asyncio.run(async_main(args.output))


if __name__ == "__main__":
    main()
