"""Experimental owner-preview option-chain adapter backed by Yahoo Finance.

Yahoo's option endpoint requires a session cookie and crumb.  The adapter performs that handshake
with one bounded retry and returns provider-neutral values.  It is intentionally not registered as
a licensed production feed and must be surfaced as delayed, unofficial evidence.
"""

from __future__ import annotations

import datetime as dt
import math
import re
from typing import Any

import httpx

from bulls.market_data.options.chain import OptionChainSnapshot, OptionContract
from bulls.market_data.providers.us_yahoo import yahoo_symbol

YAHOO_COOKIE_URL = "https://fc.yahoo.com"
YAHOO_CRUMB_URL = "https://query2.finance.yahoo.com/v1/test/getcrumb"
YAHOO_OPTIONS_URL = "https://query2.finance.yahoo.com/v7/finance/options/{symbol}"
_UA = "Mozilla/5.0 BullsOfTheWorld/0.1 owner-options-preview"
_CODE_RE = re.compile(r"^[A-Z0-9][A-Z0-9.\-]{0,15}$")


class OptionChainUnavailable(LookupError):
    """The provider has no usable chain for the requested symbol or expiration."""


class OptionChainProviderError(RuntimeError):
    """The upstream provider could not be queried or returned an invalid response."""


def _finite_number(value: Any, *, positive: bool = False) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or (positive and number <= 0):
        return None
    return number


def _non_negative_int(value: Any) -> int | None:
    number = _finite_number(value)
    if number is None or number < 0:
        return None
    return int(number)


def _utc_datetime(value: Any) -> dt.datetime | None:
    number = _finite_number(value)
    if number is None or number <= 0:
        return None
    try:
        return dt.datetime.fromtimestamp(number, tz=dt.UTC)
    except (OverflowError, OSError, ValueError):
        return None


def _utc_date(value: Any) -> dt.date | None:
    timestamp = _utc_datetime(value)
    return timestamp.date() if timestamp is not None else None


def _contract(
    row: Any,
    *,
    option_type: str,
    expiration: dt.date,
    default_currency: str,
) -> OptionContract | None:
    if not isinstance(row, dict):
        return None
    strike = _finite_number(row.get("strike"), positive=True)
    symbol = row.get("contractSymbol")
    if strike is None or not isinstance(symbol, str) or not symbol.strip():
        return None

    bid = _finite_number(row.get("bid"))
    ask = _finite_number(row.get("ask"))
    midpoint: float | None = None
    spread_pct: float | None = None
    if bid is not None and ask is not None and bid > 0 and ask >= bid:
        midpoint = round((bid + ask) / 2, 4)
        spread_pct = round((ask - bid) / midpoint * 100, 2) if midpoint > 0 else None

    activity = (_non_negative_int(row.get("volume")) or 0) + (
        _non_negative_int(row.get("openInterest")) or 0
    )
    if midpoint is None:
        liquidity = "unquoted"
    elif spread_pct is not None and spread_pct <= 25 and activity >= 25:
        liquidity = "usable"
    else:
        liquidity = "thin"

    iv = _finite_number(row.get("impliedVolatility"))
    return OptionContract(
        contract_symbol=symbol.strip(),
        option_type=option_type,  # type: ignore[arg-type]
        expiration=expiration,
        strike=strike,
        currency=str(row.get("currency") or default_currency),
        last_price=_finite_number(row.get("lastPrice")),
        bid=bid,
        ask=ask,
        midpoint=midpoint,
        spread_pct=spread_pct,
        volume=_non_negative_int(row.get("volume")),
        open_interest=_non_negative_int(row.get("openInterest")),
        implied_volatility_pct=round(iv * 100, 2) if iv is not None and iv >= 0 else None,
        in_the_money=bool(row.get("inTheMoney", False)),
        last_trade_at=_utc_datetime(row.get("lastTradeDate")),
        contract_size=str(row["contractSize"]) if row.get("contractSize") else None,
        liquidity=liquidity,
    )


