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
        response, TokenOut(access_token="access", refresh_token="secret-refresh")
    )

    cookie = response.headers["set-cookie"]
    assert returned.refresh_token is None
    assert "bulls_refresh=secret-refresh" in cookie
    assert "HttpOnly" in cookie
    assert "Secure" in cookie
    assert "SameSite=lax" in cookie


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
