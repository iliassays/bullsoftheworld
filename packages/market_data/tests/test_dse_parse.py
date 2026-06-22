"""Parser tests against saved fixtures (no network).

The live test at the bottom is opt-in: `DSE_LIVE=1 uv run pytest -k live`.
"""

from __future__ import annotations

import datetime as dt
import os
from pathlib import Path

import pytest

from bulls.market_data.providers.dse_scrape import (
    DseScrapeProvider,
    parse_bars,
    parse_quotes,
    parse_symbols,
)

FIXTURES = Path(__file__).parent / "fixtures"
LATEST = (FIXTURES / "latest_sample.html").read_text()
ARCHIVE = (FIXTURES / "archive_sample.html").read_text()


def test_parse_quotes_maps_columns_by_header():
    quotes = {q.code: q for q in parse_quotes(LATEST, as_of=dt.datetime.now(dt.UTC))}
    # suspended row (LTP '--') is skipped
    assert set(quotes) == {"1JANATAMF", "GP"}

    gp = quotes["GP"]
    assert gp.ltp == 294.2
    assert gp.high == 299.2 and gp.low == 291.5
    assert gp.prev_close == 291.4
    assert gp.open is None  # not published on the latest page
    assert gp.volume == 66928 and gp.trades == 925
    assert gp.is_delayed is True
    # change_pct computed from change/ycp
    assert gp.change == 2.8
    assert gp.change_pct == round(2.8 / 291.4 * 100, 2)


def test_parse_symbols():
    codes = {s.code for s in parse_symbols(LATEST)}
    assert {"GP", "1JANATAMF"} <= codes
    assert all(s.market == "DSE" for s in parse_symbols(LATEST))


def test_parse_bars_full_ohlc():
    bars = parse_bars(ARCHIVE)
    assert len(bars) == 2
    b = bars[0]
    assert b.code == "GP"
    assert b.date == dt.date(2025, 6, 19)
    assert b.open == 296.6 and b.high == 299.2 and b.low == 291.5 and b.close == 294.2
    assert b.volume == 66928
    # OHLC sanity: low <= open/close <= high
    for bar in bars:
        assert bar.low <= bar.open <= bar.high
        assert bar.low <= bar.close <= bar.high


def test_layout_change_raises():
    with pytest.raises(ValueError, match="layout changed"):
        parse_quotes("<html><body>no table here</body></html>", as_of=dt.datetime.now(dt.UTC))


@pytest.mark.skipif(not os.getenv("DSE_LIVE"), reason="set DSE_LIVE=1 to hit dsebd.org")
@pytest.mark.asyncio
async def test_live_quotes_smoke():
    provider = DseScrapeProvider()
    quotes = await provider.get_quotes(["GP", "BEXIMCO"])
    assert quotes, "no quotes returned from live DSE"
    for q in quotes:
        assert q.ltp > 0 and q.is_delayed
