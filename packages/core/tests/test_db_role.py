"""Production database-role safety checks."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from bulls.core import db


class _Result:
    def __init__(self, row: tuple[str, bool, bool]) -> None:
        self._row = row

    def one(self) -> tuple[str, bool, bool]:
        return self._row


class _Session:
    def __init__(self, row: tuple[str, bool, bool]) -> None:
        self._row = row

    async def execute(self, _statement) -> _Result:
        return _Result(self._row)


class _SessionContext:
    def __init__(self, row: tuple[str, bool, bool]) -> None:
        self._session = _Session(row)

    async def __aenter__(self) -> _Session:
        return self._session

    async def __aexit__(self, *_args) -> None:
        return None


class _SessionMaker:
    def __init__(self, row: tuple[str, bool, bool]) -> None:
        self._row = row

    def __call__(self) -> _SessionContext:
        return _SessionContext(self._row)


@pytest.mark.asyncio
async def test_production_accepts_restricted_runtime_role(monkeypatch) -> None:
    monkeypatch.setattr(db, "get_settings", lambda: SimpleNamespace(env="production"))
    monkeypatch.setattr(
        db,
        "get_sessionmaker",
        lambda: _SessionMaker(("bulls_app", False, False)),
    )

    await db.verify_runtime_database_role()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("row", "expected"),
    [
        (("owner", True, False), "owner"),
        (("runtime_bypass", False, True), "runtime_bypass"),
    ],
)
async def test_production_rejects_roles_that_bypass_rls(monkeypatch, row, expected) -> None:
    monkeypatch.setattr(db, "get_settings", lambda: SimpleNamespace(env="production"))
    monkeypatch.setattr(db, "get_sessionmaker", lambda: _SessionMaker(row))

    with pytest.raises(RuntimeError, match=expected):
        await db.verify_runtime_database_role()


@pytest.mark.asyncio
async def test_local_environment_skips_role_enforcement(monkeypatch) -> None:
    monkeypatch.setattr(db, "get_settings", lambda: SimpleNamespace(env="local"))

    def unexpected_sessionmaker():
        raise AssertionError("local role verification should not open a database connection")

    monkeypatch.setattr(db, "get_sessionmaker", unexpected_sessionmaker)
    await db.verify_runtime_database_role()
