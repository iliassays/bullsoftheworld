"""L0 — normalize & extract. Evasion lives here (spec §4 L0).

We produce two text views plus structured signals:
- `folded`  — NFKC, zero-width stripped, latin lower-cased, runs collapsed, whitespace normalized.
              Word boundaries preserved → used for *phrase* patterns. Bangla script kept as-is.
- `compact` — `folded` with separators removed and leet folded (`b.u.y`/`8uy` → `buy`) → used for
              *single-token* lexicon hits that obfuscation would otherwise slip past.

Bangla is caseless, so lower-casing only touches latin; Banglish (romanized Bangla) is latin, so both
views cover it. Structured extraction pulls cashtags, links, phones and money/percent mentions for the
rule and scorer layers.
"""

from __future__ import annotations

import re
import unicodedata

from pydantic import BaseModel

# $ + 1-16 symbol chars. US tickers include one-letter codes and share classes like BRK.B.
_CASHTAG_RE = re.compile(r"\$([A-Z][A-Z0-9.-]{0,15})")
_URL_RE = re.compile(r"https?://\S+|\b(?:t\.me|wa\.me|chat\.whatsapp\.com|bit\.ly)/\S+", re.I)
# BD mobile numbers: 01XXXXXXXXX or +8801XXXXXXXXX, tolerating spaces/dashes.
_PHONE_RE = re.compile(r"(?:\+?880[\s-]?)?01[\s-]?\d[\s-]?\d(?:[\s-]?\d){7}")
_PERCENT_RE = re.compile(r"\d{1,3}(?:\.\d+)?\s?%")
_MONEY_RE = re.compile(r"(?:৳|tk|taka|rs)\s?\d[\d,]*", re.I)

_ZERO_WIDTH = dict.fromkeys(map(ord, "​‌‍⁠﻿"), None)
_LEET = str.maketrans(
    {"0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "7": "t", "8": "b", "@": "a"}
)
# folded: 3+ identical chars -> 2, so legit doubles survive ("guaranteeed" -> "guaranteed",
# not "guaranted"). compact then collapses ALL doubles for obfuscation-proof token matching.
_RUN3_RE = re.compile(r"(.)\1{2,}")
_RUN2_RE = re.compile(r"(.)\1+")
_WS_RE = re.compile(r"\s+")
_SEP_RE = re.compile(r"[^0-9a-zঀ-৿]+")  # keep latin + digits + Bangla block


class NormalizedPost(BaseModel):
    raw: str
    folded: str
    compact: str
    cashtags: list[str]
    urls: list[str]
    phones: list[str]
    percents: list[str]
    money: list[str]

    @property
    def has_contact(self) -> bool:
        """Off-platform contact surface — a solicitation signal."""
        return bool(self.urls or self.phones)


def parse_cashtags(text: str) -> list[str]:
    """Unique cashtag codes in order of first appearance.

    This deliberately extracts candidates only. The API validates candidates against the active
    tenant's symbol table before attaching them to a post.
    """
    codes: list[str] = []
    seen: set[str] = set()
    for raw in _CASHTAG_RE.findall(text.upper()):
        code = raw.rstrip(".-")
        if not code or code in seen:
            continue
        seen.add(code)
        codes.append(code)
    return codes


def _fold(text: str) -> str:
    t = unicodedata.normalize("NFKC", text).translate(_ZERO_WIDTH)
    t = _RUN3_RE.sub(r"\1\1", t.lower())
    return _WS_RE.sub(" ", t).strip()


def _compact(folded: str) -> str:
    """Strip separators, fold leet, and collapse all doubles so `b.u.y`, `b u y`, `8uy`, `buuuy`
    all become `buy` for obfuscation-proof single-token matching."""
    return _RUN2_RE.sub(r"\1", _SEP_RE.sub("", folded.translate(_LEET)))


def normalize(text: str) -> NormalizedPost:
    folded = _fold(text)
    return NormalizedPost(
        raw=text,
        folded=folded,
        compact=_compact(folded),
        # cashtags parse off the raw upper-case (folded is lower-cased).
        cashtags=parse_cashtags(text),
        urls=[m.group(0) for m in _URL_RE.finditer(text)],
        phones=[m.group(0) for m in _PHONE_RE.finditer(text)],
        percents=[m.group(0) for m in _PERCENT_RE.finditer(folded)],
        money=[m.group(0) for m in _MONEY_RE.finditer(folded)],
    )
