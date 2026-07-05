"""Public member profiles (/users/{handle}) — portfolio is opt-in and private by default.

DB_TESTS=1 uv run pytest -k users_profile
"""

from __future__ import annotations

import os
import uuid

import pytest
from fastapi.testclient import TestClient


@pytest.mark.skipif(not os.getenv("DB_TESTS"), reason="set DB_TESTS=1 with Postgres + ingestion")
def test_unknown_handle_404s() -> None:
    from api.main import app

    with TestClient(app) as c:
        assert c.get("/users/definitely-not-a-real-handle").status_code == 404


@pytest.mark.skipif(not os.getenv("DB_TESTS"), reason="set DB_TESTS=1 with Postgres + ingestion")
def test_portfolio_private_by_default_then_opt_in() -> None:
    """A holdings list is sensitive — nothing about it should be visible to anyone until the
    account holder explicitly flips the visibility switch themselves."""
    from api.main import app

    with TestClient(app) as c:
        handle_seed = "t" + uuid.uuid4().hex[:12]
        reg = c.post(
            "/auth/register",
            json={
                "name": "Public Profile Tester",
                "contact": f"{handle_seed}@example.com",
                "password": "password123",
            },
        )
        assert reg.status_code == 201, reg.text
        hdr = {"Authorization": f"Bearer {reg.json()['access_token']}"}
        handle = c.get("/auth/me", headers=hdr).json()["handle"]

        # Default: private. Both endpoints refuse to leak anything.
        prof = c.get(f"/users/{handle}").json()
        assert prof["portfolio_public"] is False
        assert c.get(f"/users/{handle}/portfolio").status_code == 404
        assert c.get(f"/users/{handle}/portfolio/history").status_code == 404

        # No one else can flip it on for them — only the signed-in owner, via /portfolio/visibility.
        assert c.patch("/portfolio/visibility", json={"public": True}).status_code in (401, 403)

        r = c.post(
            "/portfolio/holdings",
            json={"code": "GP", "quantity": 100, "avg_cost": 250.0},
            headers=hdr,
        )
        assert r.status_code == 201, r.text

        vis = c.patch("/portfolio/visibility", json={"public": True}, headers=hdr)
        assert vis.status_code == 200 and vis.json() == {"public": True}

        prof = c.get(f"/users/{handle}").json()
        assert prof["portfolio_public"] is True

        pf = c.get(f"/users/{handle}/portfolio").json()
        assert len(pf["holdings"]) == 1 and pf["holdings"][0]["code"] == "GP"
        # Never leak the viewer-specific alert fields onto a public profile — they don't even
        # appear in the schema (PublicHoldingOut has no latest_alert_title/has_price_alert).
        assert "latest_alert_title" not in pf["holdings"][0]
        assert "has_price_alert" not in pf["holdings"][0]

        hist = c.get(f"/users/{handle}/portfolio/history?period=all")
        assert hist.status_code == 200 and hist.json() == []  # no snapshot yet, honestly empty
        assert c.get(f"/users/{handle}/portfolio/history?period=bogus").status_code == 422

        # Opting back out re-locks both endpoints immediately.
        c.patch("/portfolio/visibility", json={"public": False}, headers=hdr)
        assert c.get(f"/users/{handle}/portfolio").status_code == 404

        c.delete("/portfolio/holdings/GP", headers=hdr)
