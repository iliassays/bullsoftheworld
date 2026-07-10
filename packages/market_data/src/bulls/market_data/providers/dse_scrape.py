"""DSE adapter — delayed/EOD data scraped from the public dsebd.org pages.

Sources (public, already-published):
  - Latest prices: https://www.dsebd.org/latest_share_price_scroll_l.php  (delayed snapshot)
  - Day-end archive: https://www.dsebd.org/day_end_archive.php?startDate=..&endDate=..&inst=..&archive=data

This provider is DELAYED, so every Quote sets is_delayed=True. It has no subscribe(); the ingestion
service polls it on a schedule. Parsing is keyed by HEADER NAME (not column index) so it survives
column reordering — when dsebd.org changes layout, /scrape-check catches it.

Note: dsebd.org serves an incomplete TLS chain (no intermediates), so verified requests fail with
CERTIFICATE_VERIFY_FAILED. We read public data over a GET; `verify_ssl=False` is a deliberate,
documented trade-off for this source until a licensed feed replaces it.
"""

from __future__ import annotations

import datetime as dt
import re

import httpx
from selectolax.parser import HTMLParser

from bulls.market_data.provider import (
    AnnualFinancial,
    Bar,
    CompanyInfo,
    CompanyProfile,
    DividendRecord,
    MarketSummary,
    NewsItem,
    Quote,
    SectorPE,
    Shareholding,
    Symbol,
)

_BASE = "https://www.dsebd.org"
_LATEST_URL = f"{_BASE}/latest_share_price_scroll_l.php"
_ARCHIVE_URL = f"{_BASE}/day_end_archive.php"
_SUMMARY_URL = f"{_BASE}/market_summary.php"
_COMPANY_URL = f"{_BASE}/displayCompany.php"
_SECTOR_PE_URL = f"{_BASE}/sectoral_PE.php"
# News on news_archive.php is rendered client-side by a jQuery DataTable that AJAX-loads
# ajax/load-news.php (same dsebd.org host). That AJAX endpoint is the only one that returns rows,
# and only when the X-Requested-With: XMLHttpRequest header is present (see get_news).
_NEWS_URL = f"{_BASE}/ajax/load-news.php"
# old_news.php is the historical archive — server-rendered, honours startDate/endDate (see
# get_news_archive). load-news.php can't backfill because it ignores the range.
_ARCHIVE_NEWS_URL = f"{_BASE}/old_news.php"
_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"


def _norm(header: str) -> str:
    """Normalize a header cell: 'LTP*' -> 'LTP', 'TRADING CODE' -> 'TRADING CODE'."""
    return header.strip().rstrip("*").strip().upper()


def _num(value: str | None) -> float | None:
    """Parse '1,183,581' / '3.1' / '--' / '' into a float, or None if not numeric."""
    if not value:
        return None
    cleaned = value.replace(",", "").strip()
    if cleaned in ("", "-", "--", "N/A"):
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _data_table(html: str) -> tuple[dict[str, int], list[list[str]]]:
    """Return (header->index map, data rows) for the dsebd 'shares-table'."""
    tree = HTMLParser(html)
    table = tree.css_first("table.shares-table")
    if table is None:
        raise ValueError("DSE page layout changed: no table.shares-table found")
    rows = table.css("tr")
    header_cells = [c.text(strip=True) for c in rows[0].css("th, td")]
    headers = {_norm(h): i for i, h in enumerate(header_cells)}
    data = [[c.text(strip=True) for c in r.css("td")] for r in rows[1:] if r.css("td")]
    return headers, data


def _col(row: list[str], headers: dict[str, int], name: str) -> str | None:
    i = headers.get(name)
    return row[i] if i is not None and i < len(row) else None


def parse_quotes(html: str, *, as_of: dt.datetime) -> list[Quote]:
    """Parse the latest-price page into Quotes (all instruments)."""
    headers, rows = _data_table(html)
    quotes: list[Quote] = []
    for row in rows:
        code = _col(row, headers, "TRADING CODE")
        ltp = _num(_col(row, headers, "LTP"))
        if not code or ltp is None:
            continue
        ycp = _num(_col(row, headers, "YCP"))
        change = _num(_col(row, headers, "CHANGE")) or 0.0
        change_pct = (change / ycp * 100) if ycp else 0.0
        quotes.append(
            Quote(
                market="DSE",
                code=code,
                ltp=ltp,
                change=change,
                change_pct=round(change_pct, 2),
                open=_num(_col(row, headers, "OPENP")),  # absent on latest page -> None
                high=_num(_col(row, headers, "HIGH")) or ltp,
                low=_num(_col(row, headers, "LOW")) or ltp,
                close=_num(_col(row, headers, "CLOSEP")) or ltp,
                prev_close=ycp,
                volume=int(_num(_col(row, headers, "VOLUME")) or 0),
                trades=int(_num(_col(row, headers, "TRADE")) or 0),
                as_of=as_of,
                is_delayed=True,
            )
        )
    return quotes


