"""Canonical product-universe scope for Atlas queries.

Research readiness and exchange product eligibility are separate controls. A symbol may retain
private evidence after an exchange status change, but it must not remain selectable by current
queues, dossiers, catalysts, options, or backtests when its market requires the guarded security
master and that listing is no longer product eligible.
"""

from __future__ import annotations

import uuid

from sqlalchemy import Select

from bulls.core.markets import get_market_profile
from bulls.core.models import ResearchUniverseMember, SecurityMaster, Symbol


def apply_research_product_scope(statement: Select, *, market: str) -> Select:
    """Apply the market profile's current-product gate to a Symbol-based statement."""

    if not get_market_profile(market).features.security_master_product_gate:
        return statement
    return statement.join(
        SecurityMaster,
        Symbol.security_id == SecurityMaster.security_id,
    ).where(
        SecurityMaster.market == market,
        SecurityMaster.is_active.is_(True),
        SecurityMaster.is_product_eligible.is_(True),
    )


def apply_certified_universe_scope(
    statement: Select,
    *,
    market: str,
    snapshot_id: uuid.UUID,
    require_model_eligible: bool = False,
    cohorts: tuple[str, ...] | None = None,
) -> Select:
    """Restrict a Symbol query to one explicit, immutable universe snapshot.

    The snapshot id is mandatory by design.  Falling back to the latest row would make a
    historical run silently change when tomorrow's universe is generated.  Model training and
    promotable backtests must also request ``require_model_eligible`` so diagnostic current-state
    snapshots cannot leak into their samples.
    """

    scoped = statement.join(
        ResearchUniverseMember,
        (ResearchUniverseMember.market == Symbol.market)
        & (ResearchUniverseMember.code == Symbol.code),
    ).where(
        Symbol.market == market,
        ResearchUniverseMember.market == market,
        ResearchUniverseMember.snapshot_id == snapshot_id,
        ResearchUniverseMember.decision == "eligible",
    )
    if require_model_eligible:
        scoped = scoped.where(ResearchUniverseMember.model_eligible.is_(True))
    if cohorts:
        scoped = scoped.where(ResearchUniverseMember.cohort.in_(cohorts))
    return scoped


__all__ = ["apply_certified_universe_scope", "apply_research_product_scope"]
