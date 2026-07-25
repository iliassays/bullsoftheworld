"""Tests for the EDGAR filing-event poller: routing, dedupe, and byte-identical replay."""

from __future__ import annotations

import datetime as dt

from bulls.market_data.providers.sec_daily_index import DailyIndexEntry
from ingestion.edgar_events import (
    TARGET_FORMS,
    filing_object_key,
    index_object_key,
    parse_filing,
    plan_new_entries,
    replay_day_index,
    replay_filing,
)
from ingestion.us_options.storage import LocalImmutableObjectStore

_FORM4_XML = """<?xml version="1.0"?>
<ownershipDocument>
    <issuer><issuerCik>0001045810</issuerCik><issuerTradingSymbol>NVDA</issuerTradingSymbol></issuer>
    <reportingOwner>
        <reportingOwnerId><rptOwnerCik>0000777001</rptOwnerCik><rptOwnerName>DOE JANE</rptOwnerName></reportingOwnerId>
        <reportingOwnerRelationship><isOfficer>1</isOfficer></reportingOwnerRelationship>
    </reportingOwner>
    <nonDerivativeTable>
        <nonDerivativeTransaction>
            <transactionDate><value>2026-07-17</value></transactionDate>
            <transactionCoding><transactionCode>P</transactionCode></transactionCoding>
            <transactionAmounts>
                <transactionShares><value>100</value></transactionShares>
                <transactionPricePerShare><value>10.5</value></transactionPricePerShare>
            </transactionAmounts>
        </nonDerivativeTransaction>
    </nonDerivativeTable>
</ownershipDocument>
"""

_13D_TXT = """<SEC-DOCUMENT>x
<SEC-HEADER>x
<ACCEPTANCE-DATETIME>20260717163045
ACCESSION NUMBER:\t0000902012-26-000011
CONFORMED SUBMISSION TYPE:\tSC 13D
FILED AS OF DATE:\t20260717
SUBJECT COMPANY:\t
\tCOMPANY DATA:\t
\t\tCOMPANY CONFORMED NAME:\t\tTARGET INDUSTRIES INC
\t\tCENTRAL INDEX KEY:\t\t0000123456
FILED BY:\t
\tCOMPANY DATA:\t
\t\tCOMPANY CONFORMED NAME:\t\tELLIOTT INVESTMENT MANAGEMENT L.P.
\t\tCENTRAL INDEX KEY:\t\t0000902012
</SEC-HEADER>
</SEC-DOCUMENT>
"""


def _entry(form: str, accession: str, cik: int = 1) -> DailyIndexEntry:
    return DailyIndexEntry(
        cik=cik,
        company="X CORP",
        form=form,
        date_filed=dt.date(2026, 7, 17),
        filename=f"edgar/data/{cik}/{accession}.txt",
    )


def test_plan_new_entries_filters_forms_and_dedupes() -> None:
    entries = [
        _entry("4", "0000000001-26-000001"),
        _entry("10-K", "0000000001-26-000002"),  # not a target form
        _entry("SC 13D", "0000000001-26-000003", cik=10),  # issuer's index row
        _entry("SC 13D", "0000000001-26-000003", cik=20),  # same filing, filer's index row
    ]
    planned = plan_new_entries(entries, existing={"0000000001-26-000001"})
    # The already-captured Form 4 is skipped; the 13D's second index row (same
    # accession, different filer CIK) is deduped within the batch, not just against
    # already-committed accessions — else the filing gets fetched from SEC twice.
    assert [(e.form, e.accession_number) for e in planned] == [("SC 13D", "0000000001-26-000003")]
    assert all(e.form in TARGET_FORMS for e in planned)


def test_parse_filing_routes_form4() -> None:
    outcome = parse_filing(_entry("4", "0000000001-26-000001"), _FORM4_XML.encode())
    assert outcome.parse_status == "parsed"
    assert outcome.stake_row is None
    assert len(outcome.insider_rows) == 1
    row = outcome.insider_rows[0]
    assert row["code"] == "P"
    assert row["issuer_cik"] == 1045810
    assert row["owner_cik"] == 777001
    assert row["accession_number"] == "0000000001-26-000001"


