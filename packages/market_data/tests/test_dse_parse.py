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
    parse_company,
    parse_market_summary,
    parse_quotes,
    parse_sector_pe,
    parse_symbols,
)

FIXTURES = Path(__file__).parent / "fixtures"
LATEST = (FIXTURES / "latest_sample.html").read_text()
ARCHIVE = (FIXTURES / "archive_sample.html").read_text()
SUMMARY = (FIXTURES / "summary_sample.html").read_text()
COMPANY = (FIXTURES / "company_sample.html").read_text()
SECTOR_PE = (FIXTURES / "sector_pe_sample.html").read_text()


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
    # the suspended SALVOCHEM row ('--' everywhere) is skipped — only the 2 GP bars remain
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


def test_parse_bars_skips_suspended_rows():
    """A halted/suspended day comes back as '--' across the board; CLOSEP parses to None.
    Such rows must be dropped, not persisted as all-zero bars (regression: SALVOCHEM)."""
    bars = parse_bars(ARCHIVE)
    assert all(b.code != "SALVOCHEM" for b in bars)
    assert all(b.close > 0 for b in bars)


def test_parse_market_summary():
    summaries = {s.date: s for s in parse_market_summary(SUMMARY)}
    # the marquee/ticker table (no 'Market Summary of' title) is ignored; 2 day-blocks parsed
    assert set(summaries) == {dt.date(2026, 6, 24), dt.date(2026, 6, 23)}

    s = summaries[dt.date(2026, 6, 24)]
    assert s.market == "DSE"
    assert s.dsex == 5616.83456 and s.dsex_change == 11.57963
    assert s.ds30 == 2127.48289 and s.ds30_change == 0.10162
    # commas stripped; counts coerced to int, money kept as float
    assert s.total_trade == 223987 and isinstance(s.total_trade, int)
    assert s.total_volume == 266704867 and isinstance(s.total_volume, int)
    assert s.total_value_mn == 9402.133
    assert s.total_market_cap_mn == 6908678.625


def test_parse_company_profile():
    info = parse_company(COMPANY, "PRAGATIINS")
    assert info is not None
    p = info.profile
    assert p.market == "DSE" and p.code == "PRAGATIINS"
    # values-then-labels block parses the same as labels-then-values (order-independent rule)
    assert p.sector == "Insurance"
    assert p.outstanding_shares == 81214559 and isinstance(p.outstanding_shares, int)
    assert p.authorized_capital_mn == 2000.0 and p.paid_up_capital_mn == 812.15
    assert p.face_value == 10.0 and p.market_lot == 1
    assert p.market_cap_mn == 6147.942 and p.free_float_mcap_mn == 3579.915
    assert p.listing_year == 1996 and p.market_category == "A"
    assert p.instrument_type == "Equity" and p.year_end == "31-Dec"
    assert p.latest_dividend == "27.00, 3%B for 2025"
    assert p.cash_dividend_pct == 27.0  # leading cash % parsed off the dividend string
    assert p.operational_status == "Active"
    # latest-year (2025) fundamentals from the 13-col NAV table, not the prior year
    assert p.eps == 5.31 and p.nav_per_share == 57.36
    # debt + reserves, parsed through the same reversed label/value grid
    assert p.short_term_loan_mn == 120.5 and p.long_term_loan_mn == 450.0
    assert p.reserve_surplus_mn == 3702.8 and p.oci_mn == 8.3
    # credit rating captured when the page populates it (often blank in practice)
    assert p.credit_rating_short == "ST-2" and p.credit_rating_long == "AA"


def test_parse_company_financials_and_dividends():
    info = parse_company(COMPANY, "PRAGATIINS")
    assert info is not None
    # multi-year EPS/NAV series (both years from the fundamentals table)
    fin = {f.fiscal_year: f for f in info.financials}
    assert set(fin) == {2024, 2025}
    assert (
        fin[2025].eps == 5.31 and fin[2025].nav_per_share == 57.36 and fin[2025].profit_mn == 418.85
    )
    # dividend history merges cash + bonus per year
    div = {d.year: d for d in info.dividends}
    assert div[2025].cash_pct == 27.0 and div[2025].bonus_pct == 3.0
    assert div[2024].cash_pct == 20.0 and div[2024].bonus_pct == 7.0
    assert div[2022].cash_pct == 25.0 and div[2022].bonus_pct is None  # cash-only year


def test_parse_sector_pe():
    sectors = {s.sector: s.median_pe for s in parse_sector_pe(SECTOR_PE)}
    assert sectors["Bank"] == 4.885
    assert sectors["Insurance"] == 14.30
    assert "Pharmaceuticals & Chemicals" in sectors  # ampersand survives
    assert len(sectors) == 4  # the marquee table is ignored


def test_parse_company_shareholdings():
    info = parse_company(COMPANY, "PRAGATIINS")
    assert info is not None
    by_date = {s.as_of_date: s for s in info.shareholdings}
    assert set(by_date) == {dt.date(2025, 12, 31), dt.date(2026, 5, 31)}
    latest = by_date[dt.date(2026, 5, 31)]
    assert latest.sponsor_director == 39.98
    assert latest.institute == 21.24 and latest.public == 38.78
    # breakdown sums to ~100%
    total = (
        latest.sponsor_director
        + latest.govt
        + latest.institute
        + latest.foreign_pct
        + latest.public
    )
    assert abs(total - 100.0) < 0.05


def test_parse_company_unknown_code_returns_none():
    assert parse_company("<html><body>no data</body></html>", "NOPE") is None


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
