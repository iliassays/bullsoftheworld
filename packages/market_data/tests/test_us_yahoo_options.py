from __future__ import annotations

import datetime as dt
import json

import httpx
import pytest

from bulls.market_data.options.chain import analyze_option_chain
from bulls.market_data.providers.us_yahoo_options import (
    OptionChainProviderError,
    YahooUsOptionChainProvider,
    parse_yahoo_option_chain,
)


def _contract(
    symbol: str,
    strike: float,
    *,
    bid: float = 4.5,
    ask: float = 5.5,
    volume: int = 50,
    open_interest: int = 100,
    iv: float = 0.4,
) -> dict[str, object]:
    return {
        "contractSymbol": symbol,
        "strike": strike,
        "currency": "USD",
        "lastPrice": 5.0,
        "bid": bid,
        "ask": ask,
        "volume": volume,
        "openInterest": open_interest,
        "impliedVolatility": iv,
        "inTheMoney": strike < 100,
        "lastTradeDate": 1784246400,
        "contractSize": "REGULAR",
    }


def _payload() -> dict[str, object]:
    expiration = 1785456000  # 2026-07-31 UTC
    return {
        "optionChain": {
            "result": [
                {
                    "underlyingSymbol": "TEST",
                    "expirationDates": [expiration, 1787875200],
                    "quote": {
                        "regularMarketPrice": 100.0,
                        "regularMarketTime": 1784246400,
                        "marketState": "CLOSED",
                        "currency": "USD",
                    },
                    "options": [
                        {
                            "expirationDate": expiration,
                            "calls": [
                                _contract("TEST260731C00095000", 95, iv=0.38),
                                _contract("TEST260731C00100000", 100, iv=0.40),
                                _contract("TEST260731C00105000", 105, iv=0.42),
                                _contract("TEST260731C00110000", 110, iv=0.44),
                            ],
                            "puts": [
                                _contract("TEST260731P00090000", 90, iv=0.52),
                                _contract("TEST260731P00095000", 95, iv=0.50),
                                _contract("TEST260731P00100000", 100, iv=0.46),
                                _contract("TEST260731P00105000", 105, iv=0.45),
                            ],
                        }
                    ],
                }
            ],
            "error": None,
        }
    }


def test_parse_and_analyze_yahoo_option_chain() -> None:
    observed_at = dt.datetime(2026, 7, 17, 12, tzinfo=dt.UTC)
    snapshot = parse_yahoo_option_chain(_payload(), code="test", fetched_at=observed_at)
    analysis = analyze_option_chain(snapshot)

    assert snapshot.code == "TEST"
    assert snapshot.expiration == dt.date(2026, 7, 31)
    assert len(snapshot.available_expirations) == 2
    assert snapshot.is_delayed is True
    assert snapshot.source == "yahoo_unofficial"
    assert len(snapshot.contracts) == 8
    assert all(contract.liquidity == "usable" for contract in snapshot.contracts)
    assert analysis.metrics.quality == "usable"
    assert analysis.metrics.put_call_volume_ratio == 1.0
    assert analysis.metrics.put_call_open_interest_ratio == 1.0
    assert analysis.metrics.atm_implied_volatility_pct == 43.0
    assert analysis.metrics.approximate_downside_skew_pp == 8.0
    assert analysis.metrics.implied_move_pct == 10.0


def test_parser_marks_missing_two_sided_quotes_as_unquoted() -> None:
    payload = _payload()
    calls = payload["optionChain"]["result"][0]["options"][0]["calls"]  # type: ignore[index]
    calls[0]["bid"] = 0  # type: ignore[index]
    calls[0]["ask"] = 0  # type: ignore[index]

    snapshot = parse_yahoo_option_chain(
        payload,
        code="TEST",
        fetched_at=dt.datetime.now(dt.UTC),
    )

    contract = next(
        item for item in snapshot.contracts if item.contract_symbol == "TEST260731C00095000"
    )
    assert contract.liquidity == "unquoted"
    assert contract.midpoint is None


async def test_provider_uses_cookie_crumb_and_requested_expiration() -> None:
    seen_dates: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "fc.yahoo.com":
            return httpx.Response(404, headers={"set-cookie": "A=session; Path=/"})
        if request.url.path == "/v1/test/getcrumb":
            return httpx.Response(200, text="crumb-value")
        seen_dates.append(request.url.params.get("date"))
        assert request.url.params["crumb"] == "crumb-value"
        return httpx.Response(200, content=json.dumps(_payload()).encode())

    provider = YahooUsOptionChainProvider(transport=httpx.MockTransport(handler))
    snapshot = await provider.get_option_chain("test", dt.date(2026, 7, 31))

    assert snapshot.code == "TEST"
    assert seen_dates == [str(1785456000)]


async def test_provider_default_avoids_expiry_inside_seven_days() -> None:
    requested_dates: list[str | None] = []
    today = dt.datetime.now(dt.UTC).date()
    first_expiry = int(
        dt.datetime.combine(today + dt.timedelta(days=1), dt.time.min, tzinfo=dt.UTC).timestamp()
    )
    target_expiry = int(
        dt.datetime.combine(today + dt.timedelta(days=8), dt.time.min, tzinfo=dt.UTC).timestamp()
    )

    def payload(expiry: int) -> dict[str, object]:
        value = _payload()
        result = value["optionChain"]["result"][0]  # type: ignore[index]
        result["expirationDates"] = [first_expiry, target_expiry]  # type: ignore[index]
        result["options"][0]["expirationDate"] = expiry  # type: ignore[index]
        return value

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "fc.yahoo.com":
            return httpx.Response(404, headers={"set-cookie": "A=session; Path=/"})
        if request.url.path == "/v1/test/getcrumb":
            return httpx.Response(200, text="crumb-value")
        requested = request.url.params.get("date")
        requested_dates.append(requested)
        expiry = int(requested) if requested is not None else first_expiry
        return httpx.Response(200, content=json.dumps(payload(expiry)).encode())

    provider = YahooUsOptionChainProvider(transport=httpx.MockTransport(handler))
    snapshot = await provider.get_option_chain("TEST")

    assert requested_dates == [None, str(target_expiry)]
    assert snapshot.expiration == dt.datetime.fromtimestamp(target_expiry, tz=dt.UTC).date()


async def test_provider_rejects_non_json_response_after_bounded_retry() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/test/getcrumb":
            return httpx.Response(200, text="crumb-value")
        if request.url.host == "fc.yahoo.com":
            return httpx.Response(404)
        return httpx.Response(200, text="not-json")

    provider = YahooUsOptionChainProvider(transport=httpx.MockTransport(handler))

    with pytest.raises(OptionChainProviderError):
        await provider.get_option_chain("TEST")
