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

import httpx
from selectolax.parser import HTMLParser

from bulls.market_data.provider import Bar, Quote, Symbol

_BASE = "https://www.dsebd.org"
_LATEST_URL = f"{_BASE}/latest_share_price_scroll_l.php"
_ARCHIVE_URL = f"{_BASE}/day_end_archive.php"
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
        bars.append(
            Bar(
                market="DSE",
                code=code,
                date=dt.date.fromisoformat(date_str),
                open=_num(_col(row, headers, "OPENP")) or close or 0.0,
                high=_num(_col(row, headers, "HIGH")) or close or 0.0,
                low=_num(_col(row, headers, "LOW")) or close or 0.0,
                close=close or 0.0,
                volume=int(_num(_col(row, headers, "VOLUME")) or 0),
            )
        )
    return bars


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
