"""Read-only audit of the DSE Daily Shortlist archive and its historical follow-through.

The command does not update rankings, archives, or strategy state. It reconciles every archived
row to source bars, measures independent ticker episodes, and compares each daily five-name slate
with the same session's non-selected eligible universe.

    uv run python scripts/audit_dse_daily_shortlist.py
"""

from __future__ import annotations

import asyncio
import datetime as dt
import json
from collections import defaultdict
from dataclasses import asdict

from sqlalchemy import or_, select

from bulls.analytics.daily_shortlist_performance import (
    BenchmarkClose,
    ShortlistAppearance,
    ShortlistPortfolioPolicy,
    ShortlistPriceBar,
    eligible_universe_by_date,
    evaluate_matched_eligible_control,
    evaluate_shortlist_performance,
    simulate_shortlist_portfolio,
)
from bulls.core.db import bind_tenant_context, dispose_engine, get_sessionmaker
from bulls.core.models import DailyBar, DailyShortlistState, MarketSummary, Symbol

TENANT_ID = "bullsofdhaka"
MARKET = "DSE"


def _json_default(value: object) -> str:
    if isinstance(value, (dt.date, dt.datetime)):
        return value.isoformat()
    raise TypeError(f"Cannot serialize {type(value).__name__}")


def _archive_integrity(
    snapshots: list[DailyShortlistState],
    bars: list[DailyBar],
    market_dates: list[dt.date],
) -> dict[str, object]:
    bars_by_key = {(bar.code, bar.date): bar for bar in bars}
    date_index = {date: index for index, date in enumerate(market_dates)}
    snapshots_by_date: dict[dt.date, list[DailyShortlistState]] = defaultdict(list)
    counters = {
        "matched_selection_closes": 0,
        "missing_selection_bars": 0,
        "close_mismatches": 0,
        "matched_selection_moves": 0,
        "missing_move_inputs": 0,
        "move_mismatches": 0,
    }

    for row in snapshots:
        snapshots_by_date[row.as_of_date].append(row)
        bar = bars_by_key.get((row.code, row.as_of_date))
        if bar is None:
            counters["missing_selection_bars"] += 1
            continue
        counters["matched_selection_closes"] += 1
        if abs(bar.close - row.close) > max(0.01, abs(row.close) * 0.0001):
            counters["close_mismatches"] += 1

        index = date_index.get(row.as_of_date)
        previous = (
            bars_by_key.get((row.code, market_dates[index - 1]))
            if index is not None and index > 0
            else None
        )
        if row.change_pct is None or previous is None or previous.close <= 0:
            counters["missing_move_inputs"] += 1
            continue
        counters["matched_selection_moves"] += 1
        expected_move = (bar.close / previous.close - 1.0) * 100.0
        if abs(expected_move - row.change_pct) > 0.02:
            counters["move_mismatches"] += 1

    incomplete_sessions = 0
    invalid_rank_sessions = 0
    for rows in snapshots_by_date.values():
        if len(rows) != max(row.slate_size for row in rows):
            incomplete_sessions += 1
        if sorted(row.rank for row in rows) != list(range(1, len(rows) + 1)):
            invalid_rank_sessions += 1

    return {
        "rows": len(snapshots),
        "sessions": len(snapshots_by_date),
        "forward_rows": sum(row.evidence_mode == "forward" for row in snapshots),
        "reconstructed_rows": sum(row.evidence_mode == "reconstructed" for row in snapshots),
        **counters,
        "incomplete_sessions": incomplete_sessions,
        "invalid_rank_sessions": invalid_rank_sessions,
        "methodology_versions": sorted({row.methodology_version for row in snapshots}),
    }


async def _load() -> tuple[
    list[DailyShortlistState],
    list[DailyBar],
    list[MarketSummary],
    set[str],
]:
    async with get_sessionmaker()() as session:
        await bind_tenant_context(session, TENANT_ID)
        snapshots = list(
            await session.scalars(
                select(DailyShortlistState)
                .where(DailyShortlistState.market == MARKET)
                .order_by(
                    DailyShortlistState.as_of_date,
                    DailyShortlistState.rank,
                    DailyShortlistState.code,
                )
            )
        )
        if not snapshots:
            return [], [], [], set()
        clean_codes = set(
            await session.scalars(
                select(Symbol.code).where(
                    Symbol.market == MARKET,
                    Symbol.is_active.is_(True),
                    Symbol.is_hidden.is_(False),
                    Symbol.data_status == "ready",
                    or_(Symbol.category.is_(None), Symbol.category != "Z"),
                )
            )
        )
        bars = list(
            await session.scalars(
                select(DailyBar)
                .where(DailyBar.market == MARKET)
                .order_by(DailyBar.code, DailyBar.date)
            )
        )
        summaries = list(
            await session.scalars(
                select(MarketSummary)
                .where(
                    MarketSummary.market == MARKET,
                    MarketSummary.dsex.is_not(None),
                    MarketSummary.dsex > 0,
                )
                .order_by(MarketSummary.date)
            )
        )
    return snapshots, bars, summaries, clean_codes


