"""Smoke test: the app boots, tenant resolves, health is OK."""

from fastapi.testclient import TestClient

from api.main import app


def test_health_and_tenant():
    with TestClient(app) as client:
        assert client.get("/health").json() == {"status": "ok"}
        assert client.get("/live").json() == {"status": "ok"}
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


def test_contradictory_tenant_signals_fail_closed():
    cases = (
        ("https://api.bullsofwallst.com", "research.bullsofdhaka.com"),
        ("https://api.bullsofdhaka.com", "research.bullsofwallst.com"),
    )
    with TestClient(app) as client:
        responses = [
            client.get(
                f"{api_host}/whoami",
                headers={"X-Tenant-Host": tenant_host},
            )
            for api_host, tenant_host in cases
        ]

    for response in responses:
        assert response.status_code == 421
        assert response.json()["detail"] == "Request tenant does not match the API host"


def test_tenant_sensitive_api_responses_are_not_http_cached():
    with TestClient(app) as client:
        res = client.get("/whoami", headers={"X-Tenant-Host": "bullsofwallst.com"})
        assert res.headers["cache-control"] == "no-store"
        vary = {part.strip().lower() for part in res.headers["vary"].split(",")}
        assert {"origin", "x-tenant-host", "referer"}.issubset(vary)


def test_request_id_is_propagated_or_generated():
    with TestClient(app) as client:
        supplied = client.get("/health", headers={"X-Request-ID": "trace-123"})
        assert supplied.headers["x-request-id"] == "trace-123"
        generated = client.get("/health")
        assert len(generated.headers["x-request-id"]) == 32
