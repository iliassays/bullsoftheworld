"""L2 — heuristic risk score (spec §4). Classic features, no model API. Content features come from the
normalized post; velocity / near-duplicate / account / market-risk features are supplied by the caller
via `Context` (the write-path fills them from Postgres/Redis; defaults are neutral so the engine is
testable standalone). Phase 1 is a transparent weighted rule set; it can be swapped for a fitted
logistic/GBM later without changing the interface.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .normalize import NormalizedPost

# Urgency / call-to-action cues in English + Banglish (romanized Bangla).
_URGENCY = re.compile(
    r"\b(now|today|hurry|fast|quick|last chance|don'?t miss|before (?:open|close)|"
    r"akhon|taratari|joldi|ajke|ajkei|kinbe|kine|kinen|kinun|dhukbe|dhuke|beche)\b",
    re.I,
)


@dataclass
class Context:
    """Signals the engine can't derive from text alone. All optional; neutral by default."""

    account_age_days: float | None = None
    prior_violations: int = 0
    is_official: bool = False
    followers: int = 0
    thin_liquidity: bool = False
    z_category: bool = False
    near_extreme_move: bool = False
    near_duplicate_count: int = 0  # recent near-identical posts → coordinated pump
    cashtag_velocity: int = 0  # same author spamming one cashtag
    route_code: str | None = None  # symbol page/thread the post sits under
    is_reply: bool = False


def _relevance_off_topic(post: NormalizedPost, ctx: Context) -> bool:
    """Soft signal only (spec principle #9): routed to a symbol page but the post neither tags that
    code nor any code, and isn't a reply. Never a standalone block."""
    if ctx.route_code is None or ctx.is_reply:
        return False
    return ctx.route_code not in post.cashtags and not post.cashtags


def score(post: NormalizedPost, ctx: Context | None = None) -> float:
    """Return manipulation risk in [0, 1]."""
    ctx = ctx or Context()
    r = 0.0

    has_urgency = bool(_URGENCY.search(post.folded))
    has_number = bool(post.percents or post.money)
    if post.cashtags and has_urgency and has_number:
        r += 0.30  # "buy $GP now, target ৳120" shape
    elif post.cashtags and has_urgency:
        r += 0.15

    if post.has_contact:
        r += 0.25  # off-platform contact surface

    if ctx.near_duplicate_count >= 3:
        r += 0.35  # many near-identical posts = coordinated
    if ctx.cashtag_velocity >= 5:
        r += 0.20  # one author flooding a cashtag

    if ctx.account_age_days is not None and ctx.account_age_days < 7:
        r += 0.20
    r += min(ctx.prior_violations, 3) * 0.10

    if ctx.thin_liquidity or ctx.z_category:
        r += 0.15  # easier to manipulate
    if ctx.near_extreme_move:
        r += 0.10

    if _relevance_off_topic(post, ctx):
        r += 0.15  # soft, never alone

    if ctx.is_official:
        r -= 0.50
    if ctx.followers >= 1000:
        r -= 0.10

    return max(0.0, min(1.0, r))
