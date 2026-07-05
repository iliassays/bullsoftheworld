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


@pytest.mark.skipif(not os.getenv("DB_TESTS"), reason="set DB_TESTS=1 with Postgres + ingestion")
@pytest.mark.asyncio
async def test_portfolio_history_period_filtering() -> None:
    """/portfolio/history never reconstructs the past from current holdings — it only reads
    whatever the daily snapshot job (services/ingestion/portfolio_snapshot.py) already wrote,
    so an old point must disappear under a short period and reappear under 'all'.

    Uses httpx's ASGI transport (not TestClient) so the HTTP calls and the direct DB setup/
    teardown share this coroutine's own event loop natively — TestClient runs the app on its
    own internal loop via a background portal, which crashes cross-loop when mixed with a
    directly-awaited session from get_sessionmaker() in the same test.
    """
    from httpx import ASGITransport, AsyncClient
    from sqlalchemy import delete, select

    from api.main import app, lifespan
    from bulls.core.db import dispose_engine, get_sessionmaker
    from bulls.core.models import PortfolioSnapshot, User

    # ASGITransport (unlike TestClient) doesn't drive the app's lifespan automatically — without
    # it app.state.tenants is never populated. Running the lifespan directly also means everything
    # in this test (HTTP calls + the raw DB session below) shares this one coroutine's event loop,
    # which is what actually fixes the cross-loop crash TestClient's separate portal loop caused.
    # Dispose defensively first too, in case an earlier test in the same run left a stale engine
    # bound to its own now-closed loop (confirmed real: test_portfolio_snapshot.py did exactly
    # this before it got the same dispose-on-both-ends treatment).
    await dispose_engine()
    async with (
        lifespan(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c,
    ):
        handle = "t" + uuid.uuid4().hex[:12]
        reg = await c.post(
            "/auth/register",
            json={
                "name": "History Tester",
                "contact": f"{handle}@example.com",
                "password": "password123",
            },
        )
        assert reg.status_code == 201, reg.text
        hdr = {"Authorization": f"Bearer {reg.json()['access_token']}"}
        empty = await c.get("/portfolio/history", headers=hdr)
        assert empty.status_code == 200 and empty.json() == []

        sm = get_sessionmaker()
        async with sm() as session:
            # Handle is server-generated from the name, not the value we sent — look the
            # user up by the email we actually control instead.
            uid = (
                await session.scalars(select(User.id).where(User.email == f"{handle}@example.com"))
            ).one()
            session.add_all(
                [
                    PortfolioSnapshot(
                        user_id=uid,
                        market="DSE",
                        date=dt.date(2025, 1, 1),
                        total_value=20000.0,
                        total_cost=25000.0,
                    ),
                    PortfolioSnapshot(
                        user_id=uid,
                        market="DSE",
                        date=dt.date.today(),
                        total_value=25830.0,
                        total_cost=25000.0,
                    ),
                ]
            )
            await session.commit()
        try:
            recent = (await c.get("/portfolio/history?period=1w", headers=hdr)).json()
            assert len(recent) == 1 and recent[0]["total_value"] == 25830.0

            full = (await c.get("/portfolio/history?period=all", headers=hdr)).json()
            assert len(full) == 2
            assert full[0]["date"] == "2025-01-01"  # ascending, oldest first

            bad = await c.get("/portfolio/history?period=nonsense", headers=hdr)
            assert bad.status_code == 422
        finally:
            async with sm() as session:
                await session.execute(
                    delete(PortfolioSnapshot).where(PortfolioSnapshot.user_id == uid)
                )
                await session.commit()
