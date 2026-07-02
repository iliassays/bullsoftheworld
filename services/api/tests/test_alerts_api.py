"""Alerts API flow — DB-gated like the other endpoint tests.

DB_TESTS=1 uv run pytest -k alerts_api
"""

from __future__ import annotations

import os
import uuid

import pytest
from fastapi.testclient import TestClient


@pytest.mark.skipif(not os.getenv("DB_TESTS"), reason="set DB_TESTS=1 with Postgres + ingestion")
def test_alerts_flow() -> None:
    from api.main import app

    with TestClient(app) as c:
        handle = "t" + uuid.uuid4().hex[:12]
        reg = c.post(
            "/auth/register",
            json={
                "handle": handle,
                "name": "Alert Tester",
                "email": f"{handle}@example.com",
                "password": "password123",
            },
        )
        assert reg.status_code == 201, reg.text
        hdr = {"Authorization": f"Bearer {reg.json()['access_token']}"}

        # fresh user: empty inbox, zero unread
        assert c.get("/alerts", headers=hdr).json() == []
        assert c.get("/alerts/unread-count", headers=hdr).json()["unread"] == 0

        # price alerts CRUD
        r = c.post(
            "/alerts/price",
            json={"code": "gp", "level": 300.0, "direction": "above"},
            headers=hdr,
        )
        assert r.status_code == 201, r.text
        alert_id = r.json()["id"]
        assert r.json()["code"] == "GP"

        lst = c.get("/alerts/price", params={"code": "GP"}, headers=hdr).json()
        assert [a["id"] for a in lst] == [alert_id]

        # unknown symbol and bad direction rejected
        assert (
            c.post(
                "/alerts/price",
                json={"code": "NOTREAL", "level": 1, "direction": "above"},
                headers=hdr,
            ).status_code
            == 404
        )
        assert (
            c.post(
                "/alerts/price",
                json={"code": "GP", "level": 1, "direction": "sideways"},
                headers=hdr,
            ).status_code
            == 422
        )

        assert c.delete(f"/alerts/price/{alert_id}", headers=hdr).status_code == 204
        assert c.get("/alerts/price", headers=hdr).json() == []

        # mark-read is idempotent on an empty inbox
        assert c.post("/alerts/mark-read", headers=hdr).json()["status"] == "ok"

        # anonymous is rejected
        assert c.get("/alerts").status_code in (401, 403)
