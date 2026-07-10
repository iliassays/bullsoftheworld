"""Market endpoint integration tests.

Opt-in: needs Postgres up AND ingestion to have run at least once.
    DB_TESTS=1 uv run pytest -k market
"""

from __future__ import annotations

import datetime as dt
import os
import uuid

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


def test_symbol_search_filters_and_ranks_prefix_matches():
    with TestClient(app) as client:
        r = client.get("/symbols", params={"q": "gp", "limit": 5})
        assert r.status_code == 200
        codes = [row["code"] for row in r.json()]
        assert codes and codes[0] == "GP"


@pytest.mark.asyncio
async def test_eod_market_quotes_are_adjusted_and_include_session_change() -> None:
    from sqlalchemy import delete

    from api.routers.market import get_quotes
    from bulls.core.db import dispose_engine, get_sessionmaker
    from bulls.core.models import DailyBar, Symbol
    from bulls.core.tenancy import Tenant

    await dispose_engine()
    sm = get_sessionmaker()
    code = "Z" + uuid.uuid4().hex[:8].upper()
    tenant = Tenant(
        name="wallst-test",
        display_name="Wall St Test",
        market="US",
        locale="en",
        timezone="America/New_York",
        site_url="https://example.com",
        support_email="support@example.com",
        email_from="Wall St Test <no-reply@example.com>",
        logo_url="https://example.com/logo.png",
        tagline_en="Facts first",
        tagline_bn="তথ্য আগে",
    )

    try:
        async with sm() as session:
            session.add(
                Symbol(
                    market="US",
                    code=code,
                    name_en="Adjusted Test",
                    is_active=True,
                    is_hidden=False,
                    data_status="ready",
                )
            )
            session.add_all(
                [
                    DailyBar(
                        market="US",
                        code=code,
                        date=dt.date(2026, 7, 8),
                        open=98,
                        high=102,
                        low=97,
                        close=100,
                        adjusted_close=50,
                        volume=1_000,
                        source="test",
                    ),
                    DailyBar(
                        market="US",
                        code=code,
                        date=dt.date(2026, 7, 9),
                        open=108,
                        high=112,
                        low=107,
                        close=110,
                        adjusted_close=55,
                        volume=2_000,
                        source="test",
                    ),
                ]
            )
            await session.commit()

            quotes = await get_quotes(tenant, session, codes=code)
            assert len(quotes) == 1
            assert quotes[0].code == code
            assert quotes[0].ltp == pytest.approx(55)
            assert quotes[0].prev_close == pytest.approx(50)
            assert quotes[0].change_pct == pytest.approx(10)
            assert quotes[0].volume == 2_000
            assert quotes[0].as_of.tzinfo is not None
    finally:
        async with sm() as session:
            await session.execute(delete(DailyBar).where(DailyBar.market == "US", DailyBar.code == code))
            await session.execute(delete(Symbol).where(Symbol.market == "US", Symbol.code == code))
            await session.commit()
        await dispose_engine()
