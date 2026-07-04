"""Portfolio valuation unit tests (pure math) + DB-gated endpoint flow.

DB_TESTS=1 uv run pytest -k portfolio
"""

from __future__ import annotations

import datetime as dt
import os
import uuid

import pytest
from fastapi.testclient import TestClient

from api.routers.portfolio import AlertView, QuoteView, compute_portfolio
from bulls.core.models import PortfolioHolding


def _h(code: str, qty: int, cost: float) -> PortfolioHolding:
    return PortfolioHolding(user_id=1, market="DSE", code=code, quantity=qty, avg_cost=cost)


def test_compute_portfolio_math() -> None:
    holdings = [_h("GP", 500, 271.0), _h("OLYMPIC", 1200, 168.5)]
    quotes = {
        "GP": QuoteView(ltp=286.4, change=5.0, change_pct=1.78, as_of=None),
        "OLYMPIC": QuoteView(ltp=182.4, change=3.8, change_pct=2.13, as_of=None),
    }
    pf = compute_portfolio(holdings, quotes)
    gp = pf.holdings[0]
    assert gp.value == 500 * 286.4
    assert gp.pnl == pytest.approx(500 * (286.4 - 271.0))
    assert gp.pnl_pct == pytest.approx((286.4 - 271.0) / 271.0 * 100, abs=0.01)
    assert pf.total_value == pytest.approx(500 * 286.4 + 1200 * 182.4)
    assert pf.day_pnl == pytest.approx(500 * 5.0 + 1200 * 3.8)
    # day % is against yesterday's value, not cost
    prev = pf.total_value - pf.day_pnl
    assert pf.day_pnl_pct == pytest.approx(pf.day_pnl / prev * 100, abs=0.01)


def test_compute_portfolio_missing_quote_is_honest() -> None:
    """A holding we can't price shows as unpriced — never silently valued at cost (principle #4)."""
    holdings = [_h("GP", 100, 250.0), _h("DELISTED", 50, 10.0)]
    quotes = {"GP": QuoteView(ltp=260.0, change=1.0, change_pct=0.4, as_of=None)}
    pf = compute_portfolio(holdings, quotes)
    unpriced = next(h for h in pf.holdings if h.code == "DELISTED")
    assert unpriced.value is None and unpriced.pnl is None
    # totals reflect only priced rows; total_pnl compares against priced cost basis only
    assert pf.total_value == pytest.approx(100 * 260.0)
    assert pf.total_pnl == pytest.approx(100 * (260.0 - 250.0))
    assert pf.total_cost == pytest.approx(100 * 250.0 + 50 * 10.0)


def test_compute_portfolio_alert_enrichment() -> None:
    """A holding gets 'what's happening' context: its latest inbox alert (already fanned out to
    holders) and whether the user has a price alert set — never just P&L (principle: portfolio
    should add value beyond a bare valuation)."""
    holdings = [_h("GP", 100, 250.0), _h("OLYMPIC", 10, 100.0)]
    quotes = {
        "GP": QuoteView(ltp=260.0, change=1.0, change_pct=0.4, as_of=None),
        "OLYMPIC": QuoteView(ltp=105.0, change=0.5, change_pct=0.5, as_of=None),
    }
    when = dt.datetime(2026, 7, 1, tzinfo=dt.UTC)
    pf = compute_portfolio(
        holdings,
        quotes,
        latest_alerts={
            "GP": AlertView(title="GP sponsor holding falling for months", created_at=when)
        },
        alert_codes={"GP"},
    )
    gp = next(h for h in pf.holdings if h.code == "GP")
    olympic = next(h for h in pf.holdings if h.code == "OLYMPIC")
    assert gp.latest_alert_title == "GP sponsor holding falling for months"
    assert gp.latest_alert_at == when
    assert gp.has_price_alert is True
    # a holding with no recent alert / no price alert stays honestly empty, not a fake default
    assert olympic.latest_alert_title is None and olympic.has_price_alert is False


def test_compute_portfolio_empty() -> None:
    pf = compute_portfolio([], {})
    assert pf.total_value is None and pf.day_pnl is None and pf.holdings == []


@pytest.mark.skipif(not os.getenv("DB_TESTS"), reason="set DB_TESTS=1 with Postgres + ingestion")
def test_portfolio_endpoint_flow() -> None:
    from api.main import app

    with TestClient(app) as c:
        handle = "t" + uuid.uuid4().hex[:12]
        reg = c.post(
            "/auth/register",
            json={
                "name": "PF Tester",
                "contact": f"{handle}@example.com",
                "password": "password123",
            },
        )
        assert reg.status_code == 201, reg.text
        hdr = {"Authorization": f"Bearer {reg.json()['access_token']}"}

        assert c.get("/portfolio", headers=hdr).json()["holdings"] == []

        r = c.post(
            "/portfolio/holdings",
            json={"code": "gp", "quantity": 100, "avg_cost": 250.0},
            headers=hdr,
        )
        assert r.status_code == 201, r.text
        assert r.json()["status"] == "created"

        # upsert by code updates in place
        r = c.post(
            "/portfolio/holdings",
            json={"code": "GP", "quantity": 150, "avg_cost": 240.0},
            headers=hdr,
        )
        assert r.json()["status"] == "updated"

        pf = c.get("/portfolio", headers=hdr).json()
        assert len(pf["holdings"]) == 1
        assert pf["holdings"][0]["quantity"] == 150
        # no alert yet — fields present and honestly empty, not defaulted to something misleading
        assert pf["holdings"][0]["has_price_alert"] is False
        assert pf["holdings"][0]["latest_alert_title"] is None

        r = c.post(
            "/alerts/price",
            json={"code": "GP", "level": 300.0, "direction": "above"},
            headers=hdr,
        )
        assert r.status_code == 201, r.text
        pf = c.get("/portfolio", headers=hdr).json()
        assert pf["holdings"][0]["has_price_alert"] is True

        assert (
            c.post(
                "/portfolio/holdings",
                json={"code": "NOTREAL", "quantity": 1, "avg_cost": 1},
                headers=hdr,
            ).status_code
            == 404
        )

        assert c.delete("/portfolio/holdings/GP", headers=hdr).status_code == 204
        assert c.get("/portfolio", headers=hdr).json()["holdings"] == []

        # anonymous is rejected
        assert c.get("/portfolio").status_code in (401, 403)