def test_parse_filing_routes_13d() -> None:
    outcome = parse_filing(_entry("SC 13D", "0000902012-26-000011"), _13D_TXT.encode())
    assert outcome.parse_status == "parsed"
    assert outcome.insider_rows == []
    assert outcome.stake_row is not None
    assert outcome.stake_row["subject_cik"] == 123456
    assert outcome.stake_row["filed_by_cik"] == 902012


def test_parse_filing_nulls_transaction_date_after_the_filing_date() -> None:
    """Section 16 allows two business days, so a trade cannot postdate its own filing.

    Production held dates out to 2033 from exactly this class of filer typo.
    """
    xml = _FORM4_XML.replace("2026-07-17", "2033-12-11")
    outcome = parse_filing(_entry("4", "0000000001-26-000010"), xml.encode())

    assert outcome.parse_status == "parsed"
    # The date is dropped; the rest of the row is filed fact and survives.
    assert outcome.insider_rows[0]["transaction_date"] is None
    assert outcome.insider_rows[0]["shares"] == 100
    assert outcome.implausible_dates == 1


def test_parse_filing_nulls_mistyped_year_below_the_floor() -> None:
    """``0022-10-12`` is valid ISO and was accepted until the floor existed."""
    xml = _FORM4_XML.replace("2026-07-17", "0022-10-12")
    outcome = parse_filing(_entry("4", "0000000001-26-000011"), xml.encode())

    assert outcome.parse_status == "parsed"
    assert outcome.insider_rows[0]["transaction_date"] is None
    assert outcome.implausible_dates == 1


def test_parse_filing_keeps_a_transaction_dated_one_day_after_filing() -> None:
    """Timezone skew between a filer's local date and EDGAR's index date is tolerated."""
    xml = _FORM4_XML.replace("2026-07-17", "2026-07-18")
    outcome = parse_filing(_entry("4", "0000000001-26-000012"), xml.encode())

    assert outcome.insider_rows[0]["transaction_date"] == dt.date(2026, 7, 18)
    assert outcome.implausible_dates == 0


def test_parse_filing_failure_is_soft() -> None:
    outcome = parse_filing(_entry("4", "0000000001-26-000009"), b"garbage")
    assert outcome.parse_status == "failed"
    assert outcome.insider_rows == []
    assert outcome.stake_row is None


def test_archive_replay_is_byte_identical(tmp_path) -> None:
    """Stage 0.1 exit test: what we archived is exactly what we fetched."""
    store = LocalImmutableObjectStore(tmp_path)
    day = dt.date(2026, 7, 17)
    index_bytes = b"CIK|Company Name|Form Type|Date Filed|Filename\n----\n1|X|4|2026-07-17|f.txt\n"
    filing_bytes = _13D_TXT.encode()

    store.put(key=index_object_key(day), payload=index_bytes, content_type="text/plain")
    stored = store.put(
        key=filing_object_key("0000902012-26-000011"),
        payload=filing_bytes,
        content_type="text/plain",
    )

    assert replay_day_index(day, store=store) == index_bytes
    assert replay_filing("0000902012-26-000011", store=store) == filing_bytes
    # Content addressing: the recorded sha256 must re-verify against the replayed bytes.
    import hashlib

    assert hashlib.sha256(replay_filing("0000902012-26-000011", store=store)).hexdigest() == (
        stored.sha256
    )


def test_object_keys_are_stable() -> None:
    # Keys are part of the archive contract; changing them breaks historical replay.
    assert index_object_key(dt.date(2026, 7, 17)) == "edgar/daily-index/2026/07/17/master.idx"
    assert filing_object_key("0000902012-26-000011") == "edgar/filings/0000902012-26-000011.txt"
