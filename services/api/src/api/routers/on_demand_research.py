"""Authenticated, deduplicated preparation requests for US reference securities."""

from __future__ import annotations

import datetime as dt
import re
import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from api.deps import CurrentTenant, CurrentUser, DbSession
from api.queue import enqueue_us_research_preparation
from bulls.core.config import get_settings
from bulls.core.models import (
    OnDemandResearchJob,
    OnDemandResearchRequest,
    SecurityMaster,
    Symbol,
    UniverseOnboardingResult,
)

router = APIRouter(tags=["on-demand-research"])
_CODE_RE = re.compile(r"^[A-Z0-9.-]{1,16}$")
_REJECTED_RETRY_AFTER = dt.timedelta(days=30)


class ResearchPreparationOut(BaseModel):
    code: str
    status: str
    symbol_status: str
    run_id: uuid.UUID | None
    attempts: int
    request_count: int
    requested_at: dt.datetime | None
    started_at: dt.datetime | None
    completed_at: dt.datetime | None
    failure_reasons: list[str]
    can_open: bool
    disclosure: str


def _retry_allowed(job: OnDemandResearchJob, now: dt.datetime) -> bool:
    if job.status == "failed":
        return True
    return bool(
        job.status == "rejected"
        and job.completed_at is not None
        and now - job.completed_at >= _REJECTED_RETRY_AFTER
    )


async def _failure_reasons(session, job: OnDemandResearchJob | None) -> list[str]:
    if job is None or job.run_id is None:
        return []
    result = await session.scalar(
        select(UniverseOnboardingResult).where(
            UniverseOnboardingResult.run_id == job.run_id,
            UniverseOnboardingResult.code == job.code,
        )
    )
    return list(result.failure_reasons or []) if result else []


async def _response(
    session,
    symbol: Symbol,
    job: OnDemandResearchJob | None,
) -> ResearchPreparationOut:
    ready = symbol.data_status == "ready"
    status = "ready" if ready else (job.status if job else symbol.data_status)
    return ResearchPreparationOut(
        code=symbol.code,
        status=status,
        symbol_status=symbol.data_status,
        run_id=job.run_id if job else None,
        attempts=job.attempts if job else 0,
        request_count=job.request_count if job else 0,
        requested_at=job.requested_at if job else None,
        started_at=job.started_at if job else None,
        completed_at=job.completed_at if job else None,
        failure_reasons=await _failure_reasons(session, job),
        can_open=ready,
        disclosure=(
            "Preparation collects delayed market and public filing evidence. "
            "Institutional disclosures are historical evidence, not trade instructions."
        ),
    )


async def _symbol_and_security(session, market: str, code: str):
    symbol = await session.get(Symbol, (market, code))
    security = await session.scalar(
        select(SecurityMaster).where(
            SecurityMaster.market == market,
            SecurityMaster.symbol == code,
            SecurityMaster.is_active.is_(True),
            SecurityMaster.is_product_eligible.is_(True),
        )
    )
    if symbol is None or security is None:
        raise HTTPException(status_code=404, detail=f"Unknown active US security {code!r}")
    if security.instrument_type != "common_stock":
        raise HTTPException(
            status_code=422,
            detail="On-demand preparation currently supports US common stocks only",
        )
    return symbol, security


@router.get("/research-preparations/{code}")
async def preparation_status(
    code: str,
    user: CurrentUser,
    tenant: CurrentTenant,
    session: DbSession,
) -> ResearchPreparationOut:
    del user
    code = code.strip().upper()
    if tenant.market != "US" or not _CODE_RE.fullmatch(code):
        raise HTTPException(status_code=404, detail="On-demand research is unavailable")
    symbol, _ = await _symbol_and_security(session, tenant.market, code)
    job = await session.scalar(
        select(OnDemandResearchJob).where(
            OnDemandResearchJob.market == tenant.market,
            OnDemandResearchJob.code == code,
        )
    )
    return await _response(session, symbol, job)


@router.post("/research-preparations/{code}")
async def request_preparation(
    code: str,
    user: CurrentUser,
    tenant: CurrentTenant,
    session: DbSession,
) -> ResearchPreparationOut:
    code = code.strip().upper()
    if tenant.market != "US" or not _CODE_RE.fullmatch(code):
        raise HTTPException(status_code=404, detail="On-demand research is unavailable")
    symbol, _ = await _symbol_and_security(session, tenant.market, code)
    if symbol.data_status == "ready":
        return await _response(session, symbol, None)

    now = dt.datetime.now(dt.UTC)
    today = now.date()
    await session.scalar(select(func.pg_advisory_xact_lock(user.id)))
    existing_request = await session.scalar(
        select(OnDemandResearchRequest.id).where(
            OnDemandResearchRequest.tenant_id == tenant.name,
            OnDemandResearchRequest.user_id == user.id,
            OnDemandResearchRequest.market == tenant.market,
            OnDemandResearchRequest.code == code,
            OnDemandResearchRequest.request_date == today,
        )
    )
    if existing_request is None:
        used = await session.scalar(
            select(func.count())
            .select_from(OnDemandResearchRequest)
            .where(
                OnDemandResearchRequest.tenant_id == tenant.name,
                OnDemandResearchRequest.user_id == user.id,
                OnDemandResearchRequest.request_date == today,
            )
        )
        if int(used or 0) >= get_settings().on_demand_research_daily_limit:
            raise HTTPException(status_code=429, detail="Daily research preparation limit reached")

    inserted = await session.execute(
        pg_insert(OnDemandResearchJob)
        .values(
            market=tenant.market,
            code=code,
            status="queued",
            attempts=0,
            request_count=0,
            requested_at=now,
        )
        .on_conflict_do_nothing(index_elements=["market", "code"])
    )
    job = await session.scalar(
        select(OnDemandResearchJob)
        .where(
            OnDemandResearchJob.market == tenant.market,
            OnDemandResearchJob.code == code,
        )
        .with_for_update()
    )
    if job is None:
        raise RuntimeError(f"on-demand research job disappeared for {code}")
    created = bool(inserted.rowcount)
    should_enqueue = created or _retry_allowed(job, now)
    if should_enqueue:
        job.status = "queued"
        job.error = None
        job.completed_at = None
        symbol.data_status = "onboarding"
    job.request_count += 1
    job.requested_at = now

    await session.execute(
        pg_insert(OnDemandResearchRequest)
        .values(
            job_id=job.id,
            tenant_id=tenant.name,
            user_id=user.id,
            market=tenant.market,
            code=code,
            request_date=today,
            requested_at=now,
        )
        .on_conflict_do_nothing(
            index_elements=["tenant_id", "user_id", "market", "code", "request_date"]
        )
    )
    await session.commit()

    if should_enqueue:
        try:
            await enqueue_us_research_preparation(str(job.id), code, job.attempts + 1)
        except Exception as error:
            job = await session.get(OnDemandResearchJob, job.id)
            symbol = await session.get(Symbol, (tenant.market, code))
            if job is not None:
                job.status = "failed"
                job.error = f"QueueUnavailable: {error}"[:2000]
                job.completed_at = dt.datetime.now(dt.UTC)
            if symbol is not None and symbol.data_status == "onboarding":
                symbol.data_status = "reference_only"
            await session.commit()
            raise HTTPException(
                status_code=503,
                detail="Research queue is temporarily unavailable",
            ) from error

    job = await session.get(OnDemandResearchJob, job.id)
    symbol = await session.get(Symbol, (tenant.market, code))
    if job is None or symbol is None:
        raise RuntimeError(f"on-demand research state disappeared for {code}")
    return await _response(session, symbol, job)
