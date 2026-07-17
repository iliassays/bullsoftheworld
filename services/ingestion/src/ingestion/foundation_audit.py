"""Read-only acceptance audit for the Bulls research-data foundation.

The normal watchdogs answer "is today's product data fresh?". This command answers the broader
operator question: "is this market's universe internally consistent and research-ready?" It is
intentionally a bounded PostgreSQL report rather than a new service or scheduler.

    uv run python -m ingestion.foundation_audit
    uv run python -m ingestion.foundation_audit --market US --strict
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import sys
from collections import Counter
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from bulls.core.db import get_sessionmaker
from bulls.core.models import (
    AnnualFinancial,
    CompanyDataObservation,
    CompanyProfile,
    DailyBar,
    DailyBarObservation,
    DataSourceSnapshot,
    InstitutionalHoldingSummary,
    OnDemandResearchJob,
    RegulatoryDataState,
    SecFiling,
    SecFinancialFact,
    SecFinancialFactObservation,
    SecurityListingObservation,
    SecurityMaster,
    ShareholdingSnapshot,
    ShortVolumeDaily,
    Symbol,
    TickerAnalytics,
    UniverseOnboardingResult,
    UniverseOnboardingRun,
    UniverseOnboardingStage,
)
from bulls.market_data.calendar import most_recent_completed_session
from bulls.market_data.providers.us_yahoo import EOD_PUBLICATION_DELAY

AUDIT_VERSION = "data-foundation-v2"
MARKETS = ("DSE", "US")
STALE_RUN_AFTER = dt.timedelta(hours=3)
_SIZE_TABLES = (
    "symbols",
    "security_master",
    "daily_bars",
    "daily_bar_observations",
    "data_source_snapshots",
    "ticker_analytics",
    "company_profiles",
    "company_financials",
    "shareholding_snapshots",
    "sec_filings",
    "sec_financial_facts",
    "sec_financial_fact_observations",
    "security_listing_observations",
    "company_data_observations",
    "institutional_positions",
    "institutional_holding_summaries",
    "short_volume_daily",
    "universe_onboarding_runs",
    "universe_onboarding_results",
    "universe_onboarding_stages",
    "research_dataset_snapshots",
    "research_evidence_documents",
)


def _ratio(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 4) if denominator else None


async def _group_counts(session: AsyncSession, statement) -> dict[str, int]:
    return {str(key): int(value) for key, value in (await session.execute(statement)).all()}


async def _symbol_snapshot(session: AsyncSession, market: str) -> dict[str, Any]:
    status_counts = await _group_counts(
        session,
        select(Symbol.data_status, func.count())
        .where(Symbol.market == market)
        .group_by(Symbol.data_status),
    )
    total = sum(status_counts.values())
    active = int(
        await session.scalar(
            select(func.count())
            .select_from(Symbol)
            .where(Symbol.market == market, Symbol.is_active.is_(True))
        )
        or 0
    )
    visible = int(
        await session.scalar(
            select(func.count())
            .select_from(Symbol)
            .where(
                Symbol.market == market,
                Symbol.is_active.is_(True),
                Symbol.is_hidden.is_(False),
            )
        )
        or 0
    )
    ready = int(
        await session.scalar(
            select(func.count())
            .select_from(Symbol)
            .where(
                Symbol.market == market,
                Symbol.is_active.is_(True),
                Symbol.is_hidden.is_(False),
                Symbol.data_status == "ready",
            )
        )
        or 0
    )
    return {
        "total": total,
        "active": active,
        "visible": visible,
        "ready": ready,
        "by_data_status": status_counts,
    }


async def _market_data_snapshot(
    session: AsyncSession,
    market: str,
    *,
    ready: int,
    now: dt.datetime,
) -> dict[str, Any]:
    completed_session = most_recent_completed_session(
        now,
        market=market,
        publication_delay=EOD_PUBLICATION_DELAY if market == "US" else dt.timedelta(),
    )
    ready_codes = select(Symbol.code).where(
        Symbol.market == market,
        Symbol.is_active.is_(True),
        Symbol.is_hidden.is_(False),
        Symbol.data_status == "ready",
    )
    latest_bar = await session.scalar(
        select(func.max(DailyBar.date)).where(
            DailyBar.market == market,
            DailyBar.date <= completed_session,
            DailyBar.code.in_(ready_codes),
        )
    )
    first_bar = await session.scalar(
        select(func.min(DailyBar.date)).where(DailyBar.market == market)
    )
    bar_count = int(
        await session.scalar(
            select(func.count()).select_from(DailyBar).where(DailyBar.market == market)
        )
        or 0
    )
    latest_coverage = 0
    if latest_bar is not None:
        latest_coverage = int(
            await session.scalar(
                select(func.count(func.distinct(DailyBar.code))).where(
                    DailyBar.market == market,
                    DailyBar.date == latest_bar,
                    DailyBar.code.in_(ready_codes),
                )
            )
            or 0
        )
    analytics_count, analytics_date, unclassified, fingerprinted, pit_complete = (
        await session.execute(
            select(
                func.count(),
                func.max(TickerAnalytics.as_of_date),
                func.count().filter(TickerAnalytics.cap_tier.is_(None)),
                func.count().filter(TickerAnalytics.input_fingerprint.isnot(None)),
                func.count().filter(TickerAnalytics.point_in_time_complete.is_(True)),
            )
            .join(
                Symbol,
                (Symbol.market == TickerAnalytics.market)
                & (Symbol.code == TickerAnalytics.code),
            )
            .where(
                TickerAnalytics.market == market,
                TickerAnalytics.as_of_date <= completed_session,
                Symbol.is_active.is_(True),
                Symbol.is_hidden.is_(False),
                Symbol.data_status == "ready",
            )
        )
    ).one()
    return {
        "bars": {
            "latest_completed_session": completed_session,
            "rows": bar_count,
            "first_date": first_bar,
            "latest_date": latest_bar,
            "latest_ready_symbols": latest_coverage,
            "ready_coverage_ratio": _ratio(latest_coverage, ready),
        },
        "analytics": {
            "rows": int(analytics_count or 0),
            "latest_date": analytics_date,
            "unclassified_cap_tier": int(unclassified or 0),
            "fingerprinted": int(fingerprinted or 0),
            "point_in_time_complete": int(pit_complete or 0),
        },
    }


async def _identity_snapshot(session: AsyncSession, market: str) -> dict[str, int] | None:
    if market != "US":
        return None
    mismatch = int(
        await session.scalar(
            select(func.count())
            .select_from(Symbol)
            .join(
                SecurityMaster,
                (SecurityMaster.market == Symbol.market) & (SecurityMaster.symbol == Symbol.code),
            )
            .where(
                Symbol.market == market,
                Symbol.security_id.is_distinct_from(SecurityMaster.security_id),
            )
        )
        or 0
    )
    eligible_missing_symbol = int(
        await session.scalar(
            select(func.count())
            .select_from(SecurityMaster)
            .where(
                SecurityMaster.market == market,
                SecurityMaster.is_active.is_(True),
                SecurityMaster.is_product_eligible.is_(True),
                ~select(Symbol.code)
                .where(
                    Symbol.market == SecurityMaster.market,
                    Symbol.code == SecurityMaster.symbol,
                )
                .exists(),
            )
        )
        or 0
    )
    ready_missing_master = int(
        await session.scalar(
            select(func.count())
            .select_from(Symbol)
            .where(
                Symbol.market == market,
                Symbol.data_status == "ready",
                ~select(SecurityMaster.symbol)
                .where(
                    SecurityMaster.market == Symbol.market,
                    SecurityMaster.symbol == Symbol.code,
                    SecurityMaster.is_active.is_(True),
                )
                .exists(),
            )
        )
        or 0
    )
    return {
        "security_id_mismatches": mismatch,
        "eligible_listings_missing_symbol": eligible_missing_symbol,
        "ready_symbols_missing_active_master": ready_missing_master,
    }


async def _onboarding_snapshot(
    session: AsyncSession,
    market: str,
    *,
    now: dt.datetime,
) -> dict[str, Any]:
    run_counts = await _group_counts(
        session,
        select(UniverseOnboardingRun.status, func.count())
        .where(UniverseOnboardingRun.market == market)
        .group_by(UniverseOnboardingRun.status),
    )
    stale_running = int(
        await session.scalar(
            select(func.count())
            .select_from(UniverseOnboardingRun)
            .where(
                UniverseOnboardingRun.market == market,
                UniverseOnboardingRun.status == "running",
                UniverseOnboardingRun.started_at < now - STALE_RUN_AFTER,
            )
        )
        or 0
    )
    recent_runs = list(
        await session.scalars(
            select(UniverseOnboardingRun)
            .where(UniverseOnboardingRun.market == market)
            .order_by(UniverseOnboardingRun.started_at.desc())
            .limit(20)
        )
    )
    recent_ids = [run.id for run in recent_runs]
    stage_counts: dict[str, int] = {}
    if recent_ids:
        stage_counts = await _group_counts(
            session,
            select(UniverseOnboardingStage.status, func.count())
            .where(UniverseOnboardingStage.run_id.in_(recent_ids))
            .group_by(UniverseOnboardingStage.status),
        )
    failure_reasons: Counter[str] = Counter()
    if recent_ids:
        for reasons in await session.scalars(
            select(UniverseOnboardingResult.failure_reasons).where(
                UniverseOnboardingResult.run_id.in_(recent_ids),
                UniverseOnboardingResult.required_gates_passed.is_(False),
            )
        ):
            failure_reasons.update(str(reason) for reason in reasons or [])
    latest = [
        {
            "id": str(run.id),
            "cohort": run.cohort_name,
            "status": run.status,
            "requested": run.requested_count,
            "passed": run.passed_count,
            "failed": run.failed_count,
            "started_at": run.started_at,
            "completed_at": run.completed_at,
            "error": run.error,
        }
        for run in recent_runs[:10]
    ]
    return {
        "runs_by_status": run_counts,
        "stale_running": stale_running,
        "recent_failure_reasons": dict(failure_reasons.most_common()),
        "recent_stages_by_status": stage_counts,
        "recent_runs": latest,
    }


async def _lineage_snapshot(session: AsyncSession, market: str) -> dict[str, Any]:
    snapshot_counts = await _group_counts(
        session,
        select(DataSourceSnapshot.dataset_key, func.count())
        .where(DataSourceSnapshot.market == market)
        .group_by(DataSourceSnapshot.dataset_key),
    )
    observed_bar_keys = (
        select(DailyBarObservation.code, DailyBarObservation.date)
        .where(DailyBarObservation.market == market)
        .distinct()
        .subquery()
    )
    (
        bars,
        observed_bars,
        bar_revisions,
        company_observations,
        sec_observations,
        listing_observations,
    ) = (
        await session.execute(
            select(
                select(func.count())
                .select_from(DailyBar)
                .where(DailyBar.market == market)
                .scalar_subquery(),
                select(func.count()).select_from(observed_bar_keys).scalar_subquery(),
                select(func.count())
                .select_from(DailyBarObservation)
                .where(DailyBarObservation.market == market)
                .scalar_subquery(),
                select(func.count())
                .select_from(CompanyDataObservation)
                .where(CompanyDataObservation.market == market)
                .scalar_subquery(),
                select(func.count())
                .select_from(SecFinancialFactObservation)
                .where(SecFinancialFactObservation.market == market)
                .scalar_subquery(),
                select(func.count())
                .select_from(SecurityListingObservation)
                .where(SecurityListingObservation.market == market)
                .scalar_subquery(),
            )
        )
    ).one()
    return {
        "source_snapshots_by_dataset": snapshot_counts,
        "daily_bar_observations": int(bar_revisions or 0),
        "daily_bars_with_observation": int(observed_bars or 0),
        "daily_bar_projection_rows": int(bars or 0),
        "daily_bar_observation_ratio": _ratio(
            min(int(observed_bars or 0), int(bars or 0)), int(bars or 0)
        ),
        "company_data_observations": int(company_observations or 0),
        "sec_fact_observations": int(sec_observations or 0),
        "security_listing_observations": int(listing_observations or 0),
    }


async def _source_snapshot(session: AsyncSession, market: str) -> dict[str, Any]:
    if market == "DSE":
        profiles, annuals, latest_ownership = (
            await session.execute(
                select(
                    select(func.count())
                    .select_from(CompanyProfile)
                    .where(CompanyProfile.market == market)
                    .scalar_subquery(),
                    select(func.count())
                    .select_from(AnnualFinancial)
                    .where(AnnualFinancial.market == market)
                    .scalar_subquery(),
                    select(func.max(ShareholdingSnapshot.as_of_date))
                    .where(ShareholdingSnapshot.market == market)
                    .scalar_subquery(),
                )
            )
        ).one()
        return {
            "company_profiles": int(profiles or 0),
            "annual_financial_rows": int(annuals or 0),
            "latest_shareholding_date": latest_ownership,
        }

    filings, facts, holdings, short_rows = (
        await session.execute(
            select(
                select(func.count())
                .select_from(SecFiling)
                .where(SecFiling.market == market)
                .scalar_subquery(),
                select(func.count())
                .select_from(SecFinancialFact)
                .where(SecFinancialFact.market == market)
                .scalar_subquery(),
                select(func.count())
                .select_from(InstitutionalHoldingSummary)
                .where(InstitutionalHoldingSummary.market == market)
                .scalar_subquery(),
                select(func.count())
                .select_from(ShortVolumeDaily)
                .where(ShortVolumeDaily.market == market)
                .scalar_subquery(),
            )
        )
    ).one()
    states = list(
        await session.scalars(
            select(RegulatoryDataState)
            .where(RegulatoryDataState.market == market)
            .order_by(RegulatoryDataState.source)
        )
    )
    return {
        "sec_filings": int(filings or 0),
        "sec_financial_facts": int(facts or 0),
        "institutional_holding_summaries": int(holdings or 0),
        "finra_short_volume_rows": int(short_rows or 0),
        "checkpoints": [
            {
                "source": row.source,
                "as_of_date": row.as_of_date,
                "last_success_at": row.last_success_at,
                "records": row.records,
                "symbols_covered": row.symbols_covered,
                "downloaded_bytes": row.downloaded_bytes,
                "details": row.details,
            }
            for row in states
        ],
    }


async def _on_demand_snapshot(session: AsyncSession) -> dict[str, Any]:
    counts = await _group_counts(
        session,
        select(OnDemandResearchJob.status, func.count()).group_by(OnDemandResearchJob.status),
    )
    return {"jobs_by_status": counts}


def health_issues(snapshot: dict[str, Any]) -> list[dict[str, str]]:
    """Derive stable operator findings from one market snapshot."""
    issues: list[dict[str, str]] = []
    market = snapshot["market"]
    ready = snapshot["symbols"]["ready"]
    bars = snapshot["market_data"]["bars"]
    analytics = snapshot["market_data"]["analytics"]
    identity = snapshot.get("identity") or {}
    if ready == 0:
        issues.append({"severity": "critical", "code": "no_ready_symbols"})
    elif bars["latest_date"] is None:
        issues.append({"severity": "critical", "code": "no_daily_bars"})
    elif (bars["ready_coverage_ratio"] or 0) < 0.90:
        issues.append({"severity": "critical", "code": "latest_bar_coverage_below_90pct"})
    if bars["latest_date"] is not None and analytics["latest_date"] != bars["latest_date"]:
        issues.append({"severity": "critical", "code": "analytics_not_aligned_to_latest_bar"})
    if any(identity.values()):
        issues.append({"severity": "critical", "code": "security_identity_drift"})
    if snapshot["onboarding"]["stale_running"]:
        issues.append({"severity": "critical", "code": "stale_onboarding_run"})
    if snapshot["onboarding"]["recent_failure_reasons"]:
        issues.append({"severity": "warning", "code": "recent_gate_failures_need_disposition"})
    if analytics["unclassified_cap_tier"]:
        issues.append({"severity": "warning", "code": "unclassified_market_cap"})
    lineage = snapshot.get("lineage") or {}
    if bars["rows"] and (lineage.get("daily_bar_observation_ratio") or 0) < 0.99:
        issues.append({"severity": "critical", "code": "bar_revision_ledger_incomplete"})
    if analytics["rows"] and analytics["fingerprinted"] != analytics["rows"]:
        issues.append({"severity": "critical", "code": "analytics_inputs_not_fingerprinted"})
    if market == "US" and not lineage.get("security_listing_observations"):
        issues.append({"severity": "critical", "code": "security_listing_history_missing"})
    if (
        market == "US"
        and snapshot["sources"].get("sec_financial_facts")
        and not lineage.get("sec_fact_observations")
    ):
        issues.append({"severity": "critical", "code": "sec_fact_revision_history_missing"})
    if (
        market == "DSE"
        and snapshot["sources"].get("company_profiles")
        and not lineage.get("company_data_observations")
    ):
        issues.append({"severity": "critical", "code": "dse_company_revision_history_missing"})
    return [{**issue, "market": market} for issue in issues]


async def _table_sizes(session: AsyncSession) -> dict[str, int]:
    rows = (
        await session.execute(
            text(
                "SELECT c.relname, pg_total_relation_size(c.oid) "
                "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname = current_schema() AND c.relname = ANY(:tables) "
                "ORDER BY pg_total_relation_size(c.oid) DESC"
            ),
            {"tables": list(_SIZE_TABLES)},
        )
    ).all()
    return {name: int(size) for name, size in rows}


async def audit(markets: tuple[str, ...] = MARKETS) -> dict[str, Any]:
    now = dt.datetime.now(dt.UTC)
    sm = get_sessionmaker()
    async with sm() as session:
        reports: dict[str, Any] = {}
        for market in markets:
            symbols = await _symbol_snapshot(session, market)
            report = {
                "market": market,
                "symbols": symbols,
                "identity": await _identity_snapshot(session, market),
                "market_data": await _market_data_snapshot(
                    session,
                    market,
                    ready=symbols["ready"],
                    now=now,
                ),
                "onboarding": await _onboarding_snapshot(session, market, now=now),
                "sources": await _source_snapshot(session, market),
                "lineage": await _lineage_snapshot(session, market),
            }
            report["issues"] = health_issues(report)
            reports[market] = report
        result = {
            "audit_version": AUDIT_VERSION,
            "generated_at": now,
            "markets": reports,
            "on_demand_us": await _on_demand_snapshot(session),
            "table_sizes_bytes": await _table_sizes(session),
            "research_contract": {
                "operational_serving": "implemented",
                "immutable_research_snapshots": "implemented; bootstrap coverage is audited",
                "point_in_time_prices": "forward-safe; legacy rows require bounded bootstrap",
                "point_in_time_fundamentals": "forward-safe; historical coverage remains explicit",
                "point_in_time_security_universe": "event history starts at first guarded refresh",
                "dse_fundamental_known_at": "conservative ingestion upper bound where source time is absent",
            },
        }
    result["summary"] = {
        "critical": sum(
            issue["severity"] == "critical"
            for report in result["markets"].values()
            for issue in report["issues"]
        ),
        "warning": sum(
            issue["severity"] == "warning"
            for report in result["markets"].values()
            for issue in report["issues"]
        ),
    }
    return result


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit Bulls research-data foundation")
    parser.add_argument("--market", choices=MARKETS)
    parser.add_argument(
        "--strict",
        action="store_true",
        help="exit non-zero when the report contains a critical issue",
    )
    return parser.parse_args(argv)


def main() -> None:
    args = _parse_args(sys.argv[1:])
    markets = (args.market,) if args.market else MARKETS
    result = asyncio.run(audit(markets))
    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    if args.strict and result["summary"]["critical"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
