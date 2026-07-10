"""US security-master publish rules.

These tests stay DB-free: the important contract is that raw noisy instruments remain in the
security master while only product-eligible securities are projected into `symbols`.
"""

from __future__ import annotations

from bulls.market_data.providers.us_security_master import parse_nasdaq_listed, parse_other_listed
from ingestion.security_master import _chunks, _symbol_rows


def test_symbol_rows_publish_only_product_eligible_instruments() -> None:
    records = parse_nasdaq_listed(
        """Symbol|Security Name|Market Category|Test Issue|Financial Status|Round Lot Size|ETF|NextShares
AAPL|Apple Inc. - Common Stock|Q|N|N|40|N|N
AACIW|Armada Acquisition Corp. III - Warrant|G|N|N|100|N|N
TEST|Nasdaq Test Company - Common Stock|S|Y|N|100|N|N
"""
    ) + parse_other_listed(
        """ACT Symbol|Security Name|Exchange|CQS Symbol|ETF|Round Lot Size|Test Issue|NASDAQ Symbol
BRK.B|Berkshire Hathaway Inc. Class B Common Stock|N|BRK.B|N|100|N|BRK-B
ABR$D|Arbor Realty Trust Preferred Stock|N|ABRpD|N|100|N|ABR-D
"""
    )

    rows = _symbol_rows(records)

    assert [row["code"] for row in rows] == ["AAPL", "BRK-B"]
    assert all(row["market"] == "US" for row in rows)
    assert all(row["is_active"] is True for row in rows)
    assert all(row["is_hidden"] is False for row in rows)


def test_symbol_rows_preserve_long_official_names() -> None:
    long_name = "Example Holdings " + "International " * 12 + "Common Stock"
    records = parse_nasdaq_listed(
        "Symbol|Security Name|Market Category|Test Issue|Financial Status|Round Lot Size|ETF|NextShares\n"
        f"LONG|{long_name}|Q|N|N|100|N|N\n"
    )

    [row] = _symbol_rows(records)

    assert len(long_name) > 160
    assert row["name_en"] == long_name


def test_bulk_rows_are_chunked_before_upsert() -> None:
    rows = list(range(2501))

    chunks = _chunks(rows, size=1000)

    assert [len(chunk) for chunk in chunks] == [1000, 1000, 501]
    assert chunks[0][0] == 0
    assert chunks[-1][-1] == 2500
