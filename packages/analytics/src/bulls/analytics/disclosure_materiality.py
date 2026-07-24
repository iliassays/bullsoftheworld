"""DSE disclosure roles used by research and presentation layers.

Retention and investment relevance are separate decisions. Every validated exchange record remains
available for audit, while only disclosures containing a decision-relevant outcome can refresh an
investment thesis. Calendar notices remain useful catalysts without becoming evidence of an
outcome that has not happened yet.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal

DisclosureRole = Literal["material", "catalyst", "routine"]

ALWAYS_MATERIAL_CATEGORIES = frozenset({"halt", "insider", "psi"})
CATALYST_ONLY_CATEGORIES = frozenset({"board_meeting", "corporate_action"})
STRUCTURED_MATERIAL_KEYS: dict[str, frozenset[str]] = {
    "earnings": frozenset({"eps_current"}),
    "dividend": frozenset({"cash_pct", "stock_pct", "no_dividend"}),
    "rating": frozenset({"long_term", "short_term", "action"}),
}


def dse_disclosure_role(
    category: str,
    details: Mapping[str, Any] | None,
) -> DisclosureRole:
    """Classify one retained DSE record without inferring facts from an undecoded headline."""

    normalized = category.strip().lower()
    if normalized in ALWAYS_MATERIAL_CATEGORIES:
        return "material"
    if normalized in CATALYST_ONLY_CATEGORIES:
        return "catalyst"
    required_keys = STRUCTURED_MATERIAL_KEYS.get(normalized)
    if required_keys is not None:
        facts = details or {}
        return (
            "material"
            if any(key in facts and facts[key] is not None for key in required_keys)
            else "routine"
        )
    return "routine"


def is_material_dse_disclosure(
    category: str,
    details: Mapping[str, Any] | None,
) -> bool:
    return dse_disclosure_role(category, details) == "material"
