"""bulls.moderation - tenant-agnostic feed-moderation engine (L0-L2, no AI, no DB).

See docs/specs/feed-moderation.md. Typical use:

    from bulls.moderation import decide, load_policy, Context
    policy = load_policy("tenants/dhaka/moderation")
    decision = decide(body, policy, Context(account_age_days=2, route_code="GP"))
    if decision.is_blocking: ...
"""

from .engine import decide
from .lexicon import Policy, load_policy
from .normalize import NormalizedPost, normalize
from .scorer import Context, score
from .types import Action, Category, Decision

__all__ = [
    "Action",
    "Category",
    "Context",
    "Decision",
    "NormalizedPost",
    "Policy",
    "decide",
    "load_policy",
    "normalize",
    "score",
]
