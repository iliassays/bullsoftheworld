"""Reconstruct historical squeeze-taxonomy states from stored bars.

Why this is a separate module from ``squeeze_scan``
--------------------------------------------------
The nightly scan reads ``ticker_analytics``, which is keyed ``(market, code)`` — one row per
symbol, holding *today's* values. It is not a history. Calling ``analytics.compute_all`` with a
past ``as_of_date`` would therefore overwrite the live row that the screener, Ideas and the scan
all read, and stamp ``cap_tier_observations`` from the overwritten values. This module instead
computes analytics **in memory** with the pure ``bulls.analytics.engine.compute`` over
date-sliced bars, and writes nothing but ``squeeze_daily_states``.

What a reconstruction can and cannot show
-----------------------------------------
Every row is written with ``evidence_mode="reconstructed"`` and must never be quoted as forward
performance, for reasons that live in the data rather than the code:

* **Survivorship.** The store holds only currently-listed names (US: ~11k active against ~50
  inactive). A June reconstruction therefore excludes every company that has since delisted, so
  measured outcomes are biased upward. DSE has no delistings in the store at all.
* **Inputs that were never recorded.** Cap tier only began accumulating per-session on
  2026-07-17 (US) / 2026-07-23 (DSE), so reconstructed rows leave it null rather than stamping
  today's tier onto a past date. Fundamentals and ownership are likewise current-valued.
* **Families needing non-price inputs are skipped.** ``supply_constrained_breakout`` depends on
  float and sponsor concentration; reconstructing it would mean asserting today's ownership on a
  historical session.
* **DSE prices are unadjusted**, so a bonus or rights ex-date shows up as a real price move.

Its legitimate use is diagnostic: does the taxonomy progress sensibly, are the MFE/MAE
distributions plausible, is anything obviously broken. Not hit rates.

One-shot:
    uv run python -m ingestion.squeeze_backfill DSE --sessions 40
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import logging
from collections import defaultdict
from dataclasses import dataclass

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from bulls.analytics.adjustments import adjustment_factor
from bulls.analytics.engine import compute
from bulls.analytics.research_strategy import RISK_POLICIES
from bulls.analytics.squeeze_monitor import (
    METHODOLOGY_VERSION,
    SqueezeBar,
    SqueezeInputs,
    evaluate_compression_breakout,
    evaluate_failed_breakdown,
    resolve_episode,
    should_archive_transition,
)
from bulls.core.db import get_sessionmaker
from bulls.core.models import DailyBar, SqueezeDailyState
from ingestion.db_batch import parameter_safe_batches

log = logging.getLogger(__name__)

# Only price/volume families can be honestly reconstructed. supply_constrained_breakout needs
# float and sponsor history that does not exist.
_EVALUATORS = {
    "compression_breakout": evaluate_compression_breakout,
    "failed_breakdown_reversal": evaluate_failed_breakdown,
}
_WARMUP_SESSIONS = 260  # a 200-session average plus headroom must exist before the first output
_MINIMUM_SESSIONS = 60


@dataclass(frozen=True, slots=True)
class _EngineBar:
    """Adapts one adjusted bar to the analytics engine's BarLike protocol."""

    market: str
    code: str
    date: dt.date
    high: float
    low: float
    close: float
    volume: int


def _strategy_bar(row) -> SqueezeBar | None:
    """Adjusted bar, or None when the row cannot be trusted."""

    if min(row.open or 0, row.high or 0, row.low or 0, row.close or 0) <= 0:
        return None
    adjustment = adjustment_factor(float(row.close), row.adjusted_close)
    if adjustment is None:
        return None
    return SqueezeBar(
        date=row.date,
        open=float(row.open) * adjustment,
        high=float(row.high) * adjustment,
        low=float(row.low) * adjustment,
        close=float(row.close) * adjustment,
        volume=float(row.volume or 0),
    )


def _forward_protected(
    cutoffs: dict[tuple[str, str], dt.date],
    *,
    code: str,
    family: str,
    as_of: dt.date,
) -> bool:
    """Return whether replay would cross a live evidence boundary."""

    cutoff = cutoffs.get((code, family))
    return cutoff is not None and as_of >= cutoff


def _replacement_delete(market: str, start: dt.date, end: dt.date):
    """Delete only replay evidence inside one requested replacement window."""

    return delete(SqueezeDailyState).where(
        SqueezeDailyState.market == market,
        SqueezeDailyState.as_of_date >= start,
        SqueezeDailyState.as_of_date <= end,
        SqueezeDailyState.evidence_mode == "reconstructed",
    )


