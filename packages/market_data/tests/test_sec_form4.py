"""Tests for the Form 4 (ownershipDocument) parser."""

from __future__ import annotations

import datetime as dt

from bulls.market_data.providers.sec_form4 import (
    Form4Filing,
    extract_ownership_xml,
    parse_form4,
)

_OWNERSHIP_XML = """<?xml version="1.0"?>
<ownershipDocument>
    <schemaVersion>X0508</schemaVersion>
    <documentType>4</documentType>
    <periodOfReport>2026-07-15</periodOfReport>
    <aff10b5One>1</aff10b5One>
    <issuer>
        <issuerCik>0001045810</issuerCik>
        <issuerName>NVIDIA CORP</issuerName>
        <issuerTradingSymbol>NVDA</issuerTradingSymbol>
    </issuer>
    <reportingOwner>
        <reportingOwnerId>
            <rptOwnerCik>0001234567</rptOwnerCik>
            <rptOwnerName>DOE JANE</rptOwnerName>
        </reportingOwnerId>
        <reportingOwnerRelationship>
            <isDirector>1</isDirector>
            <isOfficer>1</isOfficer>
            <officerTitle>Chief Financial Officer</officerTitle>
            <isTenPercentOwner>0</isTenPercentOwner>
        </reportingOwnerRelationship>
    </reportingOwner>
    <nonDerivativeTable>
        <nonDerivativeTransaction>
            <securityTitle><value>Common Stock</value></securityTitle>
            <transactionDate><value>2026-07-15</value></transactionDate>
            <transactionCoding>
                <transactionFormType>4</transactionFormType>
                <transactionCode>S</transactionCode>
                <equitySwapInvolved>0</equitySwapInvolved>
            </transactionCoding>
            <transactionAmounts>
                <transactionShares><value>1500</value></transactionShares>
                <transactionPricePerShare><value>120.55</value></transactionPricePerShare>
                <transactionAcquiredDisposedCode><value>D</value></transactionAcquiredDisposedCode>
            </transactionAmounts>
            <postTransactionAmounts>
                <sharesOwnedFollowingTransaction><value>98500</value></sharesOwnedFollowingTransaction>
            </postTransactionAmounts>
            <ownershipNature>
                <directOrIndirectOwnership><value>D</value></directOrIndirectOwnership>
            </ownershipNature>
        </nonDerivativeTransaction>
        <nonDerivativeTransaction>
            <securityTitle><value>Common Stock</value></securityTitle>
            <transactionDate><value>2026-07-16</value></transactionDate>
            <transactionCoding>
                <transactionFormType>4</transactionFormType>
                <transactionCode>P</transactionCode>
                <equitySwapInvolved>0</equitySwapInvolved>
            </transactionCoding>
            <transactionAmounts>
                <transactionShares><value>2000</value></transactionShares>
                <transactionPricePerShare><value>118.10</value></transactionPricePerShare>
                <transactionAcquiredDisposedCode><value>A</value></transactionAcquiredDisposedCode>
            </transactionAmounts>
            <postTransactionAmounts>
                <sharesOwnedFollowingTransaction><value>100500</value></sharesOwnedFollowingTransaction>
            </postTransactionAmounts>
            <ownershipNature>
                <directOrIndirectOwnership><value>I</value></directOrIndirectOwnership>
            </ownershipNature>
        </nonDerivativeTransaction>
    </nonDerivativeTable>
    <derivativeTable>
        <derivativeTransaction>
            <securityTitle><value>Stock Option</value></securityTitle>
        </derivativeTransaction>
    </derivativeTable>
</ownershipDocument>
"""

# The dissemination .txt wraps the XML in SGML; the parser must find it in situ.
_SGML_WRAPPED = (
    "<SEC-DOCUMENT>0001234567-26-000001.txt\n<SEC-HEADER>...</SEC-HEADER>\n"
    "<DOCUMENT>\n<TYPE>4\n<FILENAME>doc4.xml\n<TEXT>\n<XML>\n" + _OWNERSHIP_XML + "\n</XML>\n"
    "</TEXT>\n</DOCUMENT>\n</SEC-DOCUMENT>\n"
)


