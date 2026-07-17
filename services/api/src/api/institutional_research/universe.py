"""Canonical product-universe scope for Atlas queries.

Research readiness and exchange product eligibility are separate controls. A symbol may retain
private evidence after an exchange status change, but it must not remain selectable by current
queues, dossiers, catalysts, options, or backtests when its market requires the guarded security
master and that listing is no longer product eligible.
"""

from __future__ import annotations

from sqlalchemy import Select

from bulls.core.markets import get_market_profile
from bulls.core.models import SecurityMaster, Symbol


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
