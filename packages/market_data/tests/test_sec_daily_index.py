"""Tests for the EDGAR daily-index provider (market-wide filing event stream)."""

from __future__ import annotations

import datetime as dt

import httpx
import pytest

from bulls.market_data.providers.sec_daily_index import (
    DailyIndexEntry,
    SecDailyIndexClient,
    accession_from_filename,
    parse_acceptance_datetime,
    parse_master_index,
)

# Verbatim shape of an EDGAR master.<date>.idx: an 11-line preamble, a dashed
# separator, then pipe-delimited rows CIK|Company Name|Form Type|Date Filed|Filename.
_MASTER_IDX = """Description:           Master Index of EDGAR Dissemination Feed by Company Name
Last Data Received:    July 17, 2026
Comments:              webmaster@sec.gov
Anonymous FTP:         ftp://ftp.sec.gov/edgar/





CIK|Company Name|Form Type|Date Filed|Filename
--------------------------------------------------------------------------------
1045810|NVIDIA CORP|4|2026-07-17|edgar/data/1045810/0001045810-26-000123.txt
1067983|BERKSHIRE HATHAWAY INC|SC 13D/A|2026-07-17|edgar/data/1067983/0001067983-26-000045.txt
320193|Apple Inc.|10-Q|2026-07-17|edgar/data/320193/0000320193-26-000077.txt
902012|ELLIOTT INVESTMENT MANAGEMENT L.P.|SC 13D|2026-07-17|edgar/data/902012/0000902012-26-000011.txt
"""


def test_parse_master_index_extracts_rows() -> None:
    entries = parse_master_index(_MASTER_IDX)
    assert len(entries) == 4
    first = entries[0]
    assert isinstance(first, DailyIndexEntry)
    assert first.cik == 1045810
    assert first.company == "NVIDIA CORP"
    assert first.form == "4"
    assert first.date_filed == dt.date(2026, 7, 17)
    assert first.filename == "edgar/data/1045810/0001045810-26-000123.txt"
    assert first.accession_number == "0001045810-26-000123"


def test_parse_master_index_filters_forms() -> None:
    entries = parse_master_index(_MASTER_IDX, forms={"SC 13D", "SC 13D/A"})
    assert [e.form for e in entries] == ["SC 13D/A", "SC 13D"]
    assert {e.company for e in entries} == {
        "BERKSHIRE HATHAWAY INC",
        "ELLIOTT INVESTMENT MANAGEMENT L.P.",
    }


def test_parse_master_index_tolerates_malformed_rows() -> None:
    # A short row and a bad date must be skipped, never raise: the poller runs unattended.
    text = _MASTER_IDX + "9999|BROKEN ROW\n123|X CORP|4|not-a-date|edgar/data/123/foo.txt\n"
    entries = parse_master_index(text)
    assert len(entries) == 4


def test_accession_from_filename() -> None:
    assert (
        accession_from_filename("edgar/data/1067983/0001067983-26-000045.txt")
        == "0001067983-26-000045"
    )
    assert accession_from_filename("edgar/data/1/garbage") is None


def _transport(payloads: dict[str, str | bytes]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        for suffix, body in payloads.items():
            if path.endswith(suffix):
                content = body.encode() if isinstance(body, str) else body
                return httpx.Response(200, content=content)
        return httpx.Response(404)

    return httpx.MockTransport(handler)


def test_client_requires_identifying_user_agent() -> None:
    with pytest.raises(ValueError):
        SecDailyIndexClient(user_agent="Mozilla/5.0")


async def test_fetch_day_returns_entries_and_raw_bytes() -> None:
    client = SecDailyIndexClient(
        user_agent="BullsOfTheWorld/0.1 hello@bullsofwallst.com",
        transport=_transport({"master.20260717.idx": _MASTER_IDX}),
    )
    raw, entries = await client.fetch_day(dt.date(2026, 7, 17))
    # Raw bytes are returned untouched so the caller can archive them content-addressed;
    # replay-from-archive must be byte-identical to the original fetch.
    assert raw == _MASTER_IDX.encode()
    assert len(entries) == 4


async def test_fetch_day_missing_index_returns_empty() -> None:
    # Weekends/holidays have no index file; that is a normal empty day, not an error.
    client = SecDailyIndexClient(
        user_agent="BullsOfTheWorld/0.1 hello@bullsofwallst.com",
        transport=_transport({}),
    )
    raw, entries = await client.fetch_day(dt.date(2026, 7, 19))
    assert raw is None
    assert entries == []


async def test_fetch_day_treats_403_as_missing_index() -> None:
    # Verified live against real EDGAR: a missing daily-index path (weekend or
    # holiday) answers 403, not 404. A well-identified client must not treat that
    # as an error, or every Saturday/Sunday raises in the daily cron.
    transport = httpx.MockTransport(lambda request: httpx.Response(403))
    client = SecDailyIndexClient(
        user_agent="BullsOfTheWorld/0.1 hello@bullsofwallst.com",
        transport=transport,
    )
    raw, entries = await client.fetch_day(dt.date(2026, 7, 4))
    assert raw is None
    assert entries == []


async def test_fetch_filing_returns_raw_document() -> None:
    body = b"<SEC-DOCUMENT>raw filing bytes</SEC-DOCUMENT>"
    client = SecDailyIndexClient(
        user_agent="BullsOfTheWorld/0.1 hello@bullsofwallst.com",
        transport=_transport({"0001067983-26-000045.txt": body}),
    )
    raw = await client.fetch_filing("edgar/data/1067983/0001067983-26-000045.txt")
    assert raw == body


def test_quarter_path() -> None:
    client = SecDailyIndexClient(user_agent="BullsOfTheWorld/0.1 hello@bullsofwallst.com")
    assert client.index_path(dt.date(2026, 7, 17)).endswith(
        "daily-index/2026/QTR3/master.20260717.idx"
    )
    assert client.index_path(dt.date(2026, 2, 2)).endswith(
        "daily-index/2026/QTR1/master.20260202.idx"
    )


def test_parse_acceptance_datetime_is_form_agnostic() -> None:
    # Every dissemination file carries this header, Form 4 included — it is the point-in-time
    # anchor signals are stamped with, so it must not be read only on the 13D/G path.
    raw = b"<SEC-DOCUMENT>x\n<ACCEPTANCE-DATETIME>20260717163045\nCONFORMED SUBMISSION TYPE:\t4\n"
    assert parse_acceptance_datetime(raw) == dt.datetime(2026, 7, 17, 16, 30, 45, tzinfo=dt.UTC)


def test_parse_acceptance_datetime_returns_none_rather_than_guessing() -> None:
    assert parse_acceptance_datetime(b"no header here") is None
    assert parse_acceptance_datetime(b"<ACCEPTANCE-DATETIME>20261352999999") is None
