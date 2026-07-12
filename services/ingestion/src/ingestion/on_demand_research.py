"""Single-security, resumable US research preparation for explicit user requests."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import uuid
from typing import Any

from sqlalchemy import or_, select

from bulls.core.db import get_sessionmaker
from bulls.core.models import OnDemandResearchJob, SecurityMaster, Symbol
from ingestion.cohorts import CohortManifest
from ingestion.universe_onboarding import create_onboarding_run, run_onboarding

MARKET = "US"
_LOCK_KEY = "ingestion:US:on-demand-research-lock"
_LOCK_TTL_SECONDS = 2 * 60 * 60
_STALE_RUNNING_AFTER = dt.timedelta(hours=2, minutes=15)
_RECONCILE_BATCH_SIZE = 100


def on_demand_manifest(code: str, *, generated_at: dt.datetime) -> CohortManifest:
    """Build a strict but cap-band-neutral manifest for one requested common stock."""
    version = generated_at.strftime("%Y%m%dT%H%M%SZ")
    payload: dict[str, Any] = {
        "schema_version": 1,
        "name": f"on-demand-{code}",
        "version": version,
        "market": MARKET,
        "backfill_years": 10,
        "description": (
            "User-requested private research preparation; enhanced-risk review and market-data "
            "authorization remain required before public promotion."
        ),
        "risk_review_id": None,
        "policy": {
            "allowed_instrument_types": ["common_stock"],
            "min_bars": 252,
            "min_history_days": 365,
            "max_staleness_days": 10,
            "min_adjusted_close_ratio": 0.98,
            "min_nonzero_volume_ratio": 0.95,
            "require_cik_for": ["common_stock"],
            "sec_filings_required_for": ["common_stock"],
            "sec_facts_required_for": ["common_stock"],
            "min_sec_filings": 1,
            "min_sec_facts": 5,
            "require_analytics": True,
            "require_13f": False,
            "min_market_cap_mn": 1.0,
            "max_market_cap_mn": None,
            "min_adtv_mn": 0.05,
            "min_price": 0.10,
            "requires_risk_review": True,
        },
        "symbols": [code],
    }
    manifest_sha = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return CohortManifest.model_validate({**payload, "manifest_sha256": manifest_sha})


async def _set_job_running(job_id: uuid.UUID) -> OnDemandResearchJob | None:
    sm = get_sessionmaker()
    async with sm() as session:
        job = await session.scalar(
            select(OnDemandResearchJob).where(OnDemandResearchJob.id == job_id).with_for_update()
        )
        if job is None or job.status not in {"queued", "failed"}:
            return None
        job.status = "running"
        job.attempts += 1
        job.started_at = dt.datetime.now(dt.UTC)
        job.completed_at = None
        job.error = None
        await session.commit()
        return job


async def _validate_security(code: str) -> None:
    sm = get_sessionmaker()
    async with sm() as session:
        security = await session.scalar(
            select(SecurityMaster).where(
                SecurityMaster.market == MARKET,
                SecurityMaster.symbol == code,
                SecurityMaster.is_active.is_(True),
                SecurityMaster.is_product_eligible.is_(True),
                SecurityMaster.instrument_type == "common_stock",
            )
        )
        if security is None:
            raise ValueError(f"{code} is not an eligible active US common stock")


async def _attach_run(job_id: uuid.UUID, run_id: uuid.UUID) -> None:
    sm = get_sessionmaker()
    async with sm() as session:
        job = await session.get(OnDemandResearchJob, job_id)
        if job is None:
            raise RuntimeError(f"research job {job_id} disappeared")
        job.run_id = run_id
        await session.commit()


async def _finish_job(
    job_id: uuid.UUID,
    *,
    status: str,
    error: str | None = None,
) -> None:
    sm = get_sessionmaker()
    async with sm() as session:
        job = await session.get(OnDemandResearchJob, job_id)
        if job is None:
            return
        job.status = status
        job.error = error[:2000] if error else None
        job.completed_at = dt.datetime.now(dt.UTC)
        symbol = await session.get(Symbol, (job.market, job.code))
        if symbol is not None and status in {"rejected", "failed"}:
            symbol.data_status = "degraded"
        await session.commit()


async def reconcile_on_demand_research(ctx) -> int:
    """Re-enqueue durable requests and recover work abandoned by a dead worker."""
    redis = ctx.get("redis") if ctx else None
    if redis is None:
        raise RuntimeError("on-demand reconciliation requires the worker Redis context")

    now = dt.datetime.now(dt.UTC)
    stale_before = now - _STALE_RUNNING_AFTER
    sm = get_sessionmaker()
    async with sm() as session:
        jobs = list(
            (
                await session.scalars(
                    select(OnDemandResearchJob)
                    .where(
                        or_(
                            OnDemandResearchJob.status == "queued",
                            (
                                (OnDemandResearchJob.status == "running")
                                & (OnDemandResearchJob.started_at < stale_before)
                            ),
                        )
                    )
                    .order_by(OnDemandResearchJob.requested_at, OnDemandResearchJob.id)
                    .limit(_RECONCILE_BATCH_SIZE)
                    .with_for_update(skip_locked=True)
                )
            ).all()
        )
        dispatches: list[tuple[str, str, int]] = []
        for job in jobs:
            if job.status == "running":
                job.status = "queued"
                job.error = "Recovered after the research worker lease expired"
                job.completed_at = None
            dispatches.append((str(job.id), job.code, job.attempts + 1))
        await session.commit()

    for job_id, code, attempt in dispatches:
        await redis.enqueue_job(
            "prepare_on_demand_research",
            job_id,
            _job_id=f"research:US:{code}:{attempt}",
        )
    return len(dispatches)


async def prepare_on_demand_research(ctx, job_id: str) -> str:
    parsed_job_id = uuid.UUID(job_id)
    redis = ctx.get("redis") if ctx else None
    if redis is None:
        raise RuntimeError("on-demand preparation requires the worker Redis context")
    acquired = await redis.set(_LOCK_KEY, job_id, ex=_LOCK_TTL_SECONDS, nx=True)
    if not acquired:
        from arq import Retry

        raise Retry(defer=60)

    job = None
    try:
        job = await _set_job_running(parsed_job_id)
        if job is None:
            return "skipped: job is no longer queued"
        await _validate_security(job.code)
        manifest = on_demand_manifest(job.code, generated_at=dt.datetime.now(dt.UTC))
        run = await create_onboarding_run(manifest)
        await _attach_run(job.id, run.id)
        result = await run_onboarding(manifest, resume_id=run.id, fetch=True, promote=False)
        passed = result["passed"] == 1
        await _finish_job(job.id, status="review_required" if passed else "rejected")
        return (
            f"code={job.code} status={'review_required' if passed else 'rejected'} run_id={run.id}"
        )
    except Exception as error:
        if job is not None:
            await _finish_job(
                job.id,
                status="failed",
                error=f"{type(error).__name__}: {error}",
            )
        raise
    finally:
        owner = await redis.get(_LOCK_KEY)
        if owner in {job_id, job_id.encode()}:
            await redis.delete(_LOCK_KEY)
