from __future__ import annotations

import datetime as dt
import os
import uuid

import pytest
from sqlalchemy import delete, select

from api.routers import on_demand_research
from api.routers.on_demand_research import _retry_allowed
from bulls.core.db import dispose_engine, get_sessionmaker
from bulls.core.models import (
    OnDemandResearchJob,
    OnDemandResearchRequest,
    Symbol,
    UniverseOnboardingResult,
    User,
)
from bulls.core.tenancy import Tenant


def _job(status: str, completed_at: dt.datetime | None = None) -> OnDemandResearchJob:
    return OnDemandResearchJob(
        market="US",
        code="CDIO",
        status=status,
        attempts=1,
        request_count=1,
        completed_at=completed_at,
    )


def test_failed_jobs_can_retry_but_recent_rejections_wait_for_new_evidence() -> None:
    now = dt.datetime(2026, 7, 11, tzinfo=dt.UTC)

    assert _retry_allowed(_job("failed", now), now)
    assert not _retry_allowed(_job("rejected", now - dt.timedelta(days=29)), now)
    assert _retry_allowed(_job("rejected", now - dt.timedelta(days=30)), now)
    assert not _retry_allowed(_job("review_required", now), now)


def test_passed_staged_symbol_has_no_manual_review_state() -> None:
    symbol = Symbol(
        market="US",
        code="VEEE",
        name_en="Twin Vee PowerCats Co.",
        is_active=True,
        is_hidden=False,
        data_status="onboarding",
    )
    result = UniverseOnboardingResult(
        run_id=uuid.uuid4(),
        market="US",
        code="VEEE",
        decision="passed",
        required_gates_passed=True,
        gates={},
        failure_reasons=[],
        bar_count=1249,
        sec_filings_count=185,
        sec_facts_count=348,
        has_13f=True,
    )

    assert on_demand_research._preparation_status(symbol, None, result) == "ready"


def test_failed_staged_symbol_is_not_reported_as_still_preparing() -> None:
    symbol = Symbol(
        market="US",
        code="VMAR",
        name_en="Vision Marine Technologies Inc.",
        is_active=True,
        is_hidden=False,
        data_status="onboarding",
    )
    result = UniverseOnboardingResult(
        run_id=uuid.uuid4(),
        market="US",
        code="VMAR",
        decision="failed",
        required_gates_passed=False,
        gates={},
        failure_reasons=["nonzero_volume"],
        bar_count=1412,
        sec_filings_count=176,
        sec_facts_count=6,
        has_13f=True,
    )

    assert on_demand_research._preparation_status(symbol, None, result) == "rejected"


@pytest.mark.skipif(not os.getenv("DB_TESTS"), reason="set DB_TESTS=1 with local Postgres")
@pytest.mark.asyncio
async def test_request_is_persisted_and_enqueued_once(monkeypatch) -> None:
    await dispose_engine()
    sm = get_sessionmaker()
    suffix = uuid.uuid4().hex[:10]
    tenant = Tenant(
        name="bullsofwallst",
        display_name="Bulls of Wall St",
        market="US",
        locale="en",
        timezone="America/New_York",
        site_url="https://example.com",
        support_email="support@example.com",
        email_from="Example <no-reply@example.com>",
        logo_url="https://example.com/logo.png",
        tagline_en="Facts first",
        tagline_bn="Facts first",
    )
    queued: list[tuple[str, str, int]] = []

    async def fake_enqueue(job_id: str, code: str, attempt: int) -> None:
        queued.append((job_id, code, attempt))

    monkeypatch.setattr(on_demand_research, "enqueue_us_research_preparation", fake_enqueue)
    user_id = None
    original_status = None
    try:
        async with sm() as session:
            symbol = await session.get(Symbol, ("US", "CDIO"))
            if symbol is None:
                pytest.skip("refresh the local US security master first")
            existing_job = await session.scalar(
                select(OnDemandResearchJob.id).where(
                    OnDemandResearchJob.market == "US",
                    OnDemandResearchJob.code == "CDIO",
                )
            )
            if existing_job is not None:
                pytest.skip("CDIO already has local preparation history")
            original_status = symbol.data_status
            symbol.data_status = "reference_only"
            user = User(
                tenant_id=tenant.name,
                handle=f"research_{suffix}",
                name="Research Test",
                password_hash="not-used",
                locale="en",
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
            user_id = user.id

            first = await on_demand_research.request_preparation("CDIO", user, tenant, session)
            second = await on_demand_research.request_preparation("CDIO", user, tenant, session)

            assert first.status == "queued"
            assert second.status == "queued"
            assert len(queued) == 1
            assert queued[0][1:] == ("CDIO", 1)
            assert second.request_count == 2
    finally:
        async with sm() as session:
            jobs = list(
                await session.scalars(
                    select(OnDemandResearchJob).where(
                        OnDemandResearchJob.market == "US",
                        OnDemandResearchJob.code == "CDIO",
                    )
                )
            )
            if jobs:
                job_ids = [job.id for job in jobs]
                await session.execute(
                    delete(OnDemandResearchRequest).where(
                        OnDemandResearchRequest.job_id.in_(job_ids)
                    )
                )
                await session.execute(
                    delete(OnDemandResearchJob).where(OnDemandResearchJob.id.in_(job_ids))
                )
            if user_id is not None:
                await session.execute(delete(User).where(User.id == user_id))
            symbol = await session.get(Symbol, ("US", "CDIO"))
            if symbol is not None and original_status is not None:
                symbol.data_status = original_status
            await session.commit()
        await dispose_engine()