def parse_symbols(html: str) -> list[Symbol]:
    """Derive the instrument universe (codes) from the latest-price page.

    Names/sector aren't on this page; enrich from company pages later (name_en defaults to code).
    """
    headers, rows = _data_table(html)
    symbols: list[Symbol] = []
    for row in rows:
        code = _col(row, headers, "TRADING CODE")
        if code:
            symbols.append(Symbol(market="DSE", code=code, name_en=code))
    return symbols


def parse_bars(html: str) -> list[Bar]:
    """Parse the day-end archive result into daily OHLCV bars."""
    headers, rows = _data_table(html)
    bars: list[Bar] = []
    for row in rows:
        code = _col(row, headers, "TRADING CODE")
        date_str = _col(row, headers, "DATE")
        if not code or not date_str:
            continue
        close = _num(_col(row, headers, "CLOSEP"))
        # '--' parses to None (caught above). A suspended/halted stock can also render a literal
        # "0.00" cell, which _num happily parses as 0.0 — that used to sail through as a fake
        # "crashed to ৳0" bar (confirmed live: SALVOCHEM got 7 such bars after its Dec 2025
        # suspension). No real DSE trading day ever closes at zero, so treat it the same as None.
        if close is None or close <= 0:
            continue
        high = _num(_col(row, headers, "HIGH")) or close
        low = _num(_col(row, headers, "LOW")) or close
        open_ = _num(_col(row, headers, "OPENP")) or close
        if high < low or open_ <= 0 or high <= 0 or low <= 0:
            continue  # incoherent OHLC — a parse/layout error, not a real trading day
        bars.append(
            Bar(
                market="DSE",
                code=code,
                date=dt.date.fromisoformat(date_str),
                open=open_,
                high=high,
                low=low,
                close=close,
                volume=int(_num(_col(row, headers, "VOLUME")) or 0),
                source="dse_archive",
            )
        )
    return bars


_SUMMARY_TITLE = "Market Summary of"
_SUMMARY_FIELDS = {  # normalized label -> (MarketSummary attr, is_int)
    "DSEX INDEX": ("dsex", False),
    "DSEX INDEX CHANGE": ("dsex_change", False),
    "DS30 INDEX": ("ds30", False),
    "DS30 INDEX CHANGE": ("ds30_change", False),
    "TOTAL TRADE": ("total_trade", True),
    "TOTAL VALUE TAKA(MN)": ("total_value_mn", False),
    "TOTAL VOLUME": ("total_volume", True),
    "TOTAL MARKET CAP. TAKA(MN)": ("total_market_cap_mn", False),
}


def parse_market_summary(html: str) -> list[MarketSummary]:
    """Parse the market_summary.php archive into one MarketSummary per trading day.

    Each day is a small label/value block titled 'Market Summary of <Mon DD, YYYY>'. We key by
    label name (not position) so the parser survives reordering — same robustness as the bar parser.
    """
    tree = HTMLParser(html)
    summaries: list[MarketSummary] = []
    for table in tree.css("table"):
        rows = table.css("tr")
        if not rows:
            continue
        title = rows[0].text(strip=True)
        if not title.startswith(_SUMMARY_TITLE):
            continue
        try:
            date = dt.datetime.strptime(title[len(_SUMMARY_TITLE) :].strip(), "%b %d, %Y").date()
        except ValueError:
            continue
        # Remaining rows are [label, value, label, value]; fold every (label, value) pair into a map.
        values: dict[str, str] = {}
        for row in rows[1:]:
            cells = [c.text(strip=True) for c in row.css("th, td")]
            for i in range(0, len(cells) - 1, 2):
                values[_norm(cells[i])] = cells[i + 1]
        fields: dict[str, float | int | None] = {}
        for label, (attr, is_int) in _SUMMARY_FIELDS.items():
            num = _num(values.get(label))
            fields[attr] = int(num) if (is_int and num is not None) else num
        summaries.append(MarketSummary(market="DSE", date=date, **fields))
    return summaries


