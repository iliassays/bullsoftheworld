"""Refresh-token/session security — unit + DB-gated rotation flow.

DB_TESTS=1 uv run pytest -k auth_sessions
"""

from __future__ import annotations

import os
import uuid
from types import SimpleNamespace

import pytest
from fastapi import Response
from fastapi.testclient import TestClient

from bulls.core.schemas.social import TokenOut
from bulls.core.security import hash_refresh, new_refresh_token


def _tenant(name: str = "bullsofdhaka") -> SimpleNamespace:
    return SimpleNamespace(name=name)


def test_refresh_tokens_are_long_unique_and_opaque() -> None:
    tokens = {new_refresh_token() for _ in range(64)}
    assert len(tokens) == 64
    t = next(iter(tokens))
    assert len(t) >= 60  # 48 bytes urlsafe → 64 chars
    assert "." not in t  # not a JWT — carries nothing


def test_hash_refresh_is_deterministic_sha256() -> None:
    t = new_refresh_token()
    assert hash_refresh(t) == hash_refresh(t)
    assert len(hash_refresh(t)) == 64
    assert hash_refresh(t) != hash_refresh(t + "x")


def test_production_refresh_token_is_httponly_cookie(monkeypatch) -> None:
    from api.routers import auth

    monkeypatch.setattr(
        auth,
        "get_settings",
        lambda: SimpleNamespace(
            refresh_cookie_name="bulls_refresh",
            refresh_token_ttl_days=60,
            refresh_cookie_samesite="lax",
            production_cookies=True,
        ),
    )
    response = Response()
    returned = auth._browser_tokens(
        response,
        TokenOut(access_token="access", refresh_token="secret-refresh"),
        _tenant(),
    )

    cookie = response.headers["set-cookie"]
    assert returned.refresh_token is None
    assert "bulls_refresh_bullsofdhaka=secret-refresh" in cookie
    assert "HttpOnly" in cookie
    assert "Secure" in cookie
    assert "SameSite=lax" in cookie


def test_refresh_cookie_names_are_tenant_specific(monkeypatch) -> None:
    from api.routers import auth

    monkeypatch.setattr(
        auth,
        "get_settings",
        lambda: SimpleNamespace(refresh_cookie_name="bulls_refresh"),
    )
    assert auth._refresh_cookie_name(_tenant("bullsofdhaka")) == "bulls_refresh_bullsofdhaka"
    assert auth._refresh_cookie_name(_tenant("bullsofwallst")) == "bulls_refresh_bullsofwallst"


def test_security_headers_on_every_response() -> None:
    from api.main import app

    with TestClient(app) as c:
        r = c.get("/health")
        assert r.headers["X-Content-Type-Options"] == "nosniff"
        assert r.headers["X-Frame-Options"] == "DENY"
        assert "Strict-Transport-Security" in r.headers
        assert "Referrer-Policy" in r.headers


@pytest.mark.skipif(not os.getenv("DB_TESTS"), reason="set DB_TESTS=1 with Postgres + ingestion")
def test_refresh_rotation_and_reuse_detection() -> None:
    from api.main import app

    with TestClient(app) as c:
        handle = "t" + uuid.uuid4().hex[:12]
        reg = c.post(
            "/auth/register",
            json={
                "handle": handle,
                "name": "Session Tester",
                "contact": f"{handle}@example.com",
                "password": "password123",
            },
        ).json()
        assert reg["refresh_token"]
        rt1 = reg["refresh_token"]

        # rotation: rt1 → rt2 (new pair, old token retired)
        r2 = c.post("/auth/refresh", json={"refresh_token": rt1})
        assert r2.status_code == 200, r2.text
        rt2 = r2.json()["refresh_token"]
        assert rt2 and rt2 != rt1

        # reuse of the retired rt1 = replay → the WHOLE family dies, including rt2
        assert c.post("/auth/refresh", json={"refresh_token": rt1}).status_code == 401
        assert c.post("/auth/refresh", json={"refresh_token": rt2}).status_code == 401

        # fresh login works and logout revokes that session
        login = c.post(
            "/auth/login", json={"identifier": f"{handle}@example.com", "password": "password123"}
        ).json()
        rt3 = login["refresh_token"]
        assert c.post("/auth/logout", json={"refresh_token": rt3}).status_code == 200
        assert c.post("/auth/refresh", json={"refresh_token": rt3}).status_code == 401

        # garbage token is rejected without information leakage
        assert c.post("/auth/refresh", json={"refresh_token": "nonsense"}).status_code == 401


