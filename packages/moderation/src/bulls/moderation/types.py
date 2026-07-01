"""Core moderation types — the vocabulary the whole cascade speaks.

Actions and categories mirror docs/specs/feed-moderation.md §3/§5. A `Decision` is what the engine
returns for one post: the action to take, why (categories + machine reason code + human-facing rule
ids), the risk score, and — for MASK — the masked body to store instead of the raw text.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class Action(StrEnum):
    """What to do with a post. Ordered by severity so `max()` picks the strictest."""

    ALLOW = "allow"  # publish normally
    MASK = "mask"  # publish with profanity masked
    LABEL = "label"  # publish with a banner (cleared low-risk only)
    HOLD = "hold"  # not public; queued for review / async adjudication
    BLOCK = "block"  # rejected at write

    @property
    def severity(self) -> int:
        return _SEVERITY[self]


_SEVERITY = {
    Action.ALLOW: 0,
    Action.MASK: 1,
    Action.LABEL: 2,
    Action.HOLD: 3,
    Action.BLOCK: 4,
}


class Category(StrEnum):
    """BSEC-aligned violation categories (spec §3). C0 = clean."""

    CLEAN = "C0"
    ADVICE = "C1"  # investment advice / recommendation
    GUARANTEE = "C2"  # guaranteed return
    PUMP = "C3"  # pump / coordinated manipulation
    RUMOUR = "C4"  # rumour-as-fact (price-sensitive)
    SOLICITATION = "C5"  # off-platform / paid tips
    ABUSE = "C6"  # abuse / profanity / harassment
    INSIDER = "C7"  # insider-information claim
    IMPERSONATION = "C8"  # impersonating an official desk
    SPAM = "C9"  # irrelevant / spam / low-quality


class Decision(BaseModel):
    """The engine's verdict for one post."""

    action: Action = Action.ALLOW
    categories: list[Category] = Field(default_factory=list)
    reason_code: str | None = None  # machine/user code, e.g. "advice_target", "guarantee"
    risk_score: float = 0.0  # 0..1, from L2
    rule_ids: list[str] = Field(default_factory=list)  # which lexicon/pattern entries fired
    layer: int = 0  # highest layer that contributed (0=normalize .. 4=LLM)
    masked_body: str | None = None  # set when action == MASK

    @property
    def is_blocking(self) -> bool:
        return self.action == Action.BLOCK

    @property
    def is_publishable(self) -> bool:
        """ALLOW/MASK/LABEL go public immediately; HOLD/BLOCK do not."""
        return self.action in (Action.ALLOW, Action.MASK, Action.LABEL)
