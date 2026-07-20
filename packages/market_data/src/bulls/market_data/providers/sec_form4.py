"""Form 4 (Section 16 ownershipDocument) parser.

Parses the structured XML that insiders have filed electronically since 2003, including
the Rule 10b5-1 plan checkbox added by the 2022-23 amendments. Non-derivative
transactions are parsed in full (the open-market P/S signal lives there); derivative
rows are only counted, and their presence is flagged so downstream consumers never
mistake the parsed share counts for the whole filing.

Accepts either the bare ownershipDocument XML or the full SGML dissemination ``.txt``
(the byte-exact artifact the daily-index poller archives).
"""

from __future__ import annotations

import datetime as dt
import re
import xml.etree.ElementTree as ET

from pydantic import BaseModel

_XML_RE = re.compile(rb"<\?xml[^>]*\?>\s*<ownershipDocument>.*?</ownershipDocument>", re.DOTALL)
_BARE_RE = re.compile(rb"<ownershipDocument>.*?</ownershipDocument>", re.DOTALL)


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
    if raw is None:
        return None
    try:
        return dt.date.fromisoformat(raw)
    except ValueError:
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
    for txn in root.findall("nonDerivativeTable/nonDerivativeTransaction"):
        amounts = txn.find("transactionAmounts")
        transactions.append(
            Form4Transaction(
                security_title=_value(txn, "securityTitle"),
                transaction_date=_date(_value(txn, "transactionDate")),
                code=_text(txn, "transactionCoding/transactionCode"),
                shares=_number(_value(amounts, "transactionShares")),
                price_per_share=_number(_value(amounts, "transactionPricePerShare")),
                acquired_disposed=_value(amounts, "transactionAcquiredDisposedCode"),
                shares_owned_after=_number(
                    _value(txn.find("postTransactionAmounts"), "sharesOwnedFollowingTransaction")
                ),
                direct_or_indirect=_value(
                    txn.find("ownershipNature"), "directOrIndirectOwnership"
                ),
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
    )
