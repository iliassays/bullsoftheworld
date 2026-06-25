"""Buzz attention tests.

The threshold helpers are pure (always run). The endpoint flow is opt-in and needs Postgres up +
ingestion (so GP exists):
    DB_TESTS=1 uv run pytest -k buzz
"""

from __future__ import annotations

import os
import uuid

import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.routers.buzz import attention_label, shown_watcher_delta


def test_attention_label_thresholds():
    assert attention_label(0, None) == "quiet"  # zero chatter is quiet without a baseline
    assert attention_label(8, None) is None  # can't judge "rising" with no baseline yet
    assert attention_label(8, 1.0) == "rising"  # 8x baseline, well above the post floor
    assert attention_label(3, 1.0) == "normal"  # 3x but below the 5-post floor
    assert attention_label(10, 8.0) == "normal"  # only 1.25x baseline


def test_shown_watcher_delta_suppresses_thin_signal():
    assert shown_watcher_delta(50, 12) == 12
    assert shown_watcher_delta(50, 3) is None  # moved too little
    assert shown_watcher_delta(10, 8) is None  # too few watchers to mean anything
    assert shown_watcher_delta(50, None) is None


@pytest.mark.skipif(not os.getenv("DB_TESTS"), reason="set DB_TESTS=1 with Postgres + ingestion")
def test_buzz_endpoint_cold_start():
    with TestClient(app) as c:
        handle = "t" + uuid.uuid4().hex[:12]
        reg = c.post(
            "/auth/register", json={"handle": handle, "name": "Buzzer", "password": "password123"}
        )
        auth = {"Authorization": f"Bearer {reg.json()['access_token']}"}

        c.post("/posts", json={"body": "$GP buzzing", "sentiment": "bull"}, headers=auth)
        c.post("/watchlist", json={"code": "GP"}, headers=auth)

        b = c.get("/symbols/GP/buzz").json()
        assert b["watchers"] >= 1
        assert b["posts_24h"] >= 1
        # Without accrued snapshot history, trend fields stay null — never fabricated.
        assert b["posts_baseline"] is None
        assert b["chatter_x"] is None

        assert c.get("/symbols/NOTREAL/buzz").status_code == 404
