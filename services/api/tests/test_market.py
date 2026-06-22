"""Market endpoint integration tests.

Opt-in: needs Postgres up AND ingestion to have run at least once.
    DB_TESTS=1 uv run pytest -k market
"""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from api.main import app

pytestmark = pytest.mark.skipif(
    not os.getenv("DB_TESTS"), reason="set DB_TESTS=1 with Postgres up + ingestion run"
)


def test_quotes_filtered_by_code():
    with TestClient(app) as client:
        r = client.get("/quotes", params={"codes": "GP"})
        assert r.status_code == 200
        quotes = r.json()
        assert isinstance(quotes, list)
        gp = next((q for q in quotes if q["code"] == "GP"), None)
        assert gp is not None, "GP not found — run ingestion first"
        assert gp["market"] == "DSE"
        assert gp["is_delayed"] is True
        assert gp["ltp"] > 0


def test_symbol_detail():
    with TestClient(app) as client:
        r = client.get("/symbols/gp")  # case-insensitive
        assert r.status_code == 200
        body = r.json()
        assert body["symbol"]["code"] == "GP"

        missing = client.get("/symbols/NOTAREALCODE")
        assert missing.status_code == 404
