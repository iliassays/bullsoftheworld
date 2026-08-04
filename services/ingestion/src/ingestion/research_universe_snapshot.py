"""Materialize the current completed-session Atlas universe under ``universe_policy_v1``.

The command intentionally accepts only the latest analytics session.  Historical reconstruction
must eventually read the append-only observation ledgers; using today's security master for an old
date would introduce survivorship bias.  Until that reconstruction exists, attempts to backfill an
older date fail rather than manufacture point-in-time evidence.

Usage::

    uv run python -m ingestion.research_universe_snapshot DSE
    uv run python -m ingestion.research_universe_snapshot US --json
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import hashlib
import json
import statistics
import sys
import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any

from sqlalchemy import String, column, func, select, text, true, union, values
from sqlalchemy.dialects.postgresql import insert as pg_insert

from bulls.analytics.universe_policy import (
    UniverseDecision,
    UniverseEvidence,
    UniversePolicy,
    UniversePolicyInput,
    UniversePolicyResult,
    default_universe_policy,
    evaluate_universe,
    universe_input_fingerprint,
)
from bulls.core.db import get_sessionmaker
from bulls.core.markets import get_market_profile
from bulls.core.models import (
    CapTierObservation,
    DailyBar,
    MarketSummary,
    ResearchUniverseMember,
    ResearchUniverseSnapshot,
    SecurityListingObservation,
    SecurityMaster,
    Symbol,
    TickerAnalytics,
)

_INSERT_BATCH_SIZE = 500
_BAR_BATCH_SIZE = 250
_BAR_LOOKBACK = 300
_RECENT_SESSIONS = 20


@dataclass(frozen=True, slots=True)
class CandidateState:
    code: str
    security_id: uuid.UUID | None
    instrument_type: str | None
    exchange: str | None
    is_active: bool | None
    is_product_eligible: bool | None
    is_hidden: bool
    is_etf: bool
    is_test_issue: bool
    financial_status: str | None
    category: str | None
    market_cap_mn: float | None
    analytics_point_in_time_complete: bool = False


@dataclass(frozen=True, slots=True)
class BarState:
    latest_bar_date: dt.date | None = None
    last_close: float | None = None
    history_sessions: int = 0
    adjusted_sessions: int = 0
    recent_sessions_observed: int = 0
    recent_sessions_traded: int = 0
    median_traded_value_20_mn: float | None = None


@dataclass(frozen=True, slots=True)
class ListingObservationState:
    security_id: uuid.UUID
    instrument_type: str
    exchange: str | None
    is_active: bool
    is_product_eligible: bool


def candidate_input_fingerprint(candidates: list[CandidateState]) -> str:
    """Fingerprint every mutable candidate field used before the bounded bar read."""

    payload = [
        {
            field: getattr(candidate, field)
            for field in CandidateState.__dataclass_fields__
        }
        for candidate in sorted(candidates, key=lambda item: item.code)
    ]
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(encoded).hexdigest()


def listing_observation_matches(
    candidate: CandidateState,
    observation: ListingObservationState | None,
) -> bool:
    """Certify that the current listing projection is backed by its latest observation."""

    if observation is None or candidate.security_id is None:
        return False
    return (
        candidate.security_id == observation.security_id
        and (candidate.instrument_type or "").casefold()
        == observation.instrument_type.casefold()
        and (candidate.exchange or "").casefold() == (observation.exchange or "").casefold()
        and candidate.is_active == observation.is_active
        and candidate.is_product_eligible == observation.is_product_eligible
    )


def summarize_recent_bars(
    rows: list[tuple[str, dt.date, float, int]],
) -> dict[str, BarState]:
    """Build deterministic 20-market-session metrics from a compact row projection."""

    grouped: dict[str, list[tuple[dt.date, float, int]]] = defaultdict(list)
    for code, date, close, volume in rows:
        grouped[code].append((date, float(close), int(volume or 0)))

    result: dict[str, BarState] = {}
    for code, history in grouped.items():
        ordered = sorted(history, key=lambda row: row[0])
        latest_date, latest_close, _ = ordered[-1]
        traded_values = [close * volume / 1_000_000 for _, close, volume in ordered]
        result[code] = BarState(
            latest_bar_date=latest_date,
            last_close=latest_close,
            recent_sessions_observed=len(ordered),
            recent_sessions_traded=sum(volume > 0 for _, _, volume in ordered),
            median_traded_value_20_mn=(
                statistics.median(traded_values) if traded_values else None
            ),
        )
    return result


def build_policy_input(
    *,
    market: str,
    as_of_date: dt.date,
    candidate: CandidateState,
    bars: BarState,
    listing_point_in_time: bool,
) -> UniversePolicyInput:
    """Join database projections into the pure policy contract."""

    capitalization_point_in_time = candidate.market_cap_mn is not None
    bars_point_in_time = candidate.analytics_point_in_time_complete
    # Adjusted-close coverage is necessary but not sufficient. It is accepted as corporate-action
    # evidence only after the complete analytics input passes the explicit point-in-time audit.
    corporate_actions_complete = (
        market == "US"
        and bars.history_sessions > 0
        and bars.adjusted_sessions >= bars.history_sessions
        and bars_point_in_time
    )
    return UniversePolicyInput(
        market=market,
        as_of_date=as_of_date,
        code=candidate.code,
        security_id=candidate.security_id,
        instrument_type=candidate.instrument_type,
        exchange=candidate.exchange,
        is_active=candidate.is_active,
        is_product_eligible=candidate.is_product_eligible,
        is_hidden=candidate.is_hidden,
        is_etf=candidate.is_etf,
        is_test_issue=candidate.is_test_issue,
        financial_status=candidate.financial_status,
        category=candidate.category,
        latest_bar_date=bars.latest_bar_date,
        last_close=bars.last_close,
        history_sessions=bars.history_sessions,
        recent_sessions_observed=bars.recent_sessions_observed,
        recent_sessions_traded=bars.recent_sessions_traded,
        median_traded_value_20_mn=bars.median_traded_value_20_mn,
        market_cap_mn=candidate.market_cap_mn,
        recent_reverse_split=None,
        evidence=UniverseEvidence(
            listing_point_in_time=listing_point_in_time,
            bars_point_in_time=bars_point_in_time,
            capitalization_point_in_time=capitalization_point_in_time,
            corporate_actions_complete=corporate_actions_complete,
            # No explicit, dated reverse-split event history exists yet.  Adjusted close alone is
            # not promoted into a stronger claim.
            reverse_split_history_complete=False,
        ),
    )


def snapshot_quality(results: list[UniversePolicyResult]) -> dict[str, Any]:
    reason_counts = Counter(reason.value for row in results for reason in row.reasons)
    blocker_counts = Counter(reason.value for row in results for reason in row.model_blockers)
    cohort_counts = Counter(row.cohort.value for row in results if row.cohort is not None)
    return {
        "decisions": dict(Counter(row.decision.value for row in results)),
        "cohorts": dict(sorted(cohort_counts.items())),
        "reasons": dict(reason_counts.most_common()),
        "model_blockers": dict(blocker_counts.most_common()),
    }


def snapshot_model_ready(results: list[UniversePolicyResult]) -> bool:
    """Require a non-empty, fully known universe before allowing model consumption."""

    eligible = [row for row in results if row.decision == UniverseDecision.ELIGIBLE]
    return (
        bool(eligible)
        and not any(row.decision == UniverseDecision.DATA_BLOCKED for row in results)
        and all(row.model_eligible for row in eligible)
    )


def _snapshot_payload(
    snapshot: ResearchUniverseSnapshot,
    *,
    reused: bool,
) -> dict[str, Any]:
    return {
        "snapshot_id": str(snapshot.id),
        "market": snapshot.market,
        "as_of_date": snapshot.as_of_date.isoformat(),
        "candidate_count": snapshot.candidate_count,
        "eligible_count": snapshot.eligible_count,
        "ineligible_count": snapshot.ineligible_count,
        "data_blocked_count": snapshot.data_blocked_count,
        "model_eligible_count": snapshot.model_eligible_count,
        "model_ready": snapshot.model_ready,
        "quality_report": snapshot.quality_report,
        "reused": reused,
    }


async def _latest_session(session, market: str) -> dt.date:
    latest = await session.scalar(
        select(func.max(TickerAnalytics.as_of_date)).where(TickerAnalytics.market == market)
    )
    if latest is None:
        raise ValueError(f"No completed analytics session exists for {market}")
    cap_archive_latest = await session.scalar(
        select(func.max(CapTierObservation.as_of_date)).where(
            CapTierObservation.market == market
        )
    )
    if cap_archive_latest != latest:
        raise ValueError(
            f"Analytics refresh is incomplete for {market}: analytics={latest}, "
            f"cap_archive={cap_archive_latest}"
        )
    return latest


async def _candidates(
    session,
    *,
    market: str,
    as_of_date: dt.date,
) -> list[CandidateState]:
    rows = (
        await session.execute(
            select(
                SecurityMaster.symbol,
                SecurityMaster.security_id,
                SecurityMaster.instrument_type,
                SecurityMaster.exchange,
                SecurityMaster.is_active,
                SecurityMaster.is_product_eligible,
                SecurityMaster.is_etf,
                SecurityMaster.is_test_issue,
                SecurityMaster.financial_status,
                Symbol.is_hidden,
                Symbol.category,
                CapTierObservation.market_cap_mn,
                TickerAnalytics.point_in_time_complete.label(
                    "analytics_point_in_time_complete"
                ),
            )
            .outerjoin(
                Symbol,
                (Symbol.market == SecurityMaster.market)
                & (Symbol.code == SecurityMaster.symbol),
            )
            .outerjoin(
                CapTierObservation,
                (CapTierObservation.market == SecurityMaster.market)
                & (CapTierObservation.code == SecurityMaster.symbol)
                & (CapTierObservation.as_of_date == as_of_date),
            )
            .outerjoin(
                TickerAnalytics,
                (TickerAnalytics.market == SecurityMaster.market)
                & (TickerAnalytics.code == SecurityMaster.symbol)
                & (TickerAnalytics.as_of_date == as_of_date),
            )
            .where(SecurityMaster.market == market)
            .order_by(SecurityMaster.symbol)
        )
    ).all()
    return [
        CandidateState(
            code=row.symbol,
            security_id=row.security_id,
            instrument_type=row.instrument_type,
            exchange=row.exchange,
            is_active=row.is_active,
            is_product_eligible=row.is_product_eligible,
            is_hidden=bool(row.is_hidden),
            is_etf=bool(row.is_etf),
            is_test_issue=bool(row.is_test_issue),
            financial_status=row.financial_status,
            category=row.category,
            market_cap_mn=(
                float(row.market_cap_mn) if row.market_cap_mn is not None else None
            ),
            analytics_point_in_time_complete=bool(
                row.analytics_point_in_time_complete
            ),
        )
        for row in rows
    ]


def _bar_batch_statement(
    market: str,
    codes: list[str],
    *,
    through_date: dt.date,
):
    """Build an index-bounded latest-bars query for one security batch."""

    requested_codes = (
        values(column("code", String(32)), name="requested_codes")
        .data([(code,) for code in codes])
        .cte("requested_codes")
    )
    latest_bars = (
        select(
            DailyBar.date.label("date"),
            DailyBar.close.label("close"),
            DailyBar.volume.label("volume"),
            DailyBar.adjusted_close.label("adjusted_close"),
        )
        .where(
            DailyBar.market == market,
            DailyBar.code == requested_codes.c.code,
            DailyBar.date <= through_date,
        )
        .order_by(DailyBar.date.desc())
        .limit(_BAR_LOOKBACK)
        .lateral("latest_bars")
    )
    return (
        select(
            requested_codes.c.code,
            latest_bars.c.date,
            latest_bars.c.close,
            latest_bars.c.volume,
            latest_bars.c.adjusted_close,
        )
        .select_from(requested_codes.join(latest_bars, true()))
        .order_by(requested_codes.c.code, latest_bars.c.date)
    )


def _session_calendar_statement(market: str, *, through_date: dt.date):
    """Return the bounded completed-session calendar from independent stored projections.

    ``market_summaries`` is a useful product projection but can lag an otherwise completed EOD
    chain.  The configured market benchmark is a second authoritative trading-session witness.
    Taking their union keeps DSE and US on one profile-driven path and prevents a stale summary
    row from blocking an otherwise auditable universe snapshot.
    """

    benchmark_code = get_market_profile(market).benchmark_code
    dates = union(
        select(MarketSummary.date.label("date")).where(
            MarketSummary.market == market,
            MarketSummary.date <= through_date,
        ),
        select(DailyBar.date.label("date")).where(
            DailyBar.market == market,
            DailyBar.code == benchmark_code,
            DailyBar.date <= through_date,
        ),
    ).subquery("research_session_calendar")
    return select(dates.c.date).order_by(dates.c.date.desc()).limit(_RECENT_SESSIONS)


async def _bar_states(
    session,
    *,
    market: str,
    as_of_date: dt.date,
    codes: list[str],
) -> dict[str, BarState]:
    """Load at most 300 indexed bars per code; never aggregate the full bar store."""

    session_dates = list(
        await session.scalars(_session_calendar_statement(market, through_date=as_of_date))
    )
    if len(session_dates) != _RECENT_SESSIONS or session_dates[0] != as_of_date:
        raise ValueError(
            f"Market calendar is incomplete for {market} through {as_of_date}: "
            f"latest={session_dates[0] if session_dates else None}, "
            f"sessions={len(session_dates)}"
        )
    recent_dates = set(session_dates)
    result: dict[str, BarState] = {}
    for offset in range(0, len(codes), _BAR_BATCH_SIZE):
        batch = codes[offset : offset + _BAR_BATCH_SIZE]
        rows_by_code: dict[str, list[Any]] = defaultdict(list)
        rows = (
            await session.execute(
                _bar_batch_statement(market, batch, through_date=as_of_date)
            )
        ).mappings()
        for row in rows:
            rows_by_code[row["code"]].append(row)
        for code, history in rows_by_code.items():
            recent = [
                (code, row["date"], row["close"], row["volume"])
                for row in history
                if row["date"] in recent_dates
            ]
            compact = summarize_recent_bars(recent).get(code, BarState())
            latest = history[-1]
            result[code] = BarState(
                latest_bar_date=latest["date"],
                last_close=float(latest["close"]),
                history_sessions=len(history),
                adjusted_sessions=sum(
                    row["adjusted_close"] is not None for row in history
                ),
                recent_sessions_observed=compact.recent_sessions_observed,
                recent_sessions_traded=compact.recent_sessions_traded,
                median_traded_value_20_mn=compact.median_traded_value_20_mn,
            )
    return result


async def _listing_observation_states(
    session,
    *,
    market: str,
    knowledge_cutoff: dt.datetime,
) -> dict[str, ListingObservationState]:
    ranked = (
        select(
            SecurityListingObservation.symbol,
            SecurityListingObservation.security_id,
            SecurityListingObservation.instrument_type,
            SecurityListingObservation.exchange,
            SecurityListingObservation.is_active,
            SecurityListingObservation.is_product_eligible,
            func.row_number()
            .over(
                partition_by=SecurityListingObservation.symbol,
                order_by=(
                    SecurityListingObservation.known_at.desc(),
                    SecurityListingObservation.ingested_at.desc(),
                    SecurityListingObservation.id.desc(),
                ),
            )
            .label("row_number"),
        )
        .where(
                SecurityListingObservation.market == market,
                SecurityListingObservation.known_at <= knowledge_cutoff,
            )
        .subquery("ranked_listing_observations")
    )
    rows = (await session.execute(select(ranked).where(ranked.c.row_number == 1))).mappings()
    return {
        row["symbol"]: ListingObservationState(
            security_id=row["security_id"],
            instrument_type=row["instrument_type"],
            exchange=row["exchange"],
            is_active=row["is_active"],
            is_product_eligible=row["is_product_eligible"],
        )
        for row in rows
    }


def _member_rows(
    *,
    snapshot_id: uuid.UUID,
    inputs: list[UniversePolicyInput],
    results: list[UniversePolicyResult],
    evaluated_at: dt.datetime,
) -> list[dict[str, Any]]:
    inputs_by_code = {item.code: item for item in inputs}
    return [
        {
            "snapshot_id": snapshot_id,
            "market": row.market,
            "code": row.code,
            "security_id": row.security_id,
            "decision": row.decision.value,
            "cohort": row.cohort.value if row.cohort is not None else None,
            "cap_tier": row.cap_tier,
            "model_eligible": row.model_eligible,
            "reason_codes": [reason.value for reason in row.reasons],
            "model_blocker_codes": [reason.value for reason in row.model_blockers],
            "warning_codes": [reason.value for reason in row.warnings],
            "metrics": row.metrics,
            "evidence": inputs_by_code[row.code].evidence.model_dump(mode="json"),
            "input_sha256": row.input_sha256,
            "evaluated_at": evaluated_at,
        }
        for row in results
    ]


async def materialize_research_universe(
    market: str,
    *,
    as_of_date: dt.date | None = None,
    policy: UniversePolicy | None = None,
    force_recompute: bool = False,
) -> dict[str, Any]:
    """Evaluate and persist one idempotent current-session universe snapshot."""

    market = market.upper()
    if market not in {"DSE", "US"}:
        raise ValueError("research universe supports DSE and US only")
    selected_policy = policy or default_universe_policy()
    generated_at = dt.datetime.now(dt.UTC)
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        latest_session = await _latest_session(session, market)
        requested_date = as_of_date or latest_session
        if requested_date != latest_session:
            raise ValueError(
                f"Historical universe reconstruction is not enabled: requested {requested_date}, "
                f"latest completed session is {latest_session}"
            )
        await session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:identity, 0))"),
            {
                "identity": (
                    f"research-universe:{market}:{requested_date}:"
                    f"{selected_policy.key}:{selected_policy.version}"
                )
            },
        )
        candidates = await _candidates(
            session,
            market=market,
            as_of_date=requested_date,
        )
        if not candidates:
            raise ValueError(f"Security master has no candidates for {market}")
        candidate_fingerprint = candidate_input_fingerprint(candidates)
        if not force_recompute:
            existing = await session.scalar(
                select(ResearchUniverseSnapshot)
                .where(
                    ResearchUniverseSnapshot.market == market,
                    ResearchUniverseSnapshot.as_of_date == requested_date,
                    ResearchUniverseSnapshot.policy_key == selected_policy.key,
                    ResearchUniverseSnapshot.policy_version == selected_policy.version,
                    ResearchUniverseSnapshot.policy_sha256 == selected_policy.sha256,
                )
                .order_by(ResearchUniverseSnapshot.generated_at.desc())
                .limit(1)
            )
            if existing is not None:
                analytics_watermark = await session.scalar(
                    select(func.max(TickerAnalytics.computed_at)).where(
                        TickerAnalytics.market == market,
                        TickerAnalytics.as_of_date == requested_date,
                    )
                )
                if (
                    (analytics_watermark is None or existing.generated_at >= analytics_watermark)
                    and existing.quality_report.get("candidate_input_fingerprint")
                    == candidate_fingerprint
                ):
                    return _snapshot_payload(existing, reused=True)
        bars = await _bar_states(
            session,
            market=market,
            as_of_date=requested_date,
            codes=[candidate.code for candidate in candidates],
        )
        listing_observations = await _listing_observation_states(
            session,
            market=market,
            knowledge_cutoff=generated_at,
        )
        inputs = [
            build_policy_input(
                market=market,
                as_of_date=requested_date,
                candidate=candidate,
                bars=bars.get(candidate.code, BarState()),
                listing_point_in_time=listing_observation_matches(
                    candidate,
                    listing_observations.get(candidate.code),
                ),
            )
            for candidate in candidates
        ]
        results = evaluate_universe(inputs, policy=selected_policy)
        input_fingerprint = universe_input_fingerprint(inputs, policy=selected_policy)
        existing = await session.scalar(
            select(ResearchUniverseSnapshot).where(
                ResearchUniverseSnapshot.market == market,
                ResearchUniverseSnapshot.as_of_date == requested_date,
                ResearchUniverseSnapshot.policy_key == selected_policy.key,
                ResearchUniverseSnapshot.policy_version == selected_policy.version,
                ResearchUniverseSnapshot.input_fingerprint == input_fingerprint,
            )
        )
        if existing is not None:
            return _snapshot_payload(existing, reused=True)

        decision_counts = Counter(row.decision for row in results)
        model_eligible_count = sum(row.model_eligible for row in results)
        eligible_count = decision_counts[UniverseDecision.ELIGIBLE]
        model_ready = snapshot_model_ready(results)
        quality = snapshot_quality(results)
        quality["candidate_input_fingerprint"] = candidate_fingerprint
        snapshot = ResearchUniverseSnapshot(
            market=market,
            as_of_date=requested_date,
            knowledge_cutoff=generated_at,
            policy_key=selected_policy.key,
            policy_version=selected_policy.version,
            policy_sha256=selected_policy.sha256,
            input_fingerprint=input_fingerprint,
            # The values are read from mutable current projections.  Member-level evidence records
            # which projections are fully backed by append-only observations.
            source_mode="current_projection",
            model_ready=model_ready,
            candidate_count=len(results),
            eligible_count=eligible_count,
            ineligible_count=decision_counts[UniverseDecision.INELIGIBLE],
            data_blocked_count=decision_counts[UniverseDecision.DATA_BLOCKED],
            model_eligible_count=model_eligible_count,
            policy_parameters=selected_policy.model_dump(mode="json"),
            quality_report=quality,
            generated_at=generated_at,
        )
        session.add(snapshot)
        await session.flush()
        members = _member_rows(
            snapshot_id=snapshot.id,
            inputs=inputs,
            results=results,
            evaluated_at=generated_at,
        )
        for offset in range(0, len(members), _INSERT_BATCH_SIZE):
            await session.execute(
                pg_insert(ResearchUniverseMember).values(
                    members[offset : offset + _INSERT_BATCH_SIZE]
                )
            )
        await session.commit()
        return _snapshot_payload(snapshot, reused=False)


def _args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("market", choices=("DSE", "US"))
    parser.add_argument("--as-of", type=dt.date.fromisoformat)
    parser.add_argument(
        "--force",
        action="store_true",
        help="re-evaluate current projections and write a new immutable revision if inputs changed",
    )
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def main() -> None:
    args = _args()
    result = asyncio.run(
        materialize_research_universe(
            args.market,
            as_of_date=args.as_of,
            force_recompute=args.force,
        )
    )
    if args.json:
        json.dump(result, sys.stdout, indent=2, default=str)
        sys.stdout.write("\n")
    else:
        print(
            f"[research-universe] {result['market']} {result['as_of_date']} "
            f"eligible={result['eligible_count']} ineligible={result['ineligible_count']} "
            f"blocked={result['data_blocked_count']} model_ready={result['model_ready']} "
            f"snapshot={result['snapshot_id']} reused={result['reused']}"
        )


if __name__ == "__main__":
    main()