def _news_date(value: str) -> dt.date | None:
    value = value.strip()
    for fmt in ("%Y-%m-%d", "%b %d, %Y", "%d %b %Y", "%d-%m-%Y"):
        try:
            return dt.datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


# load-news.php renders each item as a vertical block of label/value rows — the value sits in the
# first cell, the label ("Trading Code:", "News Title:", "Post Date:") in the second. A "Trading
# Code:" row starts a new item. We key off the label so column/whitespace drift doesn't break it.
_NEWS_FIELD_BY_LABEL = {
    "trading code:": "code",
    "news title:": "title",
    "news:": "body",
    "post date:": "date",
}
_NEWS_TABLE_HEADER = {
    "trading code": "code",
    "code": "code",
    "news title": "title",
    "title": "title",
    "headline": "title",
    "news": "body",
    "news date": "date",
    "post date": "date",
    "date": "date",
}


def _emit_news(item: dict[str, str], out: list[NewsItem]) -> None:
    code = item.get("code", "").upper().strip()
    headline = item.get("title", "").strip()
    date = _news_date(item.get("date", ""))
    if code and headline and date:
        out.append(
            NewsItem(
                code=code, published_at=date, headline=headline, body=item.get("body", "").strip()
            )
        )


def _parse_news_table(tree: HTMLParser, out: list[NewsItem]) -> None:
    """Fallback for archive-style tables with column headers."""
    for table in tree.css("table"):
        rows = table.css("tr")
        header: dict[str, int] = {}
        body_start = 0
        for idx, row in enumerate(rows):
            cells = [c.text(strip=True) for c in row.css("td, th")]
            mapped = {
                field: i
                for i, cell in enumerate(cells)
                if (field := _NEWS_TABLE_HEADER.get(cell.strip().lower().rstrip(":")))
            }
            if {"date", "code", "title"}.issubset(mapped):
                header = mapped
                body_start = idx + 1
                break
        if not header:
            continue
        for row in rows[body_start:]:
            cells = [c.text(strip=True) for c in row.css("td")]
            if len(cells) <= max(header.values()):
                continue
            item = {field: cells[col] for field, col in header.items()}
            _emit_news(item, out)


def parse_news(html: str) -> list[NewsItem]:
    """Parse load-news.php into raw NewsItems (date, code, headline).

    The AJAX response is not a column table: each announcement is a run of rows shaped
    ``[value, label]`` — e.g. ``["ICBIBANK", "Trading Code:"]`` then ``["…", "News Title:"]`` then
    ``["…", "Post Date:"]``. We accumulate by label and flush when the next "Trading Code:" begins.
    """
    tree = HTMLParser(html)
    out: list[NewsItem] = []
    current: dict[str, str] = {}
    for row in tree.css("tr"):
        cells = [c.text(strip=True) for c in row.css("td, th")]
        if len(cells) < 2:
            continue
        # The label ("Trading Code:", ...) is in cell 1 on load-news.php (value|label) but in cell 0
        # on the old_news.php archive (<th>label</th><td>value</td>). Match either; the value is the
        # other cell, so one parser reads both the live feed and the historical archive.
        if (field := _NEWS_FIELD_BY_LABEL.get(cells[0].strip().lower())) is not None:
            value = cells[1]
        elif (field := _NEWS_FIELD_BY_LABEL.get(cells[1].strip().lower())) is not None:
            value = cells[0]
        else:
            continue
        if field == "code":  # a new item begins — flush the previous one
            _emit_news(current, out)
            current = {}
        current[field] = value
    _emit_news(current, out)  # last item has no trailing "Trading Code:" to flush it
    if not out:
        _parse_news_table(tree, out)
    return out


def _int(value: str | None) -> int | None:
    n = _num(value)
    return int(n) if n is not None else None


