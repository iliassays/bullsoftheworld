from __future__ import annotations

import pytest
from sqlalchemy.dialects import postgresql

from api.routers.market import _escape_like, list_symbols
from bulls.core.models import Symbol
from bulls.core.tenancy import Tenant


class _FakeScalars:
    def __init__(self, rows: list[Symbol]) -> None:
        self._rows = rows

    def all(self) -> list[Symbol]:
        return self._rows


class _FakeResult:
    def __init__(self, rows: list[Symbol]) -> None:
        self._rows = rows

    def scalars(self) -> _FakeScalars:
        return _FakeScalars(self._rows)


class _FakeSession:
    statement = None

    async def execute(self, statement):
        self.statement = statement
        return _FakeResult(
            [
                Symbol(
                    market="US",
                    code="AAPL",
                    name_en="Apple Inc.",
                    name_bn=None,
                    sector=None,
                    category=None,
                    is_active=True,
                    is_hidden=False,
                    data_status="ready",
                )
            ]
        )


def test_escape_like_treats_user_wildcards_as_literals() -> None:
    assert _escape_like("BRK_%\\") == "BRK\\_\\%\\\\"


@pytest.mark.asyncio
async def test_symbol_search_builds_server_side_filter_and_ranking() -> None:
    session = _FakeSession()
    tenant = Tenant(
        name="wallst",
        display_name="Wall St",
        market="US",
        locale="en",
        site_url="https://example.com",
        support_email="support@example.com",
        email_from="Wall St <no-reply@example.com>",
        logo_url="https://example.com/logo.png",
        tagline_en="Facts first",
        tagline_bn="তথ্য আগে",
    )

    rows = await list_symbols(tenant, session, limit=5, offset=10, q="aa")

    assert rows[0].code == "AAPL"
    sql = str(
        session.statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )
    assert "symbols.market = 'US'" in sql
    assert (
        "symbols.data_status IN "
        "('ready', 'research_only', 'reference_only', 'onboarding', 'degraded')" in sql
    )
    assert "upper(symbols.code) LIKE" in sql
    assert "upper(symbols.name_en) LIKE" in sql
    assert "ORDER BY CASE" in sql
    assert "LIMIT 5 OFFSET 10" in sql
