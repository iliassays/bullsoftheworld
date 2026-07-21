"""Tests for the Schedule 13D/13G dissemination-header parser."""

from __future__ import annotations

import datetime as dt

from bulls.market_data.providers.sec_13dg import Schedule13DG, parse_13dg

_FILING = """<SEC-DOCUMENT>0000902012-26-000011.txt : 20260717
<SEC-HEADER>0000902012-26-000011.hdr.sgml : 20260717
<ACCEPTANCE-DATETIME>20260717163045
ACCESSION NUMBER:\t\t0000902012-26-000011
CONFORMED SUBMISSION TYPE:\tSC 13D
PUBLIC DOCUMENT COUNT:\t\t2
FILED AS OF DATE:\t\t20260717

SUBJECT COMPANY:\t
\tCOMPANY DATA:\t
\t\tCOMPANY CONFORMED NAME:\t\t\tTARGET INDUSTRIES INC
\t\tCENTRAL INDEX KEY:\t\t\t0000123456
\t\tSTANDARD INDUSTRIAL CLASSIFICATION:\tSERVICES [7372]

FILED BY:\t\t
\tCOMPANY DATA:\t
\t\tCOMPANY CONFORMED NAME:\t\t\tELLIOTT INVESTMENT MANAGEMENT L.P.
\t\tCENTRAL INDEX KEY:\t\t\t0000902012
</SEC-HEADER>
<DOCUMENT>
<TYPE>SC 13D
<TEXT>
Item 13. PERCENT OF CLASS REPRESENTED BY AMOUNT IN ROW (11): 9.7%
Item 4. Purpose of Transaction ...
</TEXT>
</DOCUMENT>
</SEC-DOCUMENT>
"""


def test_parse_13dg_header_fields() -> None:
    filing = parse_13dg(_FILING.encode())
    assert isinstance(filing, Schedule13DG)
    assert filing.accession_number == "0000902012-26-000011"
    assert filing.form == "SC 13D"
    assert filing.filed_date == dt.date(2026, 7, 17)
    # Acceptance datetime is the point-in-time anchor: signal time for the event study.
    assert filing.accepted_at == dt.datetime(2026, 7, 17, 16, 30, 45, tzinfo=dt.UTC)
    assert filing.subject_name == "TARGET INDUSTRIES INC"
    assert filing.subject_cik == 123456
    assert filing.filed_by_name == "ELLIOTT INVESTMENT MANAGEMENT L.P."
    assert filing.filed_by_cik == 902012


def test_parse_13dg_percent_of_class_best_effort() -> None:
    filing = parse_13dg(_FILING.encode())
    assert filing is not None
    # Best-effort body scrape, honestly optional: cover-page formats vary wildly and a
    # None here is a valid answer, never a guess.
    assert filing.percent_of_class == 9.7


def test_parse_13dg_missing_percent_is_none() -> None:
    stripped = _FILING.replace(
        "Item 13. PERCENT OF CLASS REPRESENTED BY AMOUNT IN ROW (11): 9.7%", ""
    )
    filing = parse_13dg(stripped.encode())
    assert filing is not None
    assert filing.percent_of_class is None


def test_parse_13dg_rejects_non_13dg_documents() -> None:
    other = _FILING.replace("CONFORMED SUBMISSION TYPE:\tSC 13D", "CONFORMED SUBMISSION TYPE:\t10-K")
    assert parse_13dg(other.encode()) is None
    assert parse_13dg(b"not a filing") is None


def test_parse_13dg_missing_subject_returns_none() -> None:
    # A 13D without an identifiable subject company is useless as an event — refuse it
    # loudly (None -> parse_status failed) instead of emitting a half-row.
    broken = _FILING.replace("SUBJECT COMPANY:", "OTHER SECTION:")
    assert parse_13dg(broken.encode()) is None


def test_parse_13dg_accepts_post_2025_schedule_label() -> None:
    # EDGAR renamed CONFORMED SUBMISSION TYPE from "SC 13D"/"SC 13G" to "SCHEDULE
    # 13D"/"SCHEDULE 13G" (confirmed live, including "SCHEDULE 13D/A" amendments)
    # around 2024/2025 year-end. Both spellings must parse.
    renamed = _FILING.replace(
        "CONFORMED SUBMISSION TYPE:\tSC 13D", "CONFORMED SUBMISSION TYPE:\tSCHEDULE 13D/A"
    )
    filing = parse_13dg(renamed.encode())
    assert filing is not None
    assert filing.form == "SCHEDULE 13D/A"