@pytest.mark.skipif(not os.getenv("DB_TESTS"), reason="set DB_TESTS=1 with Postgres + ingestion")
@pytest.mark.asyncio
async def test_same_identity_has_independent_dse_and_us_accounts() -> None:
    from httpx import ASGITransport, AsyncClient
    from sqlalchemy import delete

    from api.main import app, lifespan
    from bulls.core.db import bind_tenant_context, dispose_engine, get_sessionmaker
    from bulls.core.models import RefreshSession, User

    shared_email = f"tenant-bound-{uuid.uuid4().hex[:12]}@example.com"
    tenants = {
        "bullsofdhaka": "research.bullsofdhaka.com",
        "bullsofwallst": "research.bullsofwallst.com",
    }
    user_ids: dict[str, int] = {}
    await dispose_engine()
    try:
        async with (
            lifespan(app),
            AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
        ):
            sessions: dict[str, dict] = {}
            for tenant_id, host in tenants.items():
                response = await client.post(
                    "/auth/register",
                    headers={"X-Tenant-Host": host},
                    json={
                        "name": "Tenant Boundary",
                        "contact": shared_email,
                        "password": f"password-{tenant_id}",
                        "locale": "en",
                    },
                )
                assert response.status_code == 201, response.text
                sessions[tenant_id] = response.json()
                assert f"bulls_refresh_{tenant_id}=" in response.headers.get("set-cookie", "")
                me = await client.get(
                    "/auth/me",
                    headers={
                        "X-Tenant-Host": host,
                        "Authorization": f"Bearer {response.json()['access_token']}",
                    },
                )
                assert me.status_code == 200, me.text
                user_ids[tenant_id] = me.json()["id"]

            assert user_ids["bullsofdhaka"] != user_ids["bullsofwallst"]

            replay = await client.get(
                "/auth/me",
                headers={
                    "X-Tenant-Host": tenants["bullsofwallst"],
                    "Authorization": f"Bearer {sessions['bullsofdhaka']['access_token']}",
                },
            )
            assert replay.status_code == 401

            cross_refresh = await client.post(
                "/auth/refresh",
                headers={"X-Tenant-Host": tenants["bullsofwallst"]},
                json={"refresh_token": sessions["bullsofdhaka"]["refresh_token"]},
            )
            assert cross_refresh.status_code == 401
            own_refresh = await client.post(
                "/auth/refresh",
                headers={"X-Tenant-Host": tenants["bullsofdhaka"]},
                json={"refresh_token": sessions["bullsofdhaka"]["refresh_token"]},
            )
            assert own_refresh.status_code == 200, own_refresh.text

            wrong_password = await client.post(
                "/auth/login",
                headers={"X-Tenant-Host": tenants["bullsofwallst"]},
                json={
                    "identifier": shared_email,
                    "password": "password-bullsofdhaka",
                },
            )
            assert wrong_password.status_code == 401
    finally:
        sessionmaker = get_sessionmaker()
        for tenant_id, user_id in user_ids.items():
            async with sessionmaker() as session:
                await bind_tenant_context(session, tenant_id)
                await session.execute(
                    delete(RefreshSession).where(
                        RefreshSession.tenant_id == tenant_id,
                        RefreshSession.user_id == user_id,
                    )
                )
                await session.execute(
                    delete(User).where(User.tenant_id == tenant_id, User.id == user_id)
                )
                await session.commit()
        await dispose_engine()


@pytest.mark.skipif(not os.getenv("DB_TESTS"), reason="set DB_TESTS=1 with Postgres + ingestion")
@pytest.mark.asyncio
async def test_private_account_tables_force_tenant_rls() -> None:
    from sqlalchemy import text

    from bulls.core.db import dispose_engine, get_sessionmaker

    expected = {
        "users",
        "refresh_sessions",
        "watchlist_items",
        "portfolio_holdings",
        "portfolio_snapshots",
        "post_reactions",
        "quiz_answers",
        "alert_events",
        "price_alerts",
        "on_demand_research_requests",
        "follows",
    }
    await dispose_engine()
    try:
        async with get_sessionmaker()() as session:
            rows = (
                await session.execute(
                    text(
                        "SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity, p.qual "
                        "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                        "JOIN pg_policies p ON p.schemaname = n.nspname "
                        "AND p.tablename = c.relname "
                        "WHERE n.nspname = current_schema() AND c.relname = ANY(:tables)"
                    ),
                    {"tables": list(expected)},
                )
            ).all()
        assert {row[0] for row in rows} == expected
        for table, enabled, forced, predicate in rows:
            assert enabled and forced, table
            assert "app.tenant_id" in predicate, table
    finally:
        await dispose_engine()