async def run_squeeze_backfill(
    market: str, *, sessions: int, replace: bool = False
) -> dict[str, int]:
    """Reconstruct the most recent ``sessions`` completed sessions for ``market``."""

    market = market.upper()
    policy = RISK_POLICIES[market]
    sessionmaker = get_sessionmaker()

    async with sessionmaker() as session:
        all_dates = list(
            await session.scalars(
                select(DailyBar.date)
                .where(DailyBar.market == market)
                .distinct()
                .order_by(DailyBar.date.desc())
                .limit(sessions + _WARMUP_SESSIONS)
            )
        )
        if not all_dates:
            return {
                "sessions": 0,
                "archived": 0,
                "deleted_reconstructed": 0,
                "skipped_existing": 0,
            }
        ordered = sorted(all_dates)
        target_dates = ordered[-sessions:]
        window_start = ordered[0]

        rows = (
            await session.execute(
                select(
                    SqueezeDailyState.code,
                    SqueezeDailyState.family,
                    SqueezeDailyState.as_of_date,
                    SqueezeDailyState.evidence_mode,
                ).where(
                    SqueezeDailyState.market == market,
                    SqueezeDailyState.as_of_date >= target_dates[0],
                )
            )
        ).all()
        existing = {(row.code, row.family, row.as_of_date) for row in rows}
        forward_cutoffs: dict[tuple[str, str], dt.date] = {}
        for row in rows:
            if row.evidence_mode != "forward":
                continue
            pair = (row.code, row.family)
            forward_cutoffs[pair] = min(
                row.as_of_date,
                forward_cutoffs.get(pair, row.as_of_date),
            )

        # Liquidity gate uses the same mandate floor as the scan, measured on the reconstruction's
        # own window rather than on today's analytics row.
        bars_by_code: dict[str, list[SqueezeBar]] = defaultdict(list)
        codes = list(
            await session.scalars(
                select(DailyBar.code)
                .where(DailyBar.market == market, DailyBar.date >= window_start)
                .group_by(DailyBar.code)
                .having(
                    func.avg(DailyBar.close * DailyBar.volume)
                    >= policy.minimum_average_daily_value_mn * 1_000_000
                )
            )
        )
        for start in range(0, len(codes), 300):
            chunk = codes[start : start + 300]
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
                        DailyBar.code.in_(chunk),
                        DailyBar.date >= window_start,
                    )
                    .order_by(DailyBar.code, DailyBar.date)
                )
            ).all()
            for row in rows:
                bar = _strategy_bar(row)
                if bar is not None:
                    bars_by_code[row.code].append(bar)

    payloads: list[dict] = []
    skipped = 0
    # Walk sessions forward so each session's prior state is the one this run just derived —
    # the same causal chain the nightly scan builds, never a peek at a later state.
    prior_by_pair: dict[tuple[str, str], tuple[str, dt.date, float | None]] = {}
    for as_of in target_dates:
        for code, history in bars_by_code.items():
            window = [bar for bar in history if bar.date <= as_of]
            if len(window) < _MINIMUM_SESSIONS or window[-1].date != as_of:
                continue
            # Point-in-time analytics: computed from this window only, in memory, never written.
            snapshot = compute(
                [
                    _EngineBar(
                        market=market,
                        code=code,
                        date=bar.date,
                        high=bar.high,
                        low=bar.low,
                        close=bar.close,
                        volume=int(bar.volume),
                    )
                    for bar in window
                ]
            )
            for family, evaluate in _EVALUATORS.items():
                prior = prior_by_pair.get((code, family))
                prior_state = prior[0] if prior is not None else "none"
                inputs = SqueezeInputs(
                    market=market,  # type: ignore[arg-type]
                    code=code,
                    bars=window[-130:],
                    last_close=window[-1].close,
                    sma_50=snapshot.sma_50,
                    sma_200=snapshot.sma_200,
                    pct_from_52w_high=snapshot.pct_from_52w_high,
                    relative_volume=snapshot.relative_volume,
                    rel_volume_5d=snapshot.rel_volume_5d,
                    cmf_20=snapshot.cmf_20,
                    obv_slope=snapshot.obv_slope,
                    avg_volume_20=snapshot.avg_volume_20,
                    prior_state=prior_state,  # type: ignore[arg-type]
                    prior_trigger_price=prior[2] if prior is not None else None,
                )
                assessment = evaluate(inputs)
                if not should_archive_transition(
                    state=assessment.state,
                    prior_state=prior_state,
                ):
                    prior_by_pair.pop((code, family), None)
                    continue
                first_discovered, previous_state = resolve_episode(
                    has_prior=prior is not None,
                    prior_state=prior_state,
                    prior_first_discovered=prior[1] if prior is not None else None,
                    session_date=as_of,
                )
                prior_by_pair[(code, family)] = (
                    assessment.state,
                    first_discovered,
                    assessment.trigger_price,
                )
                # Once live collection begins, that ticker/family timeline is immutable. A replay
                # must not fill gaps after the cutoff or replace a live row with hindsight data.
                if _forward_protected(
                    forward_cutoffs,
                    code=code,
                    family=family,
                    as_of=as_of,
                ):
                    skipped += 1
                    continue
                if not replace and (code, family, as_of) in existing:
                    skipped += 1
                    continue
                payloads.append(
                    {
                        "market": market,
                        "code": code,
                        "family": family,
                        "as_of_date": as_of,
                        "state": assessment.state,
                        "previous_state": previous_state,
                        "reason": assessment.reason[:500],
                        "setup_price": assessment.setup_price,
                        "trigger_price": assessment.trigger_price,
                        "invalidation_price": assessment.invalidation_price,
                        "risk_per_share": assessment.risk_per_share,
                        "planning_objective_price": assessment.planning_objective_price,
                        "first_discovered_on": first_discovered,
                        # Left null on purpose: no per-session capitalization record exists for
                        # historical dates, and today's tier is not that session's tier.
                        "cap_tier": None,
                        "average_dollar_volume_mn": None,
                        "evidence_mode": "reconstructed",
                        "evidence": {
                            "supporting": assessment.supporting_evidence,
                            "counter": assessment.counter_evidence,
                            "data_quality": [
                                *assessment.data_quality,
                                "Reconstructed from stored bars, not collected on this session. "
                                "Only currently-listed symbols exist in the store, so delisted "
                                "names are absent and outcomes are biased upward.",
                            ],
                            "missing": [
                                *assessment.missing_evidence,
                                "Capitalization tier and liquidity capacity were not recorded "
                                "for this historical session.",
                            ],
                            "expected_holding": assessment.expected_holding,
                        },
                        "methodology_version": METHODOLOGY_VERSION,
                    }
                )

    archived = 0
    deleted_reconstructed = 0
    if payloads or replace:
        async with sessionmaker() as session:
            if replace:
                # Replacement means "this methodology is the complete reconstruction for the
                # requested window", not "upsert whatever still emits". Delete the old replay
                # rows in the same transaction so obsolete v1/v2 classifications disappear while
                # a failed rebuild rolls the deletion back. Forward rows are never eligible.
                result = await session.execute(
                    _replacement_delete(
                        market,
                        target_dates[0],
                        target_dates[-1],
                    )
                )
                deleted_reconstructed = max(result.rowcount or 0, 0)
            for batch in parameter_safe_batches(payloads):
                statement = pg_insert(SqueezeDailyState).values(batch)
                await session.execute(
                    statement.on_conflict_do_update(
                        index_elements=["market", "code", "family", "as_of_date"],
                        set_={
                            column: getattr(statement.excluded, column)
                            for column in (
                                "state",
                                "previous_state",
                                "reason",
                                "setup_price",
                                "trigger_price",
                                "invalidation_price",
                                "risk_per_share",
                                "planning_objective_price",
                                "first_discovered_on",
                                "cap_tier",
                                "average_dollar_volume_mn",
                                "evidence_mode",
                                "evidence",
                                "methodology_version",
                            )
                        },
                        where=SqueezeDailyState.evidence_mode == "reconstructed",
                    )
                )
                archived += len(batch)
            await session.commit()
    log.info(
        "squeeze_backfill market=%s sessions=%s archived=%s deleted_reconstructed=%s skipped=%s",
        market,
        len(target_dates),
        archived,
        deleted_reconstructed,
        skipped,
    )
    return {
        "sessions": len(target_dates),
        "archived": archived,
        "deleted_reconstructed": deleted_reconstructed,
        "skipped_existing": skipped,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Reconstruct historical squeeze states (labelled, never forward evidence)"
    )
    parser.add_argument("market", choices=["DSE", "US"])
    parser.add_argument("--sessions", type=int, default=40)
    parser.add_argument(
        "--replace",
        action="store_true",
        help="overwrite reconstructed rows; live forward timelines remain immutable",
    )
    arguments = parser.parse_args()
    stats = asyncio.run(
        run_squeeze_backfill(
            arguments.market, sessions=arguments.sessions, replace=arguments.replace
        )
    )
    print(
        f"[squeeze-backfill] {arguments.market}: sessions={stats['sessions']} "
        f"archived={stats['archived']} "
        f"deleted_reconstructed={stats['deleted_reconstructed']} "
        f"skipped_existing={stats['skipped_existing']}"
    )


if __name__ == "__main__":
    main()