def parse_yahoo_option_chain(
    data: dict[str, Any],
    *,
    code: str,
    fetched_at: dt.datetime,
) -> OptionChainSnapshot:
    chain = data.get("optionChain") if isinstance(data, dict) else None
    if not isinstance(chain, dict):
        raise OptionChainProviderError("Yahoo returned an invalid option-chain envelope")
    if chain.get("error"):
        raise OptionChainUnavailable("Yahoo has no option chain for this request")
    results = chain.get("result")
    if not isinstance(results, list) or not results or not isinstance(results[0], dict):
        raise OptionChainUnavailable("Yahoo has no option chain for this request")

    result = results[0]
    quote = result.get("quote") if isinstance(result.get("quote"), dict) else {}
    option_sets = result.get("options")
    if not isinstance(option_sets, list) or not option_sets or not isinstance(option_sets[0], dict):
        raise OptionChainUnavailable("No contracts were returned for this expiration")
    option_set = option_sets[0]
    expiration = _utc_date(option_set.get("expirationDate"))
    spot = _finite_number(quote.get("regularMarketPrice"), positive=True)
    if expiration is None or spot is None:
        raise OptionChainProviderError("Yahoo omitted required chain identity fields")

    currency = str(quote.get("currency") or "USD")
    contracts: list[OptionContract] = []
    for option_type, key in (("call", "calls"), ("put", "puts")):
        rows = option_set.get(key)
        if not isinstance(rows, list):
            continue
        contracts.extend(
            contract
            for row in rows
            if (
                contract := _contract(
                    row,
                    option_type=option_type,
                    expiration=expiration,
                    default_currency=currency,
                )
            )
            is not None
        )
    if not contracts:
        raise OptionChainUnavailable("No valid contracts were returned for this expiration")

    expirations = sorted(
        date
        for raw in (result.get("expirationDates") or [])
        if (date := _utc_date(raw)) is not None
    )
    normalized_code = code.strip().upper()
    return OptionChainSnapshot(
        code=normalized_code,
        expiration=expiration,
        available_expirations=expirations,
        underlying_price=spot,
        underlying_as_of=_utc_datetime(quote.get("regularMarketTime")),
        market_state=str(quote["marketState"]) if quote.get("marketState") else None,
        fetched_at=fetched_at.astimezone(dt.UTC),
        currency=currency,
        source="yahoo_unofficial",
        source_url=f"https://finance.yahoo.com/quote/{yahoo_symbol(normalized_code)}/options",
        is_delayed=True,
        contracts=sorted(contracts, key=lambda item: (item.strike, item.option_type)),
    )


class YahooUsOptionChainProvider:
    market = "US"

    def __init__(
        self,
        *,
        timeout: float = 12.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._timeout = timeout
        self._transport = transport

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            headers={"User-Agent": _UA, "Accept": "application/json,text/plain,*/*"},
            timeout=self._timeout,
            follow_redirects=True,
            transport=self._transport,
        )

    async def get_option_chain(
        self,
        code: str,
        expiration: dt.date | None = None,
    ) -> OptionChainSnapshot:
        normalized = code.strip().upper()
        if not _CODE_RE.fullmatch(normalized):
            raise ValueError("Invalid US ticker")
        params: dict[str, str] = {}
        if expiration is not None:
            timestamp = dt.datetime.combine(expiration, dt.time.min, tzinfo=dt.UTC)
            params["date"] = str(int(timestamp.timestamp()))

        async with self._client() as client:
            for attempt in range(2):
                if attempt:
                    client.cookies.clear()
                try:
                    # fc.yahoo.com commonly returns an error status but still establishes the
                    # session cookie, so its body/status are intentionally ignored.
                    await client.get(YAHOO_COOKIE_URL)
                    crumb_response = await client.get(YAHOO_CRUMB_URL)
                    crumb_response.raise_for_status()
                    crumb = crumb_response.text.strip()
                    if not crumb or crumb.startswith("{"):
                        raise OptionChainProviderError("Yahoo did not issue a valid session crumb")
                    response = await client.get(
                        YAHOO_OPTIONS_URL.format(symbol=yahoo_symbol(normalized)),
                        params={**params, "crumb": crumb},
                    )
                    if response.status_code in {401, 403} and attempt == 0:
                        continue
                    if response.status_code == 404:
                        raise OptionChainUnavailable("No option chain is available for this ticker")
                    response.raise_for_status()
                    try:
                        payload = response.json()
                    except ValueError as exc:
                        raise OptionChainProviderError("Yahoo returned non-JSON option data") from exc
                    fetched_at = dt.datetime.now(dt.UTC)
                    snapshot = parse_yahoo_option_chain(
                        payload,
                        code=normalized,
                        fetched_at=fetched_at,
                    )
                    if expiration is None:
                        minimum_expiry = fetched_at.date() + dt.timedelta(days=7)
                        target = next(
                            (
                                value
                                for value in snapshot.available_expirations
                                if value >= minimum_expiry
                            ),
                            snapshot.expiration,
                        )
                        if target != snapshot.expiration:
                            target_timestamp = dt.datetime.combine(
                                target,
                                dt.time.min,
                                tzinfo=dt.UTC,
                            )
                            target_response = await client.get(
                                YAHOO_OPTIONS_URL.format(symbol=yahoo_symbol(normalized)),
                                params={
                                    "date": str(int(target_timestamp.timestamp())),
                                    "crumb": crumb,
                                },
                            )
                            if target_response.status_code in {401, 403} and attempt == 0:
                                continue
                            target_response.raise_for_status()
                            try:
                                target_payload = target_response.json()
                            except ValueError as exc:
                                raise OptionChainProviderError(
                                    "Yahoo returned non-JSON option data"
                                ) from exc
                            snapshot = parse_yahoo_option_chain(
                                target_payload,
                                code=normalized,
                                fetched_at=fetched_at,
                            )
                    return snapshot
                except OptionChainUnavailable:
                    raise
                except (httpx.HTTPError, OptionChainProviderError) as exc:
                    if attempt == 0:
                        continue
                    raise OptionChainProviderError("Yahoo option-chain request failed") from exc

        raise OptionChainProviderError("Yahoo option-chain request failed")
