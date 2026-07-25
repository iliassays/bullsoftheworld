"""Form 4 (Section 16 ownershipDocument) parser.

Parses the structured XML that insiders have filed electronically since 2003, including
the Rule 10b5-1 plan checkbox added by the 2022-23 amendments. Non-derivative
transactions are parsed in full (the open-market P/S signal lives there); derivative
rows are only counted, and their presence is flagged so downstream consumers never
mistake the parsed share counts for the whole filing.

Accepts either the bare ownershipDocument XML or the full SGML dissemination ``.txt``
(the byte-exact artifact the daily-index poller archives).

Filers hand-type transaction dates, so a minority are typos that are still valid ISO dates
(``0022-10-12`` for ``2022-10-12``). ``dt.date.fromisoformat`` accepts those happily, which is
how 32 rows with years between 0022 and 2033 reached production. Dates below
``EARLIEST_PLAUSIBLE_TRANSACTION_DATE`` are therefore dropped to ``None`` rather than repaired:
the digits a filer *meant* are a guess, and a null date is an honest "we do not know when".
The upper bound needs the filing date, which lives in the daily index, so the poller enforces
it (see ``ingestion.edgar_events.parse_filing``).
"""

from __future__ import annotations

import datetime as dt
import re
import xml.etree.ElementTree as ET

from pydantic import BaseModel

_XML_RE = re.compile(rb"<\?xml[^>]*\?>\s*<ownershipDocument>.*?</ownershipDocument>", re.DOTALL)
_BARE_RE = re.compile(rb"<ownershipDocument>.*?</ownershipDocument>", re.DOTALL)
# A leading ISO calendar date, so a trailing timezone offset ("-05:00", "+06:00", "Z") can be
# dropped. Anchored and length-bounded so it cannot rescue a genuinely malformed value.
_DATE_PREFIX_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})(?:[Tt ].*)?(?:Z|z|[+-]\d{2}:?\d{2})?$")

# Section 16 went electronic in 2003 and amendments may restate older trades, so this floor is
# set far below any real filing: it exists only to catch mistyped year digits, never to trim
# genuine history.
EARLIEST_PLAUSIBLE_TRANSACTION_DATE = dt.date(1990, 1, 1)


class Form4Owner(BaseModel):
    cik: int
    name: str
    is_director: bool = False
    is_officer: bool = False
    is_ten_percent_owner: bool = False
    officer_title: str | None = None


class Form4Transaction(BaseModel):
    security_title: str | None = None
    transaction_date: dt.date | None = None
    code: str | None = None
    shares: float | None = None
    price_per_share: float | None = None
    acquired_disposed: str | None = None
    shares_owned_after: float | None = None
    direct_or_indirect: str | None = None


class Form4Filing(BaseModel):
    issuer_cik: int
    issuer_name: str | None = None
    issuer_symbol: str | None = None
    period_of_report: dt.date | None = None
    is_10b5_1_plan: bool = False
    owners: list[Form4Owner]
    transactions: list[Form4Transaction]
    has_derivative_transactions: bool = False
    # Rows that carried a transaction date we could not use (unparseable, or below the floor).
    # Their ``transaction_date`` is None; the count is kept so the rate stays observable.
    implausible_transaction_dates: int = 0


def extract_ownership_xml(raw: bytes) -> str | None:
    """Pull the ownershipDocument XML out of an SGML dissemination file, verbatim."""
    match = _XML_RE.search(raw) or _BARE_RE.search(raw)
    return match.group(0).decode("utf-8", errors="replace") if match else None


def _text(node: ET.Element | None, path: str) -> str | None:
    if node is None:
        return None
    found = node.find(path)
    if found is None or found.text is None:
        return None
    value = found.text.strip()
    return value or None


def _value(node: ET.Element | None, path: str) -> str | None:
    # Most Form 4 fields nest the payload one level down in a <value> element.
    return _text(node, f"{path}/value")


