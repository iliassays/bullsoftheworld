from __future__ import annotations

from sqlalchemy.dialects import postgresql

from api.routers.desks import _desk_search_statement, _escape_like


def _sql(tenant: str, query: str, limit: int = 4) -> str:
    return str(
        _desk_search_statement(tenant, query, limit).compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )


def test_desk_search_is_tenant_and_official_account_scoped() -> None:
    sql = _sql("bullsofdhaka", "Volume")

    assert "users.tenant_id = 'bullsofdhaka'" in sql
    assert "users.is_official IS true" in sql
    assert "bullsofwallst" not in sql
    assert "LIMIT 4" in sql


def test_desk_search_escapes_like_wildcards() -> None:
    assert _escape_like("100%_desk\\name") == "100\\%\\_desk\\\\name"
    sql = _sql("bullsofwallst", "%_")

    assert "bullsofwallst" in sql
    assert " ESCAPE " in sql
