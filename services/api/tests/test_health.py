"""Smoke test: the app boots, tenant resolves, health is OK."""

from fastapi.testclient import TestClient

from api.main import app


def test_health_and_tenant():
    with TestClient(app) as client:
        assert client.get("/health").json() == {"status": "ok"}
        who = client.get("/whoami").json()
        assert who["tenant"] == "bullsofdhaka"
        assert who["market"] == "DSE"


def test_shared_api_can_resolve_wall_street_from_frontend_host():
    with TestClient(app) as client:
        who = client.get("/whoami", headers={"X-Tenant-Host": "bullsofwallst.com"}).json()
        assert who["tenant"] == "bullsofwallst"
        assert who["display_name"] == "Bulls of Wall Street"
        assert who["market"] == "US"

        via_origin = client.get(
            "/whoami", headers={"Origin": "https://www.bullsofwallst.com"}
        ).json()
        assert via_origin["tenant"] == "bullsofwallst"