# displayCompany.php is a 2-column label/value grid, but column order is inconsistent across
# blocks (some rows are label|value, others value|label). The value always sits half a row away,
# so we read it as cells[(label_index + n//2) % n] — order-independent.
_COMPANY_LABELS = {  # page label -> (CompanyProfile attr, coercion)
    "Sector": ("sector", str),
    "Market Category": ("market_category", str),
    "Type of Instrument": ("instrument_type", str),
    "Listing Year": ("listing_year", _int),
    "Face/par Value": ("face_value", _num),
    "Market Lot": ("market_lot", _int),
    "Authorized Capital (mn)": ("authorized_capital_mn", _num),
    "Paid-up Capital (mn)": ("paid_up_capital_mn", _num),
    "Total No. of Outstanding Securities": ("outstanding_shares", _int),
    "Market Capitalization (mn)": ("market_cap_mn", _num),
    "Free Float Market Cap. (mn)": ("free_float_mcap_mn", _num),
    "Year End": ("year_end", str),
    "Latest Dividend Status (%)": ("latest_dividend", str),
    "Short-term loan (mn)": ("short_term_loan_mn", _num),
    "Long-term loan (mn)": ("long_term_loan_mn", _num),
    "Reserve & Surplus without OCI (mn)": ("reserve_surplus_mn", _num),
    "Other Comprehensive Income (OCI) (mn)": ("oci_mn", _num),
    "Present Operational Status": ("operational_status", str),
}
_SHAREHOLDING_RE = re.compile(
    r"Sponsor/Director:([\d.]+)Govt:([\d.]+)Institute:([\d.]+)Foreign:([\d.]+)Public:([\d.]+)"
)
_AS_ON_RE = re.compile(r"as on\s+([A-Za-z]{3}\s+\d{1,2},\s+\d{4})")
_CASH_DIV_RE = re.compile(r"^\s*([\d.]+)")  # leading cash % of 'Latest Dividend Status (%)'
# The annual fundamentals table is a stable 13-column grid: [year, ...EPS cols..., NAV, ...profit].
# EPS (continuing-ops basic) at idx 4, NAV/share at idx 7, profit-for-year at idx 10.
_FUNDAMENTALS_NCOLS = 13
_EPS_COL, _NAV_COL, _PROFIT_COL = 4, 7, 10
_YEAR_RE = re.compile(r"^\d{4}$")
_DIV_YEAR_RE = re.compile(r"([\d.]+)\s*%?\s*B?\s*(\d{4})")  # '15% 2025' / '7%B 2018'


def _parse_financials(tree: HTMLParser, code: str) -> list[AnnualFinancial]:
    """Every full year of (EPS, NAV, profit) from the 'NAV Per Share' table; [] if absent."""
    table = next((t for t in tree.css("table") if "NAV Per Share" in t.text()), None)
    if table is None:
        return []
    out: list[AnnualFinancial] = []
    for row in table.css("tr"):
        cells = [c.text(strip=True) for c in row.css("td, th")]
        if len(cells) != _FUNDAMENTALS_NCOLS or not _YEAR_RE.match(cells[0] or ""):
            continue
        out.append(
            AnnualFinancial(
                market="DSE",
                code=code,
                fiscal_year=int(cells[0]),
                eps=_num(cells[_EPS_COL]),
                nav_per_share=_num(cells[_NAV_COL]),
                profit_mn=_num(cells[_PROFIT_COL]),
            )
        )
    return out


def _parse_dividends(tree: HTMLParser, code: str) -> list[DividendRecord]:
    """Merge the cash-dividend and stock-dividend history rows into one record per year."""
    by_year: dict[int, dict[str, float]] = {}
    for table in tree.css("table"):
        for row in table.css("tr"):
            cells = [c.text(strip=True) for c in row.css("td, th")]
            label = next(
                (c for c in cells if c in ("Cash Dividend", "Bonus Issue (Stock Dividend)")), None
            )
            if not label:
                continue
            history = next(
                (c for c in cells if c is not label and "%" in c and _DIV_YEAR_RE.search(c)), None
            )
            if not history:
                continue
            key = "cash_pct" if label == "Cash Dividend" else "bonus_pct"
            for pct, year in _DIV_YEAR_RE.findall(history):
                by_year.setdefault(int(year), {})[key] = float(pct)
    return [
        DividendRecord(market="DSE", code=code, year=y, **vals)
        for y, vals in sorted(by_year.items())
    ]


def _parse_credit_rating(tree: HTMLParser) -> tuple[str | None, str | None]:
    """Best-effort short/long credit rating — often blank on dsebd, so frequently (None, None)."""
    table = next((t for t in tree.css("table") if "Credit Rating" in t.text()), None)
    if table is None:
        return (None, None)
    short = long = None
    for row in table.css("tr"):
        cells = [c.text(strip=True) for c in row.css("td, th")]
        for i, cell in enumerate(cells):
            val = cells[i + 1] if i + 1 < len(cells) else ""
            if cell == "Short-term" and val:
                short = val
            elif cell == "Long-term" and val:
                long = val
    return (short, long)