async def run() -> None:
    snapshots, database_bars, summaries, clean_codes = await _load()
    if not snapshots:
        print(json.dumps({"market": MARKET, "error": "No archived shortlist rows"}))
        return

    bars = [
        ShortlistPriceBar(
            code=bar.code,
            date=bar.date,
            open=bar.open,
            high=bar.high,
            low=bar.low,
            close=bar.close,
            volume=bar.volume,
        )
        for bar in database_bars
    ]
    appearances = [
        ShortlistAppearance(
            code=row.code,
            as_of=row.as_of_date,
            close=row.close,
            rank=row.rank,
            evidence_mode=row.evidence_mode,
        )
        for row in snapshots
    ]
    market_dates = sorted({bar.date for bar in bars})
    benchmark = [
        BenchmarkClose(date=row.date, close=float(row.dsex))
        for row in summaries
        if row.dsex is not None
    ]
    performance = evaluate_shortlist_performance(
        appearances=appearances,
        bars=bars,
        benchmark=benchmark,
        market_dates=market_dates,
    )
    rank_performance = {
        str(rank): asdict(
            evaluate_shortlist_performance(
                appearances=[row for row in appearances if row.rank == rank],
                bars=bars,
                benchmark=benchmark,
                market_dates=market_dates,
            )
        )
        for rank in sorted({row.rank for row in appearances})
    }
    eligible = eligible_universe_by_date(
        bars,
        selection_dates=[row.as_of_date for row in snapshots],
        eligible_codes=clean_codes,
    )
    matched_control = evaluate_matched_eligible_control(
        appearances=appearances,
        bars=bars,
        market_dates=market_dates,
        eligible_by_date=eligible,
    )
    rank_one_base = ShortlistPortfolioPolicy(
        key="dse_daily_shortlist_rank1_hold3_v1",
    )
    rank_one_stress = ShortlistPortfolioPolicy(
        key="dse_daily_shortlist_rank1_hold3_v1_doubled_cost",
        fee_rate=rank_one_base.fee_rate * 2,
        slippage_rate=rank_one_base.slippage_rate * 2,
    )
    all_ranks_base = ShortlistPortfolioPolicy(
        key="dse_daily_shortlist_all_ranks_hold3_sensitivity_v1",
        included_ranks=(1, 2, 3, 4, 5),
    )
    all_ranks_stress = ShortlistPortfolioPolicy(
        key="dse_daily_shortlist_all_ranks_hold3_sensitivity_v1_doubled_cost",
        included_ranks=(1, 2, 3, 4, 5),
        fee_rate=all_ranks_base.fee_rate * 2,
        slippage_rate=all_ranks_base.slippage_rate * 2,
    )
    forward_appearances = [item for item in appearances if item.evidence_mode == "forward"]
    portfolio_diagnostics = {
        "policy_status": {
            "classification": "post_audit_hypothesis_not_validation",
            "registered_after": dt.date(2026, 8, 11),
            "fresh_forward_starts_after": dt.date(2026, 8, 11),
            "orders_enabled": False,
            "minimum_matured_signal_dates": 60,
        },
        "all_archived_rank1_base": asdict(
            simulate_shortlist_portfolio(
                appearances=appearances,
                bars=bars,
                benchmark=benchmark,
                policy=rank_one_base,
                market_dates=market_dates,
                evidence_scope="all_archived_mixed_reconstructed_and_forward",
            )
        ),
        "all_archived_rank1_doubled_cost": asdict(
            simulate_shortlist_portfolio(
                appearances=appearances,
                bars=bars,
                benchmark=benchmark,
                policy=rank_one_stress,
                market_dates=market_dates,
                evidence_scope="all_archived_mixed_reconstructed_and_forward",
            )
        ),
        "existing_forward_rank1_base": asdict(
            simulate_shortlist_portfolio(
                appearances=forward_appearances,
                bars=bars,
                benchmark=benchmark,
                policy=rank_one_base,
                market_dates=market_dates,
                evidence_scope="existing_forward_archive_before_policy_registration",
            )
        ),
        "existing_forward_rank1_doubled_cost": asdict(
            simulate_shortlist_portfolio(
                appearances=forward_appearances,
                bars=bars,
                benchmark=benchmark,
                policy=rank_one_stress,
                market_dates=market_dates,
                evidence_scope="existing_forward_archive_before_policy_registration",
            )
        ),
        "all_archived_all_ranks_sensitivity": asdict(
            simulate_shortlist_portfolio(
                appearances=appearances,
                bars=bars,
                benchmark=benchmark,
                policy=all_ranks_base,
                market_dates=market_dates,
                evidence_scope="sensitivity_only_not_primary_hypothesis",
            )
        ),
        "all_archived_all_ranks_doubled_cost_sensitivity": asdict(
            simulate_shortlist_portfolio(
                appearances=appearances,
                bars=bars,
                benchmark=benchmark,
                policy=all_ranks_stress,
                market_dates=market_dates,
                evidence_scope="sensitivity_only_not_primary_hypothesis",
            )
        ),
    }

    payload = {
        "generated_at": dt.datetime.now(dt.UTC),
        "tenant": TENANT_ID,
        "market": MARKET,
        "latest_source_bar": max(bar.date for bar in bars),
        "latest_benchmark": max(row.date for row in benchmark),
        "active_clean_codes": len(clean_codes),
        "archive_integrity": _archive_integrity(
            snapshots,
            database_bars,
            market_dates,
        ),
        "performance": asdict(performance),
        "rank_performance": rank_performance,
        "matched_control": asdict(matched_control),
        "portfolio_diagnostics": portfolio_diagnostics,
        "limitations": [
            "Reconstructed rows include only currently listed names and are survivor-biased.",
            "Selection-close returns are follow-through, not executable returns.",
            "Next-open figures are gross and exclude fees, slippage, and fill uncertainty.",
            "The matched universe uses current active/security classifications.",
        ],
    }
    print(json.dumps(payload, indent=2, default=_json_default))


async def main() -> None:
    try:
        await run()
    finally:
        await dispose_engine()


if __name__ == "__main__":
    asyncio.run(main())