def test_extract_ownership_xml_from_sgml() -> None:
    xml = extract_ownership_xml(_SGML_WRAPPED.encode())
    assert xml is not None
    assert xml.lstrip().startswith("<?xml")
    assert "</ownershipDocument>" in xml


def test_extract_ownership_xml_missing_returns_none() -> None:
    assert extract_ownership_xml(b"<SEC-DOCUMENT>no xml here</SEC-DOCUMENT>") is None


def test_parse_form4_full_document() -> None:
    filing = parse_form4(_OWNERSHIP_XML)
    assert isinstance(filing, Form4Filing)
    assert filing.issuer_cik == 1045810
    assert filing.issuer_symbol == "NVDA"
    assert filing.period_of_report == dt.date(2026, 7, 15)
    # The post-2023 10b5-1 checkbox: the study's signal filter drops checked filings.
    assert filing.is_10b5_1_plan is True

    owner = filing.owners[0]
    assert owner.cik == 1234567
    assert owner.name == "DOE JANE"
    assert owner.is_director and owner.is_officer and not owner.is_ten_percent_owner
    assert owner.officer_title == "Chief Financial Officer"

    assert len(filing.transactions) == 2
    sale, purchase = filing.transactions
    assert sale.code == "S"
    assert sale.shares == 1500
    assert sale.price_per_share == 120.55
    assert sale.acquired_disposed == "D"
    assert sale.shares_owned_after == 98500
    assert sale.direct_or_indirect == "D"
    assert purchase.code == "P"
    assert purchase.transaction_date == dt.date(2026, 7, 16)
    assert purchase.acquired_disposed == "A"
    assert purchase.direct_or_indirect == "I"

    # Derivative rows are out of scope for the signal but their presence is recorded
    # honestly: share counts here never describe the whole filing when this flag is set.
    assert filing.has_derivative_transactions is True


def test_parse_form4_accepts_sgml_wrapped_bytes() -> None:
    filing = parse_form4(_SGML_WRAPPED)
    assert filing is not None
    assert len(filing.transactions) == 2


def test_parse_form4_malformed_returns_none() -> None:
    assert parse_form4("<ownershipDocument><unclosed>") is None
    assert parse_form4("not xml at all") is None


def test_parse_form4_without_10b51_checkbox_defaults_false() -> None:
    xml = _OWNERSHIP_XML.replace("<aff10b5One>1</aff10b5One>", "")
    filing = parse_form4(xml)
    assert filing is not None
    # Pre-2023 documents have no checkbox; absence means "not marked", never "unknown crash".
    assert filing.is_10b5_1_plan is False


def test_parse_form4_drops_mistyped_year_below_the_floor() -> None:
    """A dropped digit is still valid ISO-8601, which is how year 0022 reached production."""
    xml = _OWNERSHIP_XML.replace(
        "<transactionDate><value>2026-07-15</value></transactionDate>",
        "<transactionDate><value>0022-07-15</value></transactionDate>",
        1,
    )
    filing = parse_form4(xml)

    assert filing is not None
    # Nulled rather than corrected to 2022 — the intended digits are a guess.
    assert filing.transactions[0].transaction_date is None
    assert filing.implausible_transaction_dates == 1
    # Everything else on the row is filed fact and must survive.
    assert filing.transactions[0].code == "S"


def test_parse_form4_counts_no_implausible_dates_on_a_clean_filing() -> None:
    filing = parse_form4(_OWNERSHIP_XML)

    assert filing is not None
    assert filing.implausible_transaction_dates == 0
    assert filing.transactions[0].transaction_date == dt.date(2026, 7, 15)
