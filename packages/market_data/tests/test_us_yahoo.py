from __future__ import annotations

import datetime as dt

from bulls.market_data.providers.us_yahoo import parse_yahoo_chart, yahoo_symbol


def test_yahoo_symbol_maps_public_share_class_codes() -> None:
    assert yahoo_symbol("brk.b") == "BRK-B"
    assert yahoo_symbol("AAPL") == "AAPL"


def test_parse_yahoo_chart_builds_daily_bars_and_skips_bad_rows() -> None:
    payload = {
        "chart": {
            "result": [
                {
                    "timestamp": [1704177000, 1704263400, 1704349800],
                    "indicators": {
                        "adjclose": [{"adjclose": [93.5, None, 185.0]}],
                        "quote": [
                            {
                                "open": [185.0, None, 187.0],
                                "high": [188.0, None, 186.0],
                                "low": [184.0, None, 188.0],
                                "close": [187.0, None, 185.0],
                                "volume": [1000, None, 2000],
                            }
                        ]
                    },
                }
            ],
            "error": None,
        }
    }

    bars = parse_yahoo_chart(payload, market="US", code="AAPL")

    assert len(bars) == 1
    assert bars[0].market == "US"
    assert bars[0].code == "AAPL"
    assert bars[0].date == dt.date(2024, 1, 2)
    assert bars[0].close == 187.0
    assert bars[0].adjusted_close == 93.5
    assert bars[0].source == "yahoo_chart"
    assert bars[0].volume == 1000


def test_parse_yahoo_chart_returns_empty_on_provider_error() -> None:
    assert parse_yahoo_chart({"chart": {"result": None, "error": {"code": "Not Found"}}}, market="US", code="NOPE") == []
