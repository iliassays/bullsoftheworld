"""Decode a DSE announcement body into language-neutral structured fields.

DSE announcement text is templated, so deterministic regex pulls out the numbers and dates that
matter to a trader — EPS now vs a year ago, dividend rate, record date, the spot-market window, a
board meeting's agenda. We store ONLY the facts (numbers, ISO dates, enums) in `details`; the
frontend renders the human sentence per locale (EN/BN), so the decoding stays bilingual.

Everything here is best-effort: a field that doesn't match is simply omitted — never guessed. This
keeps us on the right side of "omit over mislead": a half-parsed dividend shows what we're sure of.
"""

from __future__ import annotations

import datetime as dt
import re
from typing import Any

_FACE_VALUE = (
    10.0  # DSE equities are near-universally Tk 10 par; surfaced in details so the UI says so
)


def _iso(value: str) -> str | None:
    """Normalise the two DSE date formats (DD.MM.YYYY and 'Month DD, YYYY') to ISO, else None."""
    value = value.strip().rstrip(".")
    for fmt in (
        "%d.%m.%Y",
        "%d/%m/%Y",
        "%d-%b-%Y",
        "%d-%B-%Y",
        "%d %b %Y",
        "%d %B %Y",
        "%B %d, %Y",
        "%b %d, %Y",
        "%d-%m-%Y",
        "%Y-%m-%d",
    ):
        try:
            return dt.datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            continue
    return None


# A Tk amount, optionally negative via surrounding parentheses, e.g. "Tk. (1.87)" = -1.87.
_TK = r"Tk\.?\s*(\(?)\s*-?([\d,]+\.?\d*)\s*(\)?)"


def _money(m: re.Match[str] | None) -> float | None:
    if not m:
        return None
    open_p, num, close_p = m.group(1), m.group(2), m.group(3)
    val = float(num.replace(",", ""))
    return -val if (open_p and close_p) else val


def _eps_trend(cur: float, prior: float) -> str:
    if cur < 0 and prior < 0:
        return "loss_widened" if cur < prior else "loss_narrowed"
    if cur < 0 <= prior:
        return "to_loss"
    if prior < 0 <= cur:
        return "to_profit"
    if cur > prior:
        return "up"
    return "down" if cur < prior else "flat"


def _period(text: str) -> str | None:
    t = text.lower()
    if "first quarter" in t or "1st quarter" in t or "q1" in t or "january-march" in t:
        return "Q1"
    # DSE files the mid-year report as the "Second Quarter" (Jan-Jun cumulative) far more often than
    # it says "half yearly" — without the q2/second-quarter cues this whole milestone went untagged.
    if (
        "second quarter" in t
        or "2nd quarter" in t
        or "q2" in t
        or "half year" in t
        or "half-year" in t
        or "half yearly" in t
        or "january-june" in t
        or "april-june" in t
    ):
        return "H1"
    if "third quarter" in t or "3rd quarter" in t or "q3" in t or "january-september" in t:
        return "Q3"
    if "annual" in t or "year ended" in t or "audited accounts" in t:
        return "annual"
    return None


def _earnings(body: str, title: str) -> dict[str, Any]:
    d: dict[str, Any] = {}
    eps = re.search(rf"EPS\s+was\s+{_TK}\s+for\s+.+?\s+as against\s+{_TK}\s+for", body, re.I)
    if eps:
        tks = list(re.finditer(_TK, eps.group(0)))  # first = this period, second = a year ago
        if len(tks) >= 2:
            cur, prior = _money(tks[0]), _money(tks[1])
            if cur is not None and prior is not None:
                d.update(eps_current=cur, eps_prior=prior, eps_trend=_eps_trend(cur, prior))
    nav = _money(re.search(rf"NAV per share was\s+{_TK}", body, re.I))
    if nav is not None:
        d["nav"] = nav
    nocf = _money(re.search(rf"NOCFPS was\s+{_TK}", body, re.I))
    if nocf is not None:
        d["nocfps"] = nocf
    period = _period(title) or _period(body)
    if period:
        d["period"] = period
    return d


def _dividend(body: str) -> dict[str, Any]:
    d: dict[str, Any] = {}
    if re.search(r"\bno dividend\b", body, re.I):
        d["no_dividend"] = True
    cash = re.search(r"([\d.]+)\s*%\s*cash", body, re.I)
    stock = re.search(r"([\d.]+)\s*%\s*(?:stock|bonus)", body, re.I)
    if cash:
        pct = float(cash.group(1))
        d.update(
            cash_pct=pct, per_share_cash=round(pct / 100 * _FACE_VALUE, 4), face_value=_FACE_VALUE
        )
    if stock:
        d["stock_pct"] = float(stock.group(1))
    yr = re.search(r"year ended\s+([A-Za-z]+ \d{1,2}, \d{4})", body, re.I)
    if yr:
        d["year_ended"] = _iso(yr.group(1))
    agm = re.search(r"AGM[:\s]+([\d]{2}\.[\d]{2}\.[\d]{4})", body, re.I)
    if agm:
        d["agm_date"] = _iso(agm.group(1))
    return d


def _board_meeting(body: str) -> dict[str, Any]:
    d: dict[str, Any] = {}
    held = re.search(r"held on\s+([A-Za-z]+ \d{1,2},? \d{4})", body, re.I)
    if held:
        d["meeting_date"] = _iso(held.group(1))
    agenda: list[str] = []
    if re.search(r"dividend", body, re.I):
        agenda.append("dividend")
    if _period(body):
        agenda.append("financials")
    if agenda:
        d["agenda"] = agenda
        d["period"] = _period(body)
    return d


