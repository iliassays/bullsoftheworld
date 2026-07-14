"""Shared symbol publication policy.

This module is intentionally dependency-free so API and ingestion services enforce the same
coverage decision without importing each other.
"""

from __future__ import annotations

_RESEARCH_ONLY_FAILURES = frozenset(
    {
        "product_eligible",
        "nonzero_volume",
        "market_cap_floor",
        "liquidity",
        "price_floor",
    }
)


def research_publication_status(
    required_gates_passed: bool,
    failure_reasons: list[str] | tuple[str, ...],
) -> str | None:
    """Map completed evidence to a public coverage tier.

    Identity, filing, history, freshness, and integrity failures remain private. Marketability
    failures may be opened for research, but never enter ready-only rankings or agents.
    """
    if required_gates_passed:
        return "ready"
    failures = set(failure_reasons)
    if failures and failures.issubset(_RESEARCH_ONLY_FAILURES):
        return "research_only"
    return None