def _flag(node: ET.Element | None, path: str) -> bool:
    return (_text(node, path) or "").strip() in {"1", "true", "TRUE"}


def _number(raw: str | None) -> float | None:
    if raw is None:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _date(raw: str | None) -> dt.date | None:
    """Parse a Form 4 date, tolerating the timezone offset some filing agents append.

    A minority of agents emit ``2024-01-23-05:00`` — a date carrying a UTC offset.
    ``dt.date.fromisoformat`` rejects that outright, which silently dropped ~2,500 otherwise
    perfectly good transaction dates in production (0.15% of rows, all with real transaction
    codes and share counts). The calendar date is unambiguous, so the offset is stripped rather
    than treated as corruption. A genuinely mistyped year still fails the floor below.
    """
    if raw is None:
        return None
    candidates = [raw]
    match = _DATE_PREFIX_RE.match(raw)
    if match is not None:
        candidates.append(match.group(1))
    for candidate in candidates:
        try:
            parsed = dt.date.fromisoformat(candidate)
        except ValueError:
            continue
        return None if parsed < EARLIEST_PLAUSIBLE_TRANSACTION_DATE else parsed
    return None


def parse_form4(document: str | bytes) -> Form4Filing | None:
    """Parse a Form 4. Returns ``None`` on malformed input — the poller records the
    accession as parse-failed and moves on; one bad filing must not block the stream."""
    raw = document.encode() if isinstance(document, str) else document
    xml = extract_ownership_xml(raw)
    if xml is None:
        return None
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return None

    issuer = root.find("issuer")
    issuer_cik = _text(issuer, "issuerCik")
    if issuer_cik is None:
        return None

    owners = []
    for owner in root.findall("reportingOwner"):
        owner_id = owner.find("reportingOwnerId")
        cik = _text(owner_id, "rptOwnerCik")
        if cik is None:
            continue
        relationship = owner.find("reportingOwnerRelationship")
        owners.append(
            Form4Owner(
                cik=int(cik),
                name=_text(owner_id, "rptOwnerName") or "",
                is_director=_flag(relationship, "isDirector"),
                is_officer=_flag(relationship, "isOfficer"),
                is_ten_percent_owner=_flag(relationship, "isTenPercentOwner"),
                officer_title=_text(relationship, "officerTitle"),
            )
        )

    transactions = []
    implausible_dates = 0
    for txn in root.findall("nonDerivativeTable/nonDerivativeTransaction"):
        amounts = txn.find("transactionAmounts")
        raw_date = _value(txn, "transactionDate")
        transaction_date = _date(raw_date)
        if raw_date is not None and transaction_date is None:
            implausible_dates += 1
        transactions.append(
            Form4Transaction(
                security_title=_value(txn, "securityTitle"),
                transaction_date=transaction_date,
                code=_text(txn, "transactionCoding/transactionCode"),
                shares=_number(_value(amounts, "transactionShares")),
                price_per_share=_number(_value(amounts, "transactionPricePerShare")),
                acquired_disposed=_value(amounts, "transactionAcquiredDisposedCode"),
                shares_owned_after=_number(
                    _value(txn.find("postTransactionAmounts"), "sharesOwnedFollowingTransaction")
                ),
                direct_or_indirect=_value(txn.find("ownershipNature"), "directOrIndirectOwnership"),
            )
        )

    return Form4Filing(
        issuer_cik=int(issuer_cik),
        issuer_name=_text(issuer, "issuerName"),
        issuer_symbol=_text(issuer, "issuerTradingSymbol"),
        period_of_report=_date(_text(root, "periodOfReport")),
        is_10b5_1_plan=_flag(root, "aff10b5One"),
        owners=owners,
        transactions=transactions,
        has_derivative_transactions=root.find("derivativeTable/derivativeTransaction") is not None,
        implausible_transaction_dates=implausible_dates,
    )
