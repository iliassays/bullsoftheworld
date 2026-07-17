from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.dialects import postgresql

from api.institutional_research.universe import apply_research_product_scope
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
