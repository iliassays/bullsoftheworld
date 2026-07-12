from __future__ import annotations

import asyncio
import datetime as dt
from urllib.parse import parse_qs, urlparse

from bulls.market_data.providers import us_universe_discovery
from bulls.market_data.providers.us_universe_discovery import (
    fetch_yahoo_spark,
    merge_share_frames,
    parse_sec_company_facts_shares,
    parse_sec_shares_frame,
    parse_yahoo_spark,
)


def test_company_facts_share_parser_prefers_latest_filed_observation() -> None:
    payload = {
        "cik": 123,
        "facts": {
            "dei": {
                "EntityCommonStockSharesOutstanding": {
                    "units": {
                        "shares": [
                            {
                                "end": "2026-03-31",
                                "filed": "2026-04-20",
                                "val": 10_000_000,
                                "accn": "old",
                                "frame": "CY2026Q1I",
                            },
                            {
                                "end": "2026-03-31",
                                "filed": "2026-04-25",
                                "val": 11_000_000,
                                "accn": "amended",
                                "frame": "CY2026Q1I",
                            },
                        ]
                    }
                }
            }
        },
    }

    observation = parse_sec_company_facts_shares(payload)

    assert observation is not None
    assert observation.cik == 123
    assert observation.shares == 11_000_000
    assert observation.accession == "amended"
    assert observation.period == "CY2026Q1I"


def test_sec_frame_parser_keeps_positive_latest_fact_per_cik() -> None:
    older = parse_sec_shares_frame(
        {
            "data": [
                {"cik": 100, "end": "2025-12-31", "val": 10_000_000, "accn": "a"},
                {"cik": 200, "end": "bad", "val": 5, "accn": "b"},
                {"cik": 300, "end": "2025-12-31", "val": -1, "accn": "c"},
            ]
        },
        period="CY2025Q4I",
    )
    newer = parse_sec_shares_frame(
        {"data": [{"cik": 100, "end": "2026-03-31", "val": 12_000_000, "accn": "d"}]},
        period="CY2026Q1I",
    )

    merged = merge_share_frames([older, newer])

    assert set(merged) == {100}
    assert merged[100].shares == 12_000_000
    assert merged[100].end == dt.date(2026, 3, 31)
    assert merged[100].period == "CY2026Q1I"


def test_yahoo_spark_parser_computes_eod_price_and_median_dollar_volume() -> None:
    timestamps = [1_767_225_600 + day * 86_400 for day in range(21)]
    closes = [10.0 + day for day in range(21)]
    volumes = [100_000 + day * 1_000 for day in range(21)]
    payload = {
        "spark": {
            "result": [
                {
                    "symbol": "TEST",
                    "response": [
                        {
                            "timestamp": timestamps,
                            "indicators": {"quote": [{"close": closes, "volume": volumes}]},
                        }
                    ],
                },
                {"symbol": "EMPTY", "response": [{"timestamp": [], "indicators": {}}]},
            ]
        }
    }

    observations = parse_yahoo_spark(payload)

    assert set(observations) == {"TEST"}
    assert observations["TEST"].latest_close == 30.0
    assert observations["TEST"].sessions == 21
    expected = sorted(
        closes[index] * volumes[index] / 1e6 for index in range(1, 21)
    )
    assert observations["TEST"].median_dollar_volume_mn_20d == round(
        (expected[9] + expected[10]) / 2,
        6,
    )


def test_yahoo_spark_price_only_response_remains_usable_for_cap_preselection() -> None:
    payload = {
        "spark": {
            "result": [
                {
                    "symbol": "PRICE",
                    "response": [
                        {
                            "timestamp": [1_767_225_600, 1_767_312_000],
                            "indicators": {"quote": [{"close": [10.0, 11.0]}]},
                        }
                    ],
                }
            ]
        }
    }

    observation = parse_yahoo_spark(payload)["PRICE"]

    assert observation.latest_close == 11.0
    assert observation.sessions == 2
    assert observation.median_dollar_volume_mn_20d is None
    assert observation.nonzero_volume_ratio is None


def test_yahoo_spark_reconciles_partial_success_responses(monkeypatch) -> None:
    async def partial_response(client, url, **kwargs):
        del client, kwargs
        symbols = parse_qs(urlparse(url).query)["symbols"][0].split(",")
        returned = symbols[:1]
        return {
            "spark": {
                "result": [
                    {
                        "symbol": symbol,
                        "response": [
                            {
                                "timestamp": [1_767_225_600],
                                "indicators": {"quote": [{"close": [10.0]}]},
                            }
                        ],
                    }
                    for symbol in returned
                ]
            }
        }

    monkeypatch.setattr(us_universe_discovery, "_get_json_with_retry", partial_response)

    observations = asyncio.run(fetch_yahoo_spark(["AAA", "BBB", "CCC"], batch_size=3))

    assert set(observations) == {"AAA", "BBB", "CCC"}
