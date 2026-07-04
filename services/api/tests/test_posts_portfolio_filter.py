"""'/posts?portfolio=true' — genuinely holdings-scoped, distinct from '?watched=true' (watchlist).

Regression for a 2026-07-04 user report: the Home feed's "My stocks" chip was watchlist-only but
its label read as portfolio. This is the actually-held-shares filter added alongside the fix.

DB_TESTS=1 uv run pytest -k posts_portfolio_filter
"""

from __future__ import annotations

import os
import uuid

import pytest
from fastapi.testclient import TestClient


@pytest.mark.skipif(not os.getenv("DB_TESTS"), reason="set DB_TESTS=1 with Postgres")
def test_portfolio_filter_is_distinct_from_watchlist() -> None:
    from api.main import app

    with TestClient(app) as c:
        handle = "t" + uuid.uuid4().hex[:12]
        reg = c.post(
            "/auth/register",
            json={
                "name": "Feed Tester",
                "contact": f"{handle}@example.com",
                "password": "password123",
            },
        )
        assert reg.status_code == 201, reg.text
        hdr = {"Authorization": f"Bearer {reg.json()['access_token']}"}

        # GP: an actual holding. OLYMPIC: only watched, never held.
        assert (
            c.post(
                "/portfolio/holdings",
                json={"code": "GP", "quantity": 10, "avg_cost": 250.0},
                headers=hdr,
            ).status_code
            == 201
        )
        assert c.post("/watchlist", json={"code": "OLYMPIC"}, headers=hdr).status_code == 201

        held_post = c.post("/posts", json={"body": "$GP a note about a stock I hold"}, headers=hdr)
        assert held_post.status_code == 201, held_post.text
        watched_post = c.post(
            "/posts", json={"body": "$OLYMPIC a note about a stock I only watch"}, headers=hdr
        )
        assert watched_post.status_code == 201, watched_post.text

        portfolio_feed = c.get("/posts?kind=user&portfolio=true", headers=hdr).json()
        bodies = [p["body"] for p in portfolio_feed]
        assert any("I hold" in b for b in bodies)
        assert not any("I only watch" in b for b in bodies)

        watched_feed = c.get("/posts?kind=user&watched=true", headers=hdr).json()
        watched_bodies = [p["body"] for p in watched_feed]
        assert any("I only watch" in b for b in watched_bodies)
        # GP isn't watched (only held) — the watchlist filter must not silently include it too.
        assert not any("I hold" in b for b in watched_bodies)
