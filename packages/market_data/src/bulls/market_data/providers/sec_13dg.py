"""Schedule 13D/13G dissemination parser (header-first, honestly partial).

The reliable, structured part of a 13D/G dissemination ``.txt`` is its SGML header:
form type, acceptance datetime (the point-in-time signal anchor), subject company and
filed-by identities. That is what the filings-event stream needs — the *event* is the
signal (institutional study, Phase 8).

Percent-of-class is scraped from the cover page on a best-effort basis only; formats
vary wildly across filers and a ``None`` is a valid answer, never a guess. Full Item
parsing (intent, funding, derivatives in Item 6) is out of scope here — the raw bytes
are archived verbatim, so deeper parsing can be added later and replayed historically.
"""

from __future__ import annotations

import datetime as dt
import re

from pydantic import BaseModel

# EDGAR's CONFORMED SUBMISSION TYPE switched from "SC 13D"/"SC 13G" to "SCHEDULE
# 13D"/"SCHEDULE 13G" around the 2024/2025 year-end (confirmed live, including
# amendments -- e.g. accession 0000950170-25-022263 is header-labeled "SCHEDULE
# 13D/A"). Both eras' spellings are kept so historical and current filings both parse.
_FORMS = {
    "SC 13D",
    "SC 13D/A",
    "SC 13G",
    "SC 13G/A",
    "SCHEDULE 13D",
    "SCHEDULE 13D/A",
    "SCHEDULE 13G",
    "SCHEDULE 13G/A",
}

_ACCESSION_RE = re.compile(r"^ACCESSION NUMBER:\s*(\S+)", re.MULTILINE)
_TYPE_RE = re.compile(r"^CONFORMED SUBMISSION TYPE:\s*(.+?)\s*$", re.MULTILINE)
_FILED_DATE_RE = re.compile(r"^FILED AS OF DATE:\s*(\d{8})", re.MULTILINE)
_ACCEPTED_RE = re.compile(r"<ACCEPTANCE-DATETIME>(\d{14})")
_PERCENT_RE = re.compile(
    r"PERCENT OF CLASS REPRESENTED BY AMOUNT IN ROW[^%]*?([0-9]{1,2}(?:\.[0-9]+)?)\s*%",
    re.IGNORECASE | re.DOTALL,
)


class Schedule13DG(BaseModel):
    accession_number: str
    form: str
    filed_date: dt.date | None
    accepted_at: dt.datetime | None
    subject_name: str
    subject_cik: int
    filed_by_name: str | None
    filed_by_cik: int | None
    percent_of_class: float | None


def _section(text: str, heading: str) -> str | None:
    """Return the indented block following a ``HEADING:`` line in the SGML header."""
    start = text.find(f"{heading}:")
    if start < 0:
        return None
    tail = text[start + len(heading) + 1 :]
    lines = []
    for line in tail.splitlines()[1:]:
        # Section ends at the next top-level (unindented) heading.
        if line and line[0] not in " \t":
            break
        lines.append(line)
    return "\n".join(lines)


def _company(block: str | None) -> tuple[str | None, int | None]:
    if block is None:
        return None, None
    name_match = re.search(r"COMPANY CONFORMED NAME:\s*(.+?)\s*$", block, re.MULTILINE)
    cik_match = re.search(r"CENTRAL INDEX KEY:\s*(\d+)", block)
    name = name_match.group(1).strip() if name_match else None
    cik = int(cik_match.group(1)) if cik_match else None
    return name or None, cik


def parse_13dg(raw: bytes) -> Schedule13DG | None:
    """Parse a 13D/G dissemination file. ``None`` = not a usable 13D/G event."""
    text = raw.decode("latin-1", errors="replace")

    type_match = _TYPE_RE.search(text)
    if type_match is None or type_match.group(1).strip().upper() not in _FORMS:
        return None
    accession_match = _ACCESSION_RE.search(text)
    if accession_match is None:
        return None

    subject_name, subject_cik = _company(_section(text, "SUBJECT COMPANY"))
    if subject_name is None or subject_cik is None:
        # A 13D without an identifiable subject is useless as an event: refuse loudly.
        return None
    filed_by_name, filed_by_cik = _company(_section(text, "FILED BY"))

    filed_date = None
    if date_match := _FILED_DATE_RE.search(text):
        try:
            filed_date = dt.datetime.strptime(date_match.group(1), "%Y%m%d").date()
        except ValueError:
            filed_date = None

    accepted_at = None
    if accepted_match := _ACCEPTED_RE.search(text):
        try:
            accepted_at = dt.datetime.strptime(accepted_match.group(1), "%Y%m%d%H%M%S").replace(
                tzinfo=dt.UTC
            )
        except ValueError:
            accepted_at = None

    percent = None
    if percent_match := _PERCENT_RE.search(text):
        percent = float(percent_match.group(1))

    return Schedule13DG(
        accession_number=accession_match.group(1),
        form=type_match.group(1).strip().upper(),
        filed_date=filed_date,
        accepted_at=accepted_at,
        subject_name=subject_name,
        subject_cik=subject_cik,
        filed_by_name=filed_by_name,
        filed_by_cik=filed_by_cik,
        percent_of_class=percent,
    )
