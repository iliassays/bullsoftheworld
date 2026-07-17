"""Resumable, evidence-gated cohort onboarding for large market universes.

Example:
    uv run python -m ingestion.universe_onboarding \
      tenants/bullsofwallst/cohorts/liquid-expansion-v1.json
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import sys
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from bulls.core.config import get_settings
from bulls.core.db import get_sessionmaker
from bulls.core.models import (
    SecurityMaster,
    Symbol,
    UniverseOnboardingResult,
    UniverseOnboardingRun,
    UniverseOnboardingStage,
)
from bulls.core.symbol_lifecycle import research_publication_status
from bulls.market_data.calendar import to_market_tz
from ingestion.analytics import compute_all
from ingestion.cohorts import CohortManifest, load_cohort
from ingestion.history import collect as collect_history
from ingestion.lineage import content_sha256
from ingestion.onboarding_gates import GateEvidence, evaluate_cohort
from ingestion.sec import collect as collect_sec
from ingestion.security_master import collect as collect_security_master


async def create_onboarding_run(
    manifest: CohortManifest,
    promote: bool = False,
    publish_research: bool = False,
) -> UniverseOnboardingRun:
    settings = get_settings()
    run = UniverseOnboardingRun(
        id=uuid.uuid4(),
        market=manifest.market,
        cohort_name=manifest.name,
        cohort_version=manifest.version,
        manifest_sha256=manifest.manifest_sha256,
        status="running",
        promotion_requested=promote or publish_research,
        requested_count=len(manifest.symbols),
        passed_count=0,
        failed_count=0,
        parameters={
            "backfill_years": manifest.backfill_years,
            "policy": manifest.policy.model_dump(mode="json"),
            "market_data_authorization_id": (
                settings.us_market_data_authorization_id if promote else None
            ),
            "publication_mode": (
                "authorized"
                if promote
                else "owner_directed_research"
                if publish_research
                else "private"
            ),
            "risk_review_id": manifest.risk_review_id,
            "allow_restricted_research": manifest.allow_restricted_research,
        },
        error=None,
        started_at=dt.datetime.now(dt.UTC),
        completed_at=None,
    )
    sm = get_sessionmaker()
    async with sm() as session:
        session.add(run)
        await session.commit()
    return run


async def _resume_run(
    run_id: uuid.UUID,
    manifest: CohortManifest,
    promote: bool,
    publish_research: bool,
) -> UniverseOnboardingRun:
    sm = get_sessionmaker()
    async with sm() as session:
        run = await session.scalar(
            select(UniverseOnboardingRun)
            .where(UniverseOnboardingRun.id == run_id)
            .with_for_update()
        )
        if run is None:
            raise ValueError(f"unknown onboarding run {run_id}")
        if run.manifest_sha256 != manifest.manifest_sha256:
            raise ValueError("resume manifest hash does not match the original run")
        if run.promotion_requested != (promote or publish_research):
            raise ValueError("resume promotion intent does not match the original run")
        expected_mode = (
            "authorized"
            if promote
            else "owner_directed_research"
            if publish_research
            else "private"
        )
        if run.parameters.get("publication_mode", "private") != expected_mode:
            raise ValueError("resume publication mode does not match the original run")
        if run.status == "completed":
            raise ValueError("completed onboarding runs are immutable")
        run.status = "running"
        run.error = None
        run.completed_at = None
        await session.commit()
        return run


async def _begin_stage(
    run_id: uuid.UUID,
    *,
    stage_key: str,
    ordinal: int,
    input_fingerprint: str,
) -> tuple[bool, Any]:
    """Start/restart a durable stage, or return its prior result when already complete."""
    sm = get_sessionmaker()
    async with sm() as session:
        await session.execute(
            pg_insert(UniverseOnboardingStage)
            .values(
                run_id=run_id,
                stage_key=stage_key,
                ordinal=ordinal,
                status="running",
                attempts=0,
                input_fingerprint=input_fingerprint,
                output_fingerprint=None,
                stats={},
                error=None,
                started_at=dt.datetime.now(dt.UTC),
                completed_at=None,
            )
            .on_conflict_do_nothing(index_elements=["run_id", "stage_key"])
        )
        stage = await session.scalar(
            select(UniverseOnboardingStage)
            .where(
                UniverseOnboardingStage.run_id == run_id,
                UniverseOnboardingStage.stage_key == stage_key,
            )
            .with_for_update()
        )
        if stage is None:
            raise RuntimeError(f"onboarding stage {stage_key} was not persisted")
        if stage.status == "completed":
            if stage.input_fingerprint != input_fingerprint:
                raise ValueError(
                    f"completed onboarding stage {stage_key} has a different input fingerprint"
                )
            return True, stage.stats.get("result")
        stage.status = "running"
        stage.attempts += 1
        stage.error = None
        stage.input_fingerprint = input_fingerprint
        stage.output_fingerprint = None
        stage.started_at = dt.datetime.now(dt.UTC)
        stage.completed_at = None
        await session.commit()
    return False, None


async def _finish_stage(run_id: uuid.UUID, stage_key: str, result: Any) -> None:
    sm = get_sessionmaker()
    async with sm() as session:
        stage = await session.scalar(
            select(UniverseOnboardingStage)
            .where(
                UniverseOnboardingStage.run_id == run_id,
                UniverseOnboardingStage.stage_key == stage_key,
            )
            .with_for_update()
        )
        if stage is None:
            raise RuntimeError(f"onboarding stage {stage_key} disappeared")
        stage.status = "completed"
        stage.stats = {"result": result}
        stage.output_fingerprint = content_sha256(result)
        stage.error = None
        stage.completed_at = dt.datetime.now(dt.UTC)
        await session.commit()


async def _fail_stage(run_id: uuid.UUID, stage_key: str, error: BaseException) -> None:
    sm = get_sessionmaker()
    async with sm() as session:
        stage = await session.scalar(
            select(UniverseOnboardingStage)
            .where(
                UniverseOnboardingStage.run_id == run_id,
                UniverseOnboardingStage.stage_key == stage_key,
            )
            .with_for_update()
        )
        if stage is not None:
            stage.status = "failed"
            stage.error = f"{type(error).__name__}: {error}"[:2000]
            stage.completed_at = dt.datetime.now(dt.UTC)
            await session.commit()


async def _checkpointed_stage(
    run_id: uuid.UUID,
    *,
    stage_key: str,
    ordinal: int,
    input_fingerprint: str,
    operation: Callable[[], Awaitable[Any]],
) -> Any:
    completed, result = await _begin_stage(
        run_id,
        stage_key=stage_key,
        ordinal=ordinal,
        input_fingerprint=input_fingerprint,
    )
    if completed:
        return result
    try:
        result = await operation()
    except asyncio.CancelledError as error:
        await _fail_stage(run_id, stage_key, error)
        raise
    except Exception as error:
        await _fail_stage(run_id, stage_key, error)
        raise
    await _finish_stage(run_id, stage_key, result)
    return result


def _stage_input_fingerprint(
    run: UniverseOnboardingRun,
    manifest: CohortManifest,
    stage_key: str,
) -> str:
    return content_sha256(
        {
            "run_id": str(run.id),
            "stage_key": stage_key,
            "manifest_sha256": manifest.manifest_sha256,
            "parameters": run.parameters,
        }
    )


async def _persist_results(
    run: UniverseOnboardingRun,
    evidence: list[GateEvidence],
    *,
    promote: bool,
    publish_research: bool,
) -> tuple[int, int, int, int]:
    now = dt.datetime.now(dt.UTC)
    passed_codes = [row.code for row in evidence if row.passed]
    rows = [row.result_row(run.id, run.market, now) for row in evidence]
    sm = get_sessionmaker()
    async with sm() as session:
        await session.execute(
            delete(UniverseOnboardingResult).where(UniverseOnboardingResult.run_id == run.id)
        )
        if rows:
            await session.execute(pg_insert(UniverseOnboardingResult).values(rows))
        published = 0
        research_only = 0
        if promote and passed_codes:
            promotion_result = await session.execute(
                update(Symbol)
                .where(
                    Symbol.market == run.market,
                    Symbol.code.in_(passed_codes),
                    Symbol.data_status == "onboarding",
                )
                .values(data_status="ready")
            )
            published = int(promotion_result.rowcount or 0)
        elif publish_research:
            publication_codes: dict[str, list[str]] = {"ready": [], "research_only": []}
            for row in evidence:
                status = research_publication_status(row.passed, row.failure_reasons)
                if status is not None:
                    publication_codes[status].append(row.code)
            for status, codes in publication_codes.items():
                if not codes:
                    continue
                publication_result = await session.execute(
                    update(Symbol)
                    .where(
                        Symbol.market == run.market,
                        Symbol.code.in_(codes),
                        Symbol.is_active.is_(True),
                    )
                    .values(data_status=status, is_hidden=False)
                )
                count = int(publication_result.rowcount or 0)
                published += count
                if status == "research_only":
                    research_only += count
        current = await session.get(UniverseOnboardingRun, run.id)
        if current is None:
            raise RuntimeError(f"onboarding run {run.id} disappeared")
        current.status = "completed"
        current.passed_count = len(passed_codes)
        current.failed_count = len(evidence) - len(passed_codes)
        current.completed_at = now
        await session.commit()
    return len(passed_codes), len(evidence) - len(passed_codes), published, research_only


async def _mark_failed(run_id: uuid.UUID, error: Exception) -> None:
    sm = get_sessionmaker()
    async with sm() as session:
        run = await session.get(UniverseOnboardingRun, run_id)
        if run is not None:
            run.status = "failed"
            run.error = f"{type(error).__name__}: {error}"[:2000]
            run.completed_at = dt.datetime.now(dt.UTC)
            await session.commit()


async def _stage_restricted_research_symbols(manifest: CohortManifest) -> int:
    """Stage explicitly requested deficient common stocks as private research records only."""
    if not manifest.allow_restricted_research:
        return 0
    sm = get_sessionmaker()
    async with sm() as session:
        securities = list(
            await session.scalars(
                select(SecurityMaster).where(
                    SecurityMaster.market == manifest.market,
                    SecurityMaster.symbol.in_(manifest.symbols),
                    SecurityMaster.is_active.is_(True),
                    SecurityMaster.is_product_eligible.is_(False),
                    SecurityMaster.instrument_type.in_(manifest.policy.allowed_instrument_types),
                    SecurityMaster.exclude_reason.like("financial_status_%"),
                )
            )
        )
        if not securities:
            return 0
        rows = [
            {
                "security_id": security.security_id,
                "market": security.market,
                "code": security.symbol,
                "name_en": security.security_name,
                "name_bn": None,
                "sector": None,
                "category": None,
                "is_active": True,
                "is_hidden": True,
                "data_status": "onboarding",
            }
            for security in securities
        ]
        stmt = pg_insert(Symbol).values(rows)
        await session.execute(
            stmt.on_conflict_do_update(
                index_elements=["market", "code"],
                set_={
                    "security_id": stmt.excluded.security_id,
                    "name_en": stmt.excluded.name_en,
                    "is_active": True,
                    "is_hidden": True,
                    "data_status": "onboarding",
                },
            )
        )
        await session.commit()
    return len(securities)


def _validate_promotion(
    promote: bool,
    manifest: CohortManifest,
    *,
    publish_research: bool = False,
) -> None:
    if promote and publish_research:
        raise ValueError("--promote and --publish-research are mutually exclusive")
    if publish_research:
        if not manifest.risk_review_id:
            raise ValueError(
                "risk_review_id records the owner acknowledgement for research publication"
            )
        return
    if not promote:
        return
    if manifest.policy.requires_risk_review and not manifest.risk_review_id:
        raise ValueError("risk_review_id is required to promote this enhanced-risk cohort")
    settings = get_settings()
    if not settings.us_universe_promotion_enabled:
        raise ValueError("US_UNIVERSE_PROMOTION_ENABLED is false")
    if not settings.us_market_data_authorization_id.strip():
        raise ValueError("US_MARKET_DATA_AUTHORIZATION_ID is required for promotion")


async def run_onboarding(
    manifest: CohortManifest,
    *,
    resume_id: uuid.UUID | None = None,
    fetch: bool = True,
    promote: bool = False,
    publish_research: bool = False,
) -> dict[str, Any]:
    _validate_promotion(promote, manifest, publish_research=publish_research)
    run = (
        await _resume_run(resume_id, manifest, promote, publish_research)
        if resume_id
        else await create_onboarding_run(manifest, promote, publish_research)
    )
    print(f"[onboarding] run_id={run.id}", flush=True)
    try:
        fetch_stats: dict[str, Any] = {}
        if fetch:
            fetch_stats["security_master"] = await _checkpointed_stage(
                run.id,
                stage_key="security_master",
                ordinal=0,
                input_fingerprint=_stage_input_fingerprint(run, manifest, "security_master"),
                operation=lambda: collect_security_master(manifest.market),
            )
            fetch_stats["restricted_research_symbols"] = await _checkpointed_stage(
                run.id,
                stage_key="restricted_research_symbols",
                ordinal=1,
                input_fingerprint=_stage_input_fingerprint(
                    run, manifest, "restricted_research_symbols"
                ),
                operation=lambda: _stage_restricted_research_symbols(manifest),
            )
            fetch_stats["history"] = await _checkpointed_stage(
                run.id,
                stage_key="history",
                ordinal=2,
                input_fingerprint=_stage_input_fingerprint(run, manifest, "history"),
                operation=lambda: collect_history(
                    manifest.market,
                    days=round(manifest.backfill_years * 365.25),
                    codes=manifest.symbols,
                    include_reference=True,
                ),
            )
            fetch_stats["sec"] = await _checkpointed_stage(
                run.id,
                stage_key="sec",
                ordinal=3,
                input_fingerprint=_stage_input_fingerprint(run, manifest, "sec"),
                operation=lambda: collect_sec(codes=list(manifest.symbols)),
            )
            fetch_stats["analytics"] = await _checkpointed_stage(
                run.id,
                stage_key="analytics",
                ordinal=4,
                input_fingerprint=_stage_input_fingerprint(run, manifest, "analytics"),
                operation=lambda: compute_all(
                    manifest.market,
                    codes=list(manifest.symbols),
                    include_onboarding=True,
                    include_restricted=manifest.allow_restricted_research,
                ),
            )
        as_of_date = to_market_tz(dt.datetime.now(dt.UTC), market=manifest.market).date()
        evidence = await evaluate_cohort(
            manifest.market,
            manifest.symbols,
            manifest.policy,
            as_of_date=as_of_date,
        )
        passed, failed, published, research_only = await _persist_results(
            run,
            evidence,
            promote=promote,
            publish_research=publish_research,
        )
        failures = {row.code: row.failure_reasons for row in evidence if not row.passed}
        return {
            "run_id": str(run.id),
            "cohort": manifest.name,
            "version": manifest.version,
            "requested": len(manifest.symbols),
            "passed": passed,
            "failed": failed,
            "published": published,
            "research_only": research_only,
            "promotion_requested": promote or publish_research,
            "publication_mode": (
                "authorized"
                if promote
                else "owner_directed_research"
                if publish_research
                else "private"
            ),
            "fetch": fetch_stats,
            "failures": failures,
        }
    except asyncio.CancelledError:
        await _mark_failed(run.id, RuntimeError("onboarding cancelled before completion"))
        raise
    except Exception as error:
        await _mark_failed(run.id, error)
        raise


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run an auditable US cohort onboarding")
    parser.add_argument("manifest", help="versioned cohort JSON manifest")
    parser.add_argument("--resume", type=uuid.UUID, help="resume a failed/incomplete run UUID")
    parser.add_argument("--evaluate-only", action="store_true", help="skip network/data refresh")
    publication = parser.add_mutually_exclusive_group()
    publication.add_argument(
        "--promote",
        action="store_true",
        help="publish passing symbols under configured market-data authorization",
    )
    publication.add_argument(
        "--publish-research",
        action="store_true",
        help="open completed research; risk-gate failures remain research-only",
    )
    return parser.parse_args(argv)


def main() -> None:
    args = _parse_args(sys.argv[1:])
    manifest = load_cohort(args.manifest, "US")
    stats = asyncio.run(
        run_onboarding(
            manifest,
            resume_id=args.resume,
            fetch=not args.evaluate_only,
            promote=args.promote,
            publish_research=args.publish_research,
        )
    )
    print(f"[onboarding] done: {stats}", flush=True)


if __name__ == "__main__":
    main()
