"""Social flow tests.

parse_cashtags is a pure unit test (always runs). The end-to-end flow is opt-in and needs
Postgres up + ingestion to have run (so GP exists as a symbol):
    DB_TESTS=1 uv run pytest -k social
"""

from __future__ import annotations

import os
import uuid

import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.routers.posts import parse_cashtags


def test_parse_cashtags_dedup_and_uppercase():
    assert parse_cashtags("buying $gp and $BEXIMCO, $gp again") == ["GP", "BEXIMCO"]
    assert parse_cashtags("no tags here") == []


@pytest.mark.skipif(not os.getenv("DB_TESTS"), reason="set DB_TESTS=1 with Postgres + ingestion")
def test_social_flow_end_to_end():
    with TestClient(app) as c:
        handle = "t" + uuid.uuid4().hex[:12]
        auth_hdr = {}

        reg = c.post(
            "/auth/register",
            json={"handle": handle, "name": "Test User", "password": "password123"},
        )
        assert reg.status_code == 201, reg.text
        auth_hdr = {"Authorization": f"Bearer {reg.json()['access_token']}"}

        assert c.get("/auth/me", headers=auth_hdr).json()["handle"] == handle

        # post with a real cashtag (GP) and a bogus one (filtered out)
        p = c.post(
            "/posts",
            json={"body": "bullish on $GP, ignore $NOTREAL", "sentiment": "bull"},
            headers=auth_hdr,
        )
        assert p.status_code == 201, p.text
        post = p.json()
        assert post["cashtags"] == ["GP"]
        assert post["sentiment"] == "bull"

        # appears in global feed and in the GP-filtered feed
        assert any(x["id"] == post["id"] for x in c.get("/posts").json())
        assert any(x["id"] == post["id"] for x in c.get("/posts", params={"code": "GP"}).json())

        # watchlist add / list / remove
        assert c.post("/watchlist", json={"code": "gp"}, headers=auth_hdr).status_code == 201
        wl = c.get("/watchlist", headers=auth_hdr).json()
        assert any(item["symbol"]["code"] == "GP" for item in wl)
        assert c.delete("/watchlist/GP", headers=auth_hdr).status_code == 204

        # posting without a token is rejected
        assert c.post("/posts", json={"body": "x"}).status_code in (401, 403)
