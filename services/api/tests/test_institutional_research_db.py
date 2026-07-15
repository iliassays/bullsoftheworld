"""PostgreSQL-gated contract checks for the institutional research boundary."""

from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import text

from api.institutional_research.queue import build_research_queue
from api.research_access import bind_research_tenant_context
from bulls.core.db import dispose_engine, get_sessionmaker

pytestmark = [
    pytest.mark.skipif(not os.getenv("DB_TESTS"), reason="set DB_TESTS=1 with Postgres"),
    pytest.mark.asyncio,
]


async def test_research_tables_force_tenant_market_row_security() -> None:
    await dispose_engine()
    try:
        async with get_sessionmaker()() as session:
            rows = (
                await session.execute(
                    text(
                        "SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity, p.qual "
                        "FROM pg_class c "
                        "JOIN pg_namespace n ON n.oid = c.relnamespace "
                        "JOIN pg_policies p ON p.schemaname = n.nspname "
                        "AND p.tablename = c.relname "
                        "WHERE n.nspname = current_schema() "
                        "AND c.relname LIKE 'research_%'"
                    )
                )
            ).all()

        direct_user_scope = {
            "research_organizations",
            "research_organization_memberships",
            "research_workspaces",
            "research_workspace_memberships",
            "research_runs",
            "research_audit_events",
        }
        lineage_scope = {
            "research_run_steps": "research_runs",
            "research_run_evidence": "research_runs",
            "research_claims": "research_runs",
            "research_claim_citations": "research_claims",
        }
        assert len(rows) == 12
        for table, enabled, forced, predicate in rows:
            assert enabled and forced, table
            assert "app.research_tenant_id" in predicate, table
            assert "app.research_market" in predicate, table
            if table in direct_user_scope:
                assert "app.research_user_id" in predicate, table
            if table in lineage_scope:
                assert lineage_scope[table] in predicate, table
    finally:
        await dispose_engine()


async def test_live_queue_never_crosses_the_bound_market() -> None:
    await dispose_engine()
    try:
        async with get_sessionmaker()() as session:
            for tenant_id, market in (("bullsofdhaka", "DSE"), ("bullsofwallst", "US")):
                await bind_research_tenant_context(
                    session,
                    tenant_id=tenant_id,
                    market=market,
                    user_id=0,
                )
                snapshot = await build_research_queue(
                    session,
                    tenant_id=tenant_id,
                    market=market,
                    workspace_id=uuid.uuid4(),
                    limit=5,
                )

                assert snapshot.tenant_id == tenant_id
                assert snapshot.market == market
                assert all(candidate.market == market for candidate in snapshot.candidates)
                assert all(
                    candidate.id.startswith(f"{market}:") for candidate in snapshot.candidates
                )

            await session.rollback()
    finally:
        await dispose_engine()


async def test_authenticated_research_api_isolates_dse_and_us_accounts() -> None:
    from httpx import ASGITransport, AsyncClient
    from sqlalchemy import delete

    from api.main import app, lifespan
    from bulls.core.models import RefreshSession, ResearchOrganization, User

    await dispose_engine()
    created_users: list[int] = []
    created_organizations: list[tuple[str, str, int, uuid.UUID]] = []
    try:
        async with (
            lifespan(app),
            AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
        ):
            tokens: dict[str, str] = {}
            for tenant_id, market, tenant_host in (
                ("bullsofdhaka", "DSE", "research.bullsofdhaka.com"),
                ("bullsofwallst", "US", "research.bullsofwallst.com"),
            ):
                identity = f"research-{tenant_id}-{uuid.uuid4().hex[:12]}@example.com"
                tenant_headers = {"X-Tenant-Host": tenant_host}
                registered = await client.post(
                    "/auth/register",
                    headers=tenant_headers,
                    json={
                        "name": "Research Boundary Test",
                        "contact": identity,
                        "password": "research-test-password",
                        "locale": "en",
                    },
                )
                assert registered.status_code == 201, registered.text
                token = registered.json()["access_token"]
                tokens[tenant_id] = token
                authorized = {**tenant_headers, "Authorization": f"Bearer {token}"}

                me = await client.get("/auth/me", headers=authorized)
                assert me.status_code == 200, me.text
                user_id = me.json()["id"]
                created_users.append(user_id)
                workspaces = await client.get(
                    "/institutional-research/workspaces",
                    headers=authorized,
                )
                assert workspaces.status_code == 200, workspaces.text
                assert workspaces.json() == []

                bootstrap = await client.post(
                    "/institutional-research/workspaces/bootstrap",
                    headers=authorized,
                )
                assert bootstrap.status_code == 201, bootstrap.text
                workspace = bootstrap.json()
                assert workspace["tenantId"] == tenant_id
                assert workspace["market"] == market

                second_bootstrap = await client.post(
                    "/institutional-research/workspaces/bootstrap",
                    headers=authorized,
                )
                assert second_bootstrap.status_code == 201, second_bootstrap.text
                assert second_bootstrap.json()["id"] == workspace["id"]
                created_organizations.append(
                    (
                        tenant_id,
                        market,
                        user_id,
                        uuid.UUID(workspace["organizationId"]),
                    )
                )

                queue = await client.get(
                    f"/institutional-research/workspaces/{workspace['id']}/queue?limit=3",
                    headers=authorized,
                )
                assert queue.status_code == 200, queue.text
                payload = queue.json()
                assert payload["tenantId"] == tenant_id
                assert payload["market"] == market
                assert all(candidate["market"] == market for candidate in payload["candidates"])

            replay = await client.get(
                "/institutional-research/workspaces",
                headers={
                    "X-Tenant-Host": "research.bullsofwallst.com",
                    "Authorization": f"Bearer {tokens['bullsofdhaka']}",
                },
            )
            assert replay.status_code == 401
    finally:
        async with get_sessionmaker()() as session:
            for tenant_id, market, user_id, organization_id in created_organizations:
                await bind_research_tenant_context(
                    session,
                    tenant_id=tenant_id,
                    market=market,
                    user_id=user_id,
                )
                await session.execute(
                    delete(ResearchOrganization).where(
                        ResearchOrganization.id == organization_id,
                        ResearchOrganization.tenant_id == tenant_id,
                        ResearchOrganization.market == market,
                    )
                )
                await session.commit()
            if created_users:
                await session.execute(
                    delete(RefreshSession).where(RefreshSession.user_id.in_(created_users))
                )
                await session.execute(delete(User).where(User.id.in_(created_users)))
                await session.commit()
        await dispose_engine()
