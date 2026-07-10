"""US security-master sources.

Nasdaq Trader's public symbol directories are the authoritative daily listing feed for Nasdaq-listed
and other-listed US equities. SEC's ticker/exchange JSON enriches listed symbols with CIKs for
filings/fundamentals. This module is deliberately pure except for the fetch helper; ingestion owns
database writes.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Iterable, Mapping

import httpx
from pydantic import BaseModel

NASDAQ_LISTED_URL = "https://www.nasdaqtrader.com/dynamic/symdir/nasdaqlisted.txt"
OTHER_LISTED_URL = "https://www.nasdaqtrader.com/dynamic/symdir/otherlisted.txt"
SEC_TICKERS_EXCHANGE_URL = "https://www.sec.gov/files/company_tickers_exchange.json"

NASDAQ_MARKET_CATEGORY = {
    "Q": "Nasdaq Global Select Market",
    "G": "Nasdaq Global Market",
    "S": "Nasdaq Capital Market",
}

OTHER_LISTED_EXCHANGE = {
    "A": "NYSE American",
    "N": "NYSE",
    "P": "NYSE Arca",
    "Z": "Cboe BZX",
    "V": "IEX",
}

PRODUCT_INSTRUMENT_TYPES = frozenset({"common_stock", "adr", "etf"})


class SecTicker(BaseModel):
    cik: int
    name: str
    ticker: str
    exchange: str


class UsSecurityRecord(BaseModel):
    market: str = "US"
    symbol: str
    raw_symbol: str
    security_name: str
    exchange: str | None
    exchange_tier: str | None = None
    cqs_symbol: str | None = None
    nasdaq_symbol: str | None = None
    cik: int | None = None
    instrument_type: str
    is_etf: bool = False
    is_test_issue: bool = False
    is_active: bool = True
    is_product_eligible: bool = False
    exclude_reason: str | None = None
    round_lot_size: int | None = None
    financial_status: str | None = None
    source: str = "nasdaq_trader"
    source_file: str


def _yn(value: str | None) -> bool:
    return (value or "").strip().upper() == "Y"


def _int_or_none(value: str | None) -> int | None:
    value = (value or "").strip()
    return int(value) if value.isdigit() else None


def _normalize_symbol(value: str) -> str:
    return value.strip().upper()


def classify_instrument(
    name: str,
    *,
    is_etf: bool,
    nextshares: bool = False,
    assume_common: bool = False,
) -> str:
    lower = name.lower()
    if nextshares:
        return "nextshares"
    if is_etf:
        return "etf"
    if "preferred" in lower or "preference" in lower or " pfd" in lower:
        return "preferred_stock"
    if "warrant" in lower:
        return "warrant"
    if " right" in lower or lower.endswith("rights") or " rights" in lower:
        return "right"
    if " unit" in lower or lower.endswith("units") or " units" in lower:
        return "unit"
    if any(token in lower for token in (" note", " notes", " bond", " debenture")):
        return "debt"
    if any(
        token in lower
        for token in (
            "american depositary",
            "american depository",
            " adr",
            " ads",
        )
    ):
        return "adr"
    # Non-American depositary shares usually represent preferred equity. ADR/ADS wording was
    # handled above, and explicit "preferred"/"pfd" wording was handled earlier.
    if "depositary share" in lower or "depository share" in lower:
        return "preferred_stock"
    if any(
        token in lower
        for token in (
            "common stock",
            "common share",
            "ordinary share",
            "ordinary shares",
            "capital stock",
        )
    ):
        return "common_stock"
    # NYSE-family records often carry only the issuer name (for example "Visa Inc."). Reaching
    # this fallback means every known non-common security marker above was excluded.
    return "common_stock" if assume_common else "other"


def eligibility_reason(
    instrument_type: str, *, is_test_issue: bool, financial_status: str | None
) -> tuple[bool, str | None]:
    if is_test_issue:
        return False, "test_issue"
    if financial_status and financial_status != "N":
        return False, f"financial_status_{financial_status.lower()}"
    if instrument_type not in PRODUCT_INSTRUMENT_TYPES:
        return False, instrument_type
    return True, None


def _data_rows(text: str) -> Iterable[dict[str, str]]:
    reader = csv.DictReader(io.StringIO(text.strip()), delimiter="|")
    for row in reader:
        if not row:
            continue
        first = next(iter(row.values()), "")
        if (first or "").startswith("File Creation Time"):
            continue
        yield {k.strip(): (v or "").strip() for k, v in row.items() if k is not None}


def parse_nasdaq_listed(text: str) -> list[UsSecurityRecord]:
    records: list[UsSecurityRecord] = []
    for row in _data_rows(text):
        symbol = _normalize_symbol(row["Symbol"])
        name = row["Security Name"]
        is_etf = _yn(row.get("ETF"))
        is_test = _yn(row.get("Test Issue"))
        financial_status = (row.get("Financial Status") or "").strip() or None
        instrument_type = classify_instrument(
            name, is_etf=is_etf, nextshares=_yn(row.get("NextShares"))
        )
        eligible, reason = eligibility_reason(
            instrument_type, is_test_issue=is_test, financial_status=financial_status
        )
        category = (row.get("Market Category") or "").strip() or None
        records.append(
            UsSecurityRecord(
                symbol=symbol,
                raw_symbol=symbol,
                security_name=name,
                exchange="Nasdaq",
                exchange_tier=NASDAQ_MARKET_CATEGORY.get(category or "", category),
                nasdaq_symbol=symbol,
                instrument_type=instrument_type,
                is_etf=is_etf,
                is_test_issue=is_test,
                is_product_eligible=eligible,
                exclude_reason=reason,
                round_lot_size=_int_or_none(row.get("Round Lot Size")),
                financial_status=financial_status,
                source_file="nasdaqlisted",
            )
        )
    return records


def parse_other_listed(text: str) -> list[UsSecurityRecord]:
    records: list[UsSecurityRecord] = []
    for row in _data_rows(text):
        raw_symbol = _normalize_symbol(row["ACT Symbol"])
        nasdaq_symbol = _normalize_symbol(row.get("NASDAQ Symbol") or raw_symbol)
        name = row["Security Name"]
        is_etf = _yn(row.get("ETF"))
        is_test = _yn(row.get("Test Issue"))
        instrument_type = classify_instrument(name, is_etf=is_etf, assume_common=True)
        eligible, reason = eligibility_reason(
            instrument_type, is_test_issue=is_test, financial_status=None
        )
        exchange_code = (row.get("Exchange") or "").strip() or None
        records.append(
            UsSecurityRecord(
                symbol=nasdaq_symbol,
                raw_symbol=raw_symbol,
                security_name=name,
                exchange=OTHER_LISTED_EXCHANGE.get(exchange_code or "", exchange_code),
                exchange_tier=exchange_code,
                cqs_symbol=(row.get("CQS Symbol") or "").strip() or None,
                nasdaq_symbol=nasdaq_symbol,
                instrument_type=instrument_type,
                is_etf=is_etf,
                is_test_issue=is_test,
                is_product_eligible=eligible,
                exclude_reason=reason,
                round_lot_size=_int_or_none(row.get("Round Lot Size")),
                source_file="otherlisted",
            )
        )
    return records


def parse_sec_tickers_exchange(data: Mapping[str, object]) -> dict[str, SecTicker]:
    fields = [str(f) for f in data.get("fields", [])]
    out: dict[str, SecTicker] = {}
    for values in data.get("data", []):
        if not isinstance(values, list):
            continue
        row = dict(zip(fields, values, strict=False))
        ticker = _normalize_symbol(str(row.get("ticker", "")))
        if not ticker:
            continue
        out[ticker] = SecTicker(
            cik=int(row["cik"]),
            name=str(row["name"]),
            ticker=ticker,
            exchange=str(row.get("exchange") or ""),
        )
    return out


def enrich_with_sec_ciks(
    records: Iterable[UsSecurityRecord], sec_tickers: Mapping[str, SecTicker]
) -> list[UsSecurityRecord]:
    out: list[UsSecurityRecord] = []
    for record in records:
        sec = sec_tickers.get(record.symbol)
        out.append(record.model_copy(update={"cik": sec.cik if sec else None}))
    return out


async def fetch_us_security_master(user_agent: str) -> list[UsSecurityRecord]:
    headers = {"User-Agent": user_agent, "Accept": "text/plain,application/json"}
    async with httpx.AsyncClient(headers=headers, timeout=30.0, follow_redirects=True) as client:
        nasdaq_resp = await client.get(NASDAQ_LISTED_URL)
        nasdaq_resp.raise_for_status()
        other_resp = await client.get(OTHER_LISTED_URL)
        other_resp.raise_for_status()
        sec_resp = await client.get(SEC_TICKERS_EXCHANGE_URL)
        sec_resp.raise_for_status()

    records = parse_nasdaq_listed(nasdaq_resp.text) + parse_other_listed(other_resp.text)
    sec_tickers = parse_sec_tickers_exchange(sec_resp.json())
    return enrich_with_sec_ciks(records, sec_tickers)
