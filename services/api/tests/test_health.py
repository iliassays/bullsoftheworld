"""Smoke test: the app boots, tenant resolves, health is OK."""

from fastapi.testclient import TestClient

from api.main import app


def test_health_and_tenant():
    with TestClient(app) as client:
        assert client.get("/health").json() == {"status": "ok"}
        who = client.get("/whoami").json()
        assert who["tenant"] == "bullsofdhaka"
        assert who["market"] == "DSE"
