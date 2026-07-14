"""No-key US EOD bar adapter backed by Yahoo's chart endpoint.

This is a free, replaceable bootstrap provider. It intentionally lives behind the same
MarketDataProvider boundary as the DSE scraper, so a licensed feed can replace it without changing
API/UI code. It provides historical daily bars only; it does not pretend to be a real-time quote
feed.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

import httpx

from bulls.market_data.provider import (
    Bar,
    CompanyInfo,
    MarketSummary,
    NewsItem,
    Quote,
    SectorPE,
    Symbol,
)
from bulls.market_data.providers.us_security_master import fetch_us_security_master

YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
_UA = "Mozilla/5.0 BullsOfTheWorld/0.1 us-eod-bars"

# No US security-master field carries a company website (unlike DSE, which publishes one per
# listing), so only hand-reviewed ETF/fund issuer domains are returned. Inventing `companyname.com`
# can successfully fetch an unrelated site and attach a false logo, which is worse than a monogram.
_ISSUER_DOMAINS: dict[str, str] = {
    "ishares": "ishares.com",
    "vanguard": "vanguard.com",
    "spdr": "ssga.com",
    "invesco": "invesco.com",
    "schwab": "schwabassetmanagement.com",
    "wisdomtree": "wisdomtree.com",
    "vaneck": "vaneck.com",
    "global x": "globalxetfs.com",
    "first trust": "ftportfolios.com",
    "proshares": "proshares.com",
    "direxion": "direxion.com",
    "janus henderson": "janushenderson.com",
    "jpmorgan": "jpmorgan.com",
    "fidelity": "fidelity.com",
    "goldman sachs": "gsam.com",
    "pimco": "pimco.com",
    "blackrock": "blackrock.com",
}

# Ticker-specific issuer domains are added only after reviewing the issuer/IR site. This avoids
# attaching an unrelated logo when a generic company-name domain happens to exist.
_SYMBOL_DOMAINS: dict[str, str] = {
    "AEON": "aeonbiopharma.com",
    "AGEN": "agenusbio.com",
    "MIMI": "mimintinc.com",
    "NXTC": "nextcure.com",
    "QTTB": "q32bio.com",
    "SKYQ": "skyquarry.com",
    "VEEE": "twinvee.com",
    "VMAR": "visionmarinetechnologies.com",
}


def _guess_domain(name: str) -> str | None:
    """Return only an audited issuer domain; never synthesize a company domain."""
    for keyword, domain in _ISSUER_DOMAINS.items():
        if keyword in name.lower():
            return domain
    return None


def yahoo_symbol(code: str) -> str:
    """Map our public US code to Yahoo's chart symbol convention."""
    return code.strip().upper().replace(".", "-")


def _period(d: dt.date) -> int:
    return int(dt.datetime.combine(d, dt.time.min, tzinfo=dt.UTC).timestamp())


def parse_yahoo_chart(data: dict[str, Any], *, market: str, code: str) -> list[Bar]:
    chart = data.get("chart") if isinstance(data, dict) else None
    if not isinstance(chart, dict) or chart.get("error"):
        return []
    results = chart.get("result")
    if not isinstance(results, list) or not results:
        return []
    result = results[0]
    if not isinstance(result, dict):
        return []
    timestamps = result.get("timestamp")
    indicators = result.get("indicators")
    if not isinstance(timestamps, list) or not isinstance(indicators, dict):
        return []
    quotes = indicators.get("quote")
    if not isinstance(quotes, list) or not quotes or not isinstance(quotes[0], dict):
        return []
    quote = quotes[0]
    opens = quote.get("open") or []
    highs = quote.get("high") or []
    lows = quote.get("low") or []
    closes = quote.get("close") or []
    volumes = quote.get("volume") or []
    adjusted_sets = indicators.get("adjclose") or []
    adjusted = (
        adjusted_sets[0].get("adjclose") or []
        if adjusted_sets and isinstance(adjusted_sets[0], dict)
        else []
    )

    out: list[Bar] = []
    for i, ts in enumerate(timestamps):
        try:
            open_ = opens[i]
            high = highs[i]
            low = lows[i]
            close = closes[i]
            volume = volumes[i]
        except IndexError:
            continue
        if None in (open_, high, low, close):
            continue
        open_f = float(open_)
        high_f = float(high)
        low_f = float(low)
        close_f = float(close)
        if min(open_f, high_f, low_f, close_f) <= 0 or high_f < low_f:
            continue
        out.append(
            Bar(
                market=market,
                code=code,
                date=dt.datetime.fromtimestamp(int(ts), tz=dt.UTC).date(),
                open=open_f,
                high=high_f,
                low=low_f,
                close=close_f,
                volume=int(volume or 0),
                adjusted_close=(
                    float(adjusted[i])
                    if i < len(adjusted) and adjusted[i] is not None
                    else None
                ),
                source="yahoo_chart",
            )
        )
    return out


class YahooUsEodProvider:
    market = "US"

    def __init__(self, *, timeout: float = 20.0) -> None:
        self._timeout = timeout
        self._names_by_code: dict[str, str] | None = None  # lazy, one fetch for the whole run

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            headers={"User-Agent": _UA, "Accept": "application/json"},
            timeout=self._timeout,
            follow_redirects=True,
        )

    async def list_symbols(self) -> list[Symbol]:
        records = await fetch_us_security_master(_UA)
        return [
            Symbol(market=r.market, code=r.symbol, name_en=r.security_name)
            for r in records
            if r.is_product_eligible
        ]

    async def get_quotes(self, codes: list[str]) -> list[Quote]:
        return []

    async def get_daily_bars(self, code: str, start: dt.date, end: dt.date) -> list[Bar]:
        if end < start:
            return []
        params = {
            "period1": str(_period(start)),
            # Yahoo treats period2 as an exclusive boundary; include the requested end date.
            "period2": str(_period(end + dt.timedelta(days=1))),
            "interval": "1d",
            "events": "history",
            "includeAdjustedClose": "true",
        }
        async with self._client() as client:
            try:
                resp = await client.get(YAHOO_CHART_URL.format(symbol=yahoo_symbol(code)), params=params)
                resp.raise_for_status()
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 404:
                    return []
                raise
        return parse_yahoo_chart(resp.json(), market=self.market, code=code.upper())

    async def get_market_summary(self, start: dt.date, end: dt.date) -> list[MarketSummary]:
        return []

    async def get_company(self, code: str) -> CompanyInfo | None:
        return None

    async def get_company_website(self, code: str) -> str | None:
        """Audited issuer domain for logo fetching, when one is known."""
        normalized = code.strip().upper()
        if normalized in _SYMBOL_DOMAINS:
            return _SYMBOL_DOMAINS[normalized]
        if self._names_by_code is None:
            records = await fetch_us_security_master(_UA)
            self._names_by_code = {r.symbol: r.security_name for r in records}
        name = self._names_by_code.get(normalized)
        return _guess_domain(name) if name else None

    async def get_sector_pe(self) -> list[SectorPE]:
        return []

    async def get_news(self, start: dt.date, end: dt.date) -> list[NewsItem]:
        return []
