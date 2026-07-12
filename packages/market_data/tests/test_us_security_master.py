"""US security-master parsing is deliberately offline-testable.

The live Nasdaq/SEC files are large and change daily. These fixtures lock the semantics we care
about: test issues, ETFs, common stocks, ADRs, warrants, units, preferreds, and CIK enrichment.
"""

from __future__ import annotations

from bulls.market_data.providers.us_security_master import (
    classify_instrument,
    enrich_with_sec_ciks,
    parse_nasdaq_listed,
    parse_other_listed,
    parse_sec_tickers_exchange,
)


def test_coupon_series_name_is_classified_as_preferred_not_common() -> None:
    assert (
        classify_instrument(
            "DigitalBridge Group, Inc. 7.125% Series H",
            is_etf=False,
            assume_common=True,
        )
        == "preferred_stock"
    )
    assert (
        classify_instrument("Example Inc. Series A Common Stock", is_etf=False)
        == "common_stock"
    )

NASDAQ_LISTED = """Symbol|Security Name|Market Category|Test Issue|Financial Status|Round Lot Size|ETF|NextShares
AAPL|Apple Inc. - Common Stock|Q|N|N|40|N|N
GOOG|Alphabet Inc. - Class C Capital Stock|Q|N|N|100|N|N
ASML|ASML Holding N.V. - New York Registry Shares|Q|N|N|100|N|N
AAPU|Direxion Daily AAPL Bull 2X ETF|G|N|N|100|Y|N
AACIW|Armada Acquisition Corp. III - Warrant|G|N|N|100|N|N
BADF|Deficient Issuer - Common Stock|S|N|D|100|N|N
TEST|Nasdaq Test Company - Common Stock|S|Y|N|100|N|N
File Creation Time: 0709202618:04
"""

OTHER_LISTED = """ACT Symbol|Security Name|Exchange|CQS Symbol|ETF|Round Lot Size|Test Issue|NASDAQ Symbol
BRK.B|Berkshire Hathaway Inc. Class B Common Stock|N|BRK.B|N|100|N|BRK-B
BABA|Alibaba Group Holding Limited American Depositary Shares|N|BABA|N|100|N|BABA
V|Visa Inc.|N|V|N|100|N|V
ABR$D|Arbor Realty Trust 6.375% Series D Cumulative Redeemable Preferred Stock|N|ABRpD|N|100|N|ABR-D
EQH-A|Equitable Holdings, Inc. Depositary Shares|N|EQH-A|N|100|N|EQH-A
FITB-I|Fifth Third Bancorp Depositary Share repstg 1/1000th Ownership Interest Perp Pfd Series I|N|FITB-I|N|100|N|FITB-I
AAA|Alternative Access First Priority CLO Bond ETF|P|AAA|Y|100|N|AAA
AAC.U|Ares Acquisition Corporation III Units|N|AAC.U|N|100|N|AAC=
"""


def test_parse_nasdaq_listed_classifies_and_filters_product_universe() -> None:
    records = {r.symbol: r for r in parse_nasdaq_listed(NASDAQ_LISTED)}

    assert records["AAPL"].instrument_type == "common_stock"
    assert records["AAPL"].is_product_eligible
    assert records["AAPL"].round_lot_size == 40
    assert records["AAPL"].exchange == "Nasdaq"
    assert records["AAPL"].exchange_tier == "Nasdaq Global Select Market"

    assert records["AAPU"].instrument_type == "etf"
    assert records["AAPU"].is_product_eligible

    assert records["GOOG"].instrument_type == "common_stock"
    assert records["GOOG"].is_product_eligible

    assert records["ASML"].instrument_type == "adr"
    assert records["ASML"].is_product_eligible

    assert records["AACIW"].instrument_type == "warrant"
    assert not records["AACIW"].is_product_eligible
    assert records["AACIW"].exclude_reason == "warrant"

    assert records["BADF"].instrument_type == "common_stock"
    assert not records["BADF"].is_product_eligible
    assert records["BADF"].exclude_reason == "financial_status_d"

    assert records["TEST"].is_test_issue
    assert not records["TEST"].is_product_eligible
    assert records["TEST"].exclude_reason == "test_issue"


def test_parse_other_listed_normalizes_symbols_and_keeps_raw_symbol() -> None:
    records = {r.symbol: r for r in parse_other_listed(OTHER_LISTED)}

    assert records["BRK-B"].raw_symbol == "BRK.B"
    assert records["BRK-B"].instrument_type == "common_stock"
    assert records["BRK-B"].exchange == "NYSE"
    assert records["BRK-B"].is_product_eligible

    assert records["BABA"].instrument_type == "adr"
    assert records["BABA"].is_product_eligible

    assert records["V"].instrument_type == "common_stock"
    assert records["V"].is_product_eligible

    assert records["ABR-D"].instrument_type == "preferred_stock"
    assert not records["ABR-D"].is_product_eligible
    assert records["ABR-D"].exclude_reason == "preferred_stock"

    assert records["EQH-A"].instrument_type == "preferred_stock"
    assert not records["EQH-A"].is_product_eligible
    assert records["EQH-A"].exclude_reason == "preferred_stock"

    assert records["FITB-I"].instrument_type == "preferred_stock"
    assert not records["FITB-I"].is_product_eligible
    assert records["FITB-I"].exclude_reason == "preferred_stock"

    assert records["AAA"].instrument_type == "etf"
    assert records["AAA"].exchange == "NYSE Arca"
    assert records["AAA"].is_product_eligible

    assert records["AAC="].instrument_type == "unit"
    assert records["AAC="].raw_symbol == "AAC.U"
    assert not records["AAC="].is_product_eligible


def test_sec_ticker_exchange_enrichment_adds_cik_by_normalized_symbol() -> None:
    sec = parse_sec_tickers_exchange(
        {
            "fields": ["cik", "name", "ticker", "exchange"],
            "data": [
                [320193, "Apple Inc.", "AAPL", "Nasdaq"],
                [1067983, "BERKSHIRE HATHAWAY INC", "BRK-B", "NYSE"],
            ],
        }
    )
    records = parse_nasdaq_listed(NASDAQ_LISTED) + parse_other_listed(OTHER_LISTED)
    enriched = {r.symbol: r for r in enrich_with_sec_ciks(records, sec)}

    assert enriched["AAPL"].cik == 320193
    assert enriched["BRK-B"].cik == 1067983
    assert enriched["AAPU"].cik is None
