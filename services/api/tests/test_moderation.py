"""Write-path moderation integration (docs/specs/feed-moderation.md).

Opt-in, needs Postgres up + migrations applied:
    DB_TESTS=1 uv run pytest -k moderation

Verifies the synchronous gate end-to-end: clean posts publish, guarantees/pumps are blocked at write
(422 + reason, but persisted for audit), advice-with-cashtag is held as `pending` (author-only, not in
the public feed), and profanity publishes masked.
"""

from __future__ import annotations

import os
import uuid

import pytest
from fastapi.testclient import TestClient

from api.main import app
from bulls.core.config import get_settings


@pytest.fixture(autouse=True)
def _enforce(monkeypatch):
    """These tests assert enforcement behavior, so flip the shadow flag on for the module."""
    monkeypatch.setenv("MODERATION_ENFORCE", "true")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _register(c: TestClient) -> dict[str, str]:
    contact = f"m{uuid.uuid4().hex[:12]}@example.com"
    reg = c.post(
        "/auth/register",
        json={"name": "Mod Test", "contact": contact, "password": "password123"},
    )
    assert reg.status_code == 201, reg.text
    return {"Authorization": f"Bearer {reg.json()['access_token']}"}


@pytest.mark.skipif(not os.getenv("DB_TESTS"), reason="set DB_TESTS=1 with Postgres")
def test_write_path_moderation_outcomes():
    with TestClient(app) as c:
        auth = _register(c)

        # clean -> published, visible in the feed
        clean = c.post("/posts", json={"body": "DSEX looked calm into the close today"}, headers=auth)
        assert clean.status_code == 201, clean.text
        assert clean.json()["moderation_status"] == "published"
        assert any(x["id"] == clean.json()["id"] for x in c.get("/posts").json())

        # guaranteed return -> blocked at write (422 + reason)
        blocked = c.post("/posts", json={"body": "guaranteed 100% profit, no loss!"}, headers=auth)
        assert blocked.status_code == 422, blocked.text
        assert blocked.json()["detail"]["reason"] == "guarantee"

        # advice on a cashtag -> pending (author-only, NOT in the public feed)
        held = c.post("/posts", json={"body": "buy $GP now before it flies"}, headers=auth)
        assert held.status_code == 201, held.text
        held_id = held.json()["id"]
        assert held.json()["moderation_status"] == "pending"
        assert all(x["id"] != held_id for x in c.get("/posts").json())

        # profanity -> published but masked
        masked = c.post("/posts", json={"body": "this analysis is crap"}, headers=auth)
        assert masked.status_code == 201, masked.text
        assert masked.json()["moderation_status"] == "published"
        assert "****" in masked.json()["body"] and "crap" not in masked.json()["body"]


@pytest.mark.skipif(not os.getenv("DB_TESTS"), reason="set DB_TESTS=1 with Postgres")
def test_shadow_mode_logs_but_publishes(monkeypatch):
    # In shadow (enforce off) even a clear guarantee publishes, but the reason is still recorded.
    monkeypatch.setenv("MODERATION_ENFORCE", "false")
    get_settings.cache_clear()
    with TestClient(app) as c:
        auth = _register(c)
        r = c.post("/posts", json={"body": "guaranteed 100% profit, no loss!"}, headers=auth)
        assert r.status_code == 201, r.text
        assert r.json()["moderation_status"] == "published"
        assert r.json()["moderation_reason"] == "guarantee"  # logged for observability/tuning


@pytest.mark.skipif(
    not (os.getenv("DB_TESTS") and os.getenv("ADMIN_TOKEN")),
    reason="set DB_TESTS=1 and ADMIN_TOKEN with Postgres",
)
def test_review_queue_approve_publishes():
    admin = {"X-Admin-Token": os.environ["ADMIN_TOKEN"]}
    with TestClient(app) as c:
        auth = _register(c)
        held = c.post("/posts", json={"body": "sell $GP right now"}, headers=auth)
        held_id = held.json()["id"]
        assert held.json()["moderation_status"] == "pending"

        q = c.get("/moderation/queue", headers=admin)
        assert q.status_code == 200, q.text
        assert any(i["post_id"] == held_id for i in q.json()["items"])

        ok = c.post(f"/moderation/{held_id}/approve", headers=admin)
        assert ok.status_code == 200 and ok.json()["status"] == "published"
        assert any(x["id"] == held_id for x in c.get("/posts").json())