def _corporate_action(body: str) -> dict[str, Any]:
    d: dict[str, Any] = {}
    date_token = (
        r"(?:\d{1,2}[./-](?:\d{1,2}|[A-Za-z]+)[./-]\d{4}|"
        r"[A-Za-z]+\s+\d{1,2},?\s+\d{4}|\d{1,2}\s+[A-Za-z]+\s+\d{4})"
    )
    rec = re.search(
        rf"\brecord date\b(?:(?!(?:notified|notify|later)).){{0,120}}?"
        rf"(?::|\bi\.?e\.?|\bis\b|\bwill be\b)\s*({date_token})",
        body,
        re.I | re.S,
    )
    if rec:
        d["record_date"] = _iso(rec.group(1))
    spot = re.search(
        r"Spot Market.*?from\s+([\d]{2}\.[\d]{2}\.[\d]{4})\s+to\s+([\d]{2}\.[\d]{2}\.[\d]{4})",
        body,
        re.I | re.S,
    )
    if spot:
        d["spot_from"], d["spot_to"] = _iso(spot.group(1)), _iso(spot.group(2))
    agm = re.search(r"AGM[:\s]+([\d]{2}\.[\d]{2}\.[\d]{4})", body, re.I)
    if agm:
        d["agm_date"] = _iso(agm.group(1))

    # Prefer the explicit natural-language entitlement over a bare X:Y token. DSE announcements
    # sometimes show both the issuer's shorthand and the economically unambiguous explanation.
    right_for_existing = re.search(
        r"(\d+(?:\.\d+)?)\s+(?:right|rights)\s+shares?\s+"
        r"(?:for|against)\s+(?:every\s+)?(\d+(?:\.\d+)?)\s+existing\s+shares?",
        body,
        re.I,
    )
    if not right_for_existing:
        right_for_existing = re.search(
            r"(\d+(?:\.\d+)?)\s+(?:right|rights)\s+shares?\s+against\s+"
            r"(\d+(?:\.\d+)?)\s+existing",
            body,
            re.I,
        )
    if right_for_existing:
        new_shares = float(right_for_existing.group(1))
        old_shares = float(right_for_existing.group(2))
        if new_shares > 0 and old_shares > 0:
            d["rights_new_shares"] = new_shares
            d["rights_existing_shares"] = old_shares
            d["rights_ratio"] = new_shares / old_shares
    else:
        ratio = re.search(
            r"(?:issuance\s+of\s+|issue\s+of\s+)?(\d+(?:\.\d+)?)\s*:\s*"
            r"(\d+(?:\.\d+)?)\s+(?:right|rights)\s+shares?",
            body,
            re.I,
        )
        if ratio:
            new_shares = float(ratio.group(1))
            old_shares = float(ratio.group(2))
            if new_shares > 0 and old_shares > 0:
                d["rights_new_shares"] = new_shares
                d["rights_existing_shares"] = old_shares
                d["rights_ratio"] = new_shares / old_shares

    issue_price = re.search(
        r"(?:offer|issue)\s+price(?:\s+of)?\s*[:\-]?\s*"
        r"(?:BDT|Tk\.?)\s*([\d,]+(?:\.\d+)?)",
        body,
        re.I,
    )
    if issue_price:
        d["rights_subscription_price"] = float(issue_price.group(1).replace(",", ""))
    return d


def _rating(body: str) -> dict[str, Any]:
    # DSE phrasing: ... as "AA-" in the long term and "ST-2" in the short term ... "Stable" outlook.
    d: dict[str, Any] = {}
    lt = re.search(r'"([A-Z0-9+\-]{1,6})"\s+in the long[\s-]*term', body, re.I)
    st = re.search(r'"([A-Z0-9+\-]{1,6})"\s+in the short[\s-]*term', body, re.I)
    if lt:
        d["long_term"] = lt.group(1).upper()
    if st:
        d["short_term"] = st.group(1).upper()
    outlook = re.search(r"([A-Za-z]+)\s+outlook", body, re.I)
    if outlook:
        d["outlook"] = outlook.group(1).capitalize()
    if re.search(r"downgrade", body, re.I):
        d["action"] = "downgrade"
    elif re.search(r"upgrade", body, re.I):
        d["action"] = "upgrade"
    return d


_DECODERS = {
    "earnings": lambda body, title: _earnings(body, title),
    "dividend": lambda body, title: _dividend(body),
    "board_meeting": lambda body, title: _board_meeting(body),
    "corporate_action": lambda body, title: _corporate_action(body),
    "halt": lambda body, title: _corporate_action(body),  # spot/suspension share the date shape
    "rating": lambda body, title: _rating(body),
}


def decode(category: str, headline: str, body: str) -> dict[str, Any]:
    """Return the structured fields for this announcement (empty dict if nothing decodes)."""
    decoder = _DECODERS.get(category)
    if not decoder or not body:
        return {}
    try:
        details = decoder(body, headline)
        # Dividend announcements are the authoritative source for bonus terms and frequently carry
        # the record date in the same body. Merge only deterministic corporate-action fields.
        if category == "dividend":
            details.update(_corporate_action(body))
        return details
    except Exception:  # a parse miss must never break onboarding
        return {}
