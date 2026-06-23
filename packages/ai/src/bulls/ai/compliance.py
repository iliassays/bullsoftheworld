"""No-advice compliance gate.

Our AI is descriptive, never advisory. This deterministic checker flags imperative buy/sell
language, price targets, and entry/exit calls in any AI-generated text (English or Bangla). It is
the safety net behind every AI feature: an output that trips it is replaced with a safe
deterministic summary rather than shown to a user.

Deterministic on purpose (principle 6 — right tool, not an LLM): a safety gate must be reproducible
and fast, and must never itself depend on a model that could hallucinate its own verdict.

It leans toward RECALL — a few false positives (a descriptive line wrongly flagged, which just
falls back to a safe summary) are far cheaper than letting one real recommendation through.
"""

from __future__ import annotations

import re

from pydantic import BaseModel


class AdviceFinding(BaseModel):
    is_advice: bool
    matches: list[str]  # the phrases that tripped the gate (for logging/debugging)


# English recommendation patterns. We deliberately match advisory *phrases*, not bare words, so
# descriptive prose ("buyers stepped in", "the stock sold off") is not flagged.
_EN_PATTERNS: list[re.Pattern[str]] = [
    re.compile(p, re.IGNORECASE | re.MULTILINE)
    for p in (
        # imperative buy/sell at the start of a sentence ("Buy $GP now, ...")
        r"^\s*(buy|sell|accumulate|short|avoid|dump)\b",
        r"\bshould (buy|sell|hold|accumulate|exit|avoid|short|long|dump)\b",
        r"\b(buy|sell) (now|here|the dip|more|today|immediately)\b",
        r"\b(buy|sell)\b[^.!?\n]{0,20}\b(now|today)\b",  # "buy $GP now"
        r"\btime to (buy|sell|exit|enter|accumulate)\b",
        r"\b(good|great|nice|solid|attractive) (buy|entry|sell|exit)\b",
        r"\b(load|loading) up\b",
        r"\b(book|take|lock in) (profit|profits|gains)\b",
        r"\bcut (your )?loss(es)?\b",
        r"\bstop[- ]?loss\b",
        r"\b(price )?target\b",
        r"\bgo (long|short)\b",
        r"\bdouble down\b",
        r"\brecommend(ed|ation|ing)?\b",
        r"\bentry (point|price|level|zone)\b",
        r"\b(must|i'?d|i would) (buy|sell)\b",
        r"\bworth (buying|selling)\b",
    )
]

# Bangla advisory phrases. Bengali script doesn't play well with \b word boundaries, so these are
# matched as substrings — reliable for these multi-character forms.
_BN_SUBSTRINGS: tuple[str, ...] = (
    "কিনুন",  # buy (imperative)
    "কিনে ফেল",  # buy it up
    "কিনে রাখ",  # buy and hold
    "কেনা উচিত",  # should buy
    "বিক্রি করুন",  # sell (imperative)
    "বিক্রি করে দ",  # sell it off
    "বেচে দ",  # sell off
    "বিক্রি করা উচিত",  # should sell
    "ধরে রাখুন",  # hold (advice)
    "টার্গেট",  # target
    "লাভ তুলে",  # take profit
    "প্রফিট বুক",  # book profit
    "স্টপ লস",  # stop loss
    "এড়িয়ে চল",  # avoid
    "কেনার সময়",  # time to buy
    "বেচার সময়",  # time to sell
)


def contains_advice(text: str) -> AdviceFinding:
    """Flag investment-advice language in `text`. Pure and deterministic."""
    matches: list[str] = []
    for pat in _EN_PATTERNS:
        m = pat.search(text)
        if m:
            matches.append(m.group(0).lower())
    for sub in _BN_SUBSTRINGS:
        if sub in text:
            matches.append(sub)
    # de-dupe, preserve order
    matches = list(dict.fromkeys(matches))
    return AdviceFinding(is_advice=bool(matches), matches=matches)
