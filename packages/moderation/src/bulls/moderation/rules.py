"""L1 — deterministic gates (spec §4). Pure, free, explainable: regex patterns + abuse word lists over
the normalized views. Returns every hit; the engine collapses them into the strictest action.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .lexicon import Policy
from .normalize import NormalizedPost
from .types import Action, Category

_MASK = "****"
_OBFUSCATED_LATIN = {
    "a": "a@",
    "b": "b8",
    "e": "e3",
    "i": "i1",
    "o": "o0",
    "s": "s5",
    "t": "t7",
}


@dataclass(frozen=True)
class RuleHit:
    rule_id: str
    category: Category
    action: Action
    reason_code: str | None = None


# Negation cues (EN precedes the verb; Banglish often follows it: "kinen na"). If one sits within
# this window of an advice match, it's a disclaimer/negation, not a recommendation — don't hold it.
_NEGATION = re.compile(
    r"\b(not|never|no|dont|don't|didnt|didn't|wouldnt|wouldn't|wont|won't|"
    r"cant|can't|cannot|avoid|na|nai|nah)\b",
    re.I,
)
_NEG_WINDOW = 18


def _negated(text: str, start: int, end: int) -> bool:
    ctx = text[max(0, start - _NEG_WINDOW) : end + _NEG_WINDOW]
    return _NEGATION.search(ctx) is not None


def _word_present(word: str, post: NormalizedPost) -> bool:
    """A lexicon entry matches if it appears in the compact view (defeats obfuscation) or as a
    boundary-delimited token in the folded view. Compact match is substring — deliberate, so
    `f*ck`/`f.u.c.k` collapse to `fuck` and still hit."""
    compact_entry = re.sub(r"[^0-9a-zঀ-৿]+", "", word)
    if compact_entry and compact_entry in post.compact:
        return True
    return re.search(rf"(?<![\w]){re.escape(word)}(?![\w])", post.folded) is not None


def apply_rules(post: NormalizedPost, policy: Policy) -> list[RuleHit]:
    hits: list[RuleHit] = []

    for r in policy.pattern_rules:
        text = post.compact if r.target == "compact" else post.folded
        m = r.regex.search(text)
        if m is None:
            continue
        if r.guard_negation and _negated(text, m.start(), m.end()):
            continue  # disclaimed/negated phrasing — not a recommendation
        hits.append(RuleHit(r.id, r.category, r.action, r.reason_code))

    for w in policy.block_words:
        if _word_present(w, post):
            hits.append(RuleHit(f"abuse_block:{w}", Category.ABUSE, Action.BLOCK, "abuse"))
            break  # one block hit is enough
    else:
        for w in policy.mask_words:
            if _word_present(w, post):
                hits.append(RuleHit(f"abuse_mask:{w}", Category.ABUSE, Action.MASK, "profanity"))

    return hits


def mask_body(text: str, policy: Policy) -> str:
    """Replace mild-profanity occurrences in the display text with ****. Best-effort on the plain
    spelling (detection already happened on the obfuscation-proof compact view)."""
    masked = text
    for w in policy.mask_words:
        before = masked
        masked = re.sub(rf"(?<![\w]){re.escape(w)}(?![\w])", _MASK, masked, flags=re.I)
        if masked == before and re.fullmatch(r"[a-z0-9@]+", w, re.I):
            chars = []
            for ch in w.lower():
                alts = _OBFUSCATED_LATIN.get(ch, re.escape(ch))
                chars.append(f"[{alts}]+")
            pattern = r"(?<![A-Za-z0-9])" + r"[\W_]*".join(chars) + r"(?![A-Za-z0-9])"
            masked = re.sub(pattern, _MASK, masked, flags=re.I)
    return masked