def parse_sector_pe(html: str) -> list[SectorPE]:
    """Parse sectoral_PE.php — the [#, Sector Name, Sectoral Median P/E] table."""
    tree = HTMLParser(html)
    table = next((t for t in tree.css("table") if "Sectoral Median P/E" in t.text()), None)
    if table is None:
        return []
    out: list[SectorPE] = []
    for row in table.css("tr")[1:]:
        cells = [c.text(strip=True) for c in row.css("td, th")]
        if len(cells) >= 3 and cells[1]:
            out.append(SectorPE(market="DSE", sector=cells[1], median_pe=_num(cells[2])))
    return out


def _company_field_map(tree: HTMLParser) -> dict[str, str]:
    """Read every known company label to its value (value = cells[(i + n//2) % n])."""
    found: dict[str, str] = {}
    for table in tree.css("table"):
        for row in table.css("tr"):
            cells = [c.text(strip=True) for c in row.css("td, th")]
            n = len(cells)
            if n < 2:
                continue
            for i, cell in enumerate(cells):
                if cell in _COMPANY_LABELS:
                    val = cells[(i + n // 2) % n]
                    if val not in _COMPANY_LABELS and not found.get(cell):
                        found[cell] = val
    return found


def _parse_shareholdings(tree: HTMLParser, code: str) -> list[Shareholding]:
    """Each disclosure row carries an 'as on <date>' and a Sponsor/.../Public breakdown."""
    out: list[Shareholding] = []
    seen: set[dt.date] = set()
    for table in tree.css("table"):
        for row in table.css("tr"):
            joined = " ".join(c.text(strip=True) for c in row.css("td, th"))
            d = _AS_ON_RE.search(joined)
            sh = _SHAREHOLDING_RE.search(joined.replace(" ", ""))
            if not (d and sh):
                continue
            try:
                date = dt.datetime.strptime(d.group(1), "%b %d, %Y").date()
            except ValueError:
                continue
            if date in seen:
                continue
            sp, gv, ins, fo, pub = (float(x) for x in sh.groups())
            # A real disclosure's five categories always sum to ~100% by definition — unlike a
            # dividend percentage (which can legitimately hit 3000%+ for a stock like RECKITTBEN),
            # there's no such thing as a genuine 0% or 340% total. A miss here is always a parse
            # error (confirmed live: CNATEX/APOLOISPAT both stored 0/0/0/0/0). Drop, don't guess.
            if not (90.0 <= sp + gv + ins + fo + pub <= 110.0):
                continue
            seen.add(date)
            out.append(
                Shareholding(
                    market="DSE",
                    code=code,
                    as_of_date=date,
                    sponsor_director=sp,
                    govt=gv,
                    institute=ins,
                    foreign_pct=fo,
                    public=pub,
                )
            )
    return out


def parse_web_address(html: str) -> str | None:
    """Pull the company's own website from the displayCompany.php 'Web Address' row (used to hop to
    the site and fetch its logo). None when the field is blank."""
    tree = HTMLParser(html)
    for tr in tree.css("tr"):
        cells = tr.css("td, th")
        if len(cells) >= 2 and cells[0].text(strip=True).lower() == "web address":
            link = cells[1].css_first("a")
            url = (link.attributes.get("href") if link else None) or cells[1].text(strip=True)
            url = (url or "").strip()
            return url or None
    return None


def parse_company(html: str, code: str) -> CompanyInfo | None:
    """Parse displayCompany.php into a profile + shareholding history. None if the code is unknown."""
    tree = HTMLParser(html)
    fields = _company_field_map(tree)
    if not fields:  # unknown code / empty page — nothing to persist
        return None
    profile_kwargs: dict[str, object] = {"market": "DSE", "code": code}
    for label, (attr, coerce) in _COMPANY_LABELS.items():
        raw = fields.get(label)
        if raw is None or raw == "":
            continue
        value = coerce(raw)
        if value is not None and value != "":
            profile_kwargs[attr] = value

    # Derived/extra fundamentals: cash dividend % (leading number) + latest-year EPS and NAV.
    div = profile_kwargs.get("latest_dividend")
    if isinstance(div, str) and (m := _CASH_DIV_RE.match(div)):
        cash = _num(m.group(1))
        if cash is not None:
            profile_kwargs["cash_dividend_pct"] = cash

    financials = _parse_financials(tree, code)
    if financials:
        latest = max(financials, key=lambda f: f.fiscal_year)  # mirror latest year onto the profile
        if latest.eps is not None:
            profile_kwargs["eps"] = latest.eps
        if latest.nav_per_share is not None:
            profile_kwargs["nav_per_share"] = latest.nav_per_share

    short_rating, long_rating = _parse_credit_rating(tree)
    if short_rating:
        profile_kwargs["credit_rating_short"] = short_rating
    if long_rating:
        profile_kwargs["credit_rating_long"] = long_rating

    return CompanyInfo(
        profile=CompanyProfile(**profile_kwargs),
        shareholdings=_parse_shareholdings(tree, code),
        financials=financials,
        dividends=_parse_dividends(tree, code),
    )


class DseScrapeProvider:
    market = "DSE"

    def __init__(self, *, verify_ssl: bool = False, timeout: float = 25.0) -> None:
        self._verify_ssl = verify_ssl
        self._timeout = timeout

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            headers={"User-Agent": _UA},
            timeout=self._timeout,
            follow_redirects=True,
            verify=self._verify_ssl,
        )

    async def list_symbols(self) -> list[Symbol]:
        async with self._client() as client:
            resp = await client.get(_LATEST_URL)
            resp.raise_for_status()
        return parse_symbols(resp.text)

    async def get_quotes(self, codes: list[str]) -> list[Quote]:
        async with self._client() as client:
            resp = await client.get(_LATEST_URL)
            resp.raise_for_status()
        as_of = dt.datetime.now(dt.UTC)
        wanted = set(codes)
        return [q for q in parse_quotes(resp.text, as_of=as_of) if not wanted or q.code in wanted]

    async def get_daily_bars(self, code: str, start: dt.date, end: dt.date) -> list[Bar]:
        params = {
            "startDate": start.isoformat(),
            "endDate": end.isoformat(),
            "inst": code,
            "archive": "data",
        }
        async with self._client() as client:
            resp = await client.get(_ARCHIVE_URL, params=params)
            resp.raise_for_status()
        return parse_bars(resp.text)

    async def get_market_summary(self, start: dt.date, end: dt.date) -> list[MarketSummary]:
        params = {"startDate": start.isoformat(), "endDate": end.isoformat(), "archive": "data"}
        async with self._client() as client:
            resp = await client.get(_SUMMARY_URL, params=params)
            resp.raise_for_status()
        return parse_market_summary(resp.text)

    async def get_company(self, code: str) -> CompanyInfo | None:
        async with self._client() as client:
            resp = await client.get(_COMPANY_URL, params={"name": code})
            resp.raise_for_status()
        return parse_company(resp.text, code)

    async def get_company_website(self, code: str) -> str | None:
        """The company's own website URL, from the DSE company page (for logo fetching)."""
        async with self._client() as client:
            resp = await client.get(_COMPANY_URL, params={"name": code})
            resp.raise_for_status()
        return parse_web_address(resp.text)

    async def get_sector_pe(self) -> list[SectorPE]:
        async with self._client() as client:
            resp = await client.get(_SECTOR_PE_URL)
            resp.raise_for_status()
        return parse_sector_pe(resp.text)

    async def get_news(self, start: dt.date, end: dt.date) -> list[NewsItem]:
        params = {"startDate": str(start), "endDate": str(end), "inst": "All Instrument"}
        # load-news.php returns an empty body unless it looks like the DataTable's AJAX call —
        # the X-Requested-With header is the gate (a browser UA / Referer alone don't suffice).
        headers = {"X-Requested-With": "XMLHttpRequest"}
        async with self._client() as client:
            resp = await client.get(_NEWS_URL, params=params, headers=headers)
            resp.raise_for_status()
        return parse_news(resp.text)

    async def get_news_archive(self, start: dt.date, end: dt.date) -> list[NewsItem]:
        """Historical news for a date range from old_news.php.

        load-news.php is the *live* feed — it ignores startDate and only returns the last few days,
        so it can't backfill. old_news.php is the real archive: it honours the range and renders the
        full result server-side (no AJAX header needed). It's heavy (~1.5k items/month), so callers
        must chunk by month rather than requesting years at once.
        """
        params = {"startDate": str(start), "endDate": str(end), "criteria": 4, "archive": "news"}
        async with self._client() as client:
            resp = await client.get(_ARCHIVE_NEWS_URL, params=params)
            resp.raise_for_status()
        return parse_news(resp.text)
