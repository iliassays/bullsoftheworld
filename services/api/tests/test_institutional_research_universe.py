from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.dialects import postgresql

from api.institutional_research.universe import (
    apply_certified_universe_scope,
    apply_research_product_scope,
)
from bulls.core.models import Symbol


def _sql(market: str) -> str:
    statement = apply_research_product_scope(
        select(Symbol.code).where(Symbol.market == market),
        market=market,
    )
    return str(
        statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )


def test_us_research_scope_requires_active_product_security_master() -> None:
    sql = _sql("US")

    assert "JOIN security_master" in sql
    assert "security_master.is_active IS true" in sql
    assert "security_master.is_product_eligible IS true" in sql


def test_dse_research_scope_does_not_require_us_security_master() -> None:
    assert "security_master" not in _sql("DSE")


def test_certified_scope_is_bound_to_explicit_snapshot_market_and_model_gate() -> None:
    snapshot_id = uuid.UUID("12345678-1234-5678-1234-567812345678")
    statement = apply_certified_universe_scope(
        select(Symbol.code).where(Symbol.market == "US"),
        market="US",
        snapshot_id=snapshot_id,
        require_model_eligible=True,
        cohorts=("us_small", "us_micro_penny"),
    )
    sql = str(
        statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )

    assert "JOIN research_universe_members" in sql
    assert str(snapshot_id) in sql
    assert "research_universe_members.market = 'US'" in sql
    assert "research_universe_members.decision = 'eligible'" in sql
    assert "research_universe_members.model_eligible IS true" in sql
    assert "research_universe_members.cohort IN ('us_small', 'us_micro_penny')" in sql
