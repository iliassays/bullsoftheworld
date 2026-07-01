"""The synchronous engine (spec section 4, L0-L2). Pure, local, no AI, no DB - target < 15 ms.

`decide()` normalizes, runs the deterministic gates, computes the risk score, and collapses everything
into one `Decision`. Rule actions and the risk band are combined by *strictest wins* (severity max), so
a rule can only raise the action and the score can only escalate a clean post into the gray zone —
never silently downgrade a matched violation.

Anything the engine leaves in the gray zone (HOLD) is where the async L3/L4 layers take over; the engine
itself never calls them.
"""

from __future__ import annotations

from .lexicon import Policy
from .normalize import normalize
from .rules import apply_rules, mask_body
from .scorer import Context, score
from .types import Action, Category, Decision


def _band_action(risk: float, policy: Policy) -> Action:
    t = policy.thresholds
    if risk >= t.gray_high:
        return Action.BLOCK
    if risk >= t.gray_low:
        return Action.HOLD
    return Action.ALLOW


def decide(text: str, policy: Policy, ctx: Context | None = None) -> Decision:
    post = normalize(text)
    hits = apply_rules(post, policy)
    risk = score(post, ctx)

    rule_action = max((h.action for h in hits), key=lambda a: a.severity, default=Action.ALLOW)
    final = max(rule_action, _band_action(risk, policy), key=lambda a: a.severity)

    categories = list(dict.fromkeys(h.category for h in hits)) or [Category.CLEAN]
    rule_ids = [h.rule_id for h in hits]

    # Prefer a matched rule's reason; else describe why the score alone tipped it.
    reason_code = next(
        (h.reason_code for h in hits if h.action == rule_action and h.reason_code), None
    )
    if reason_code is None and final in (Action.HOLD, Action.BLOCK) and not hits:
        reason_code = "risk_score"

    layer = 1 if hits else (2 if final != Action.ALLOW else 0)

    return Decision(
        action=final,
        categories=categories,
        reason_code=reason_code,
        risk_score=round(risk, 3),
        rule_ids=rule_ids,
        layer=layer,
        masked_body=mask_body(text, policy) if final == Action.MASK else None,
    )
