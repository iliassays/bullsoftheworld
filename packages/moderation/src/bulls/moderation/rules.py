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


@dataclass(frozen=True)
class RuleHit:
    rule_id: str
    category: Category
    action: Action
    reason_code: str | None = None


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
        if r.regex.search(text):
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
        masked = re.sub(rf"(?<![\w]){re.escape(w)}(?![\w])", _MASK, masked, flags=re.I)
    return masked
