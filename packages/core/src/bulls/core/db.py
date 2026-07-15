"""Async database access. This is the seam that keeps the DB swappable.

Everything goes through `get_session()`. Today it's Postgres via SQLAlchemy 2.0 async; if we ever
need to split by region/tenant, this is the only place that changes.
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from bulls.core.config import get_settings


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


_engine = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None
_TENANT_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    """Process-wide async sessionmaker. Use in workers; the api uses get_session()."""
    global _engine, _sessionmaker
    if _sessionmaker is None:
        settings = get_settings()
        _engine = create_async_engine(
            settings.database_url,
            pool_pre_ping=True,
            pool_size=settings.database_pool_size,
            max_overflow=settings.database_max_overflow,
            pool_timeout=settings.database_pool_timeout_s,
            connect_args={
                "server_settings": {
                    "application_name": "bulls-of-the-world",
                    "statement_timeout": str(settings.database_statement_timeout_ms),
                }
            },
        )
        _sessionmaker = async_sessionmaker(_engine, expire_on_commit=False)
    return _sessionmaker


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: yields a session, commits on success, rolls back on error."""
    async with get_sessionmaker()() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def bind_tenant_context(session: AsyncSession, tenant_id: str) -> None:
    """Bind the transaction to one tenant for PostgreSQL row-level security.

    ``set_config(..., true)`` is transaction-local, so pooled connections cannot retain a
    previous request's tenant. Callers still include explicit tenant predicates where practical;
    RLS is the final database boundary, not a replacement for readable application queries.
    """
    if not _TENANT_ID_RE.fullmatch(tenant_id):
        raise ValueError(f"Invalid tenant id: {tenant_id!r}")
    await session.execute(select(func.set_config("app.tenant_id", tenant_id, True)))


async def verify_runtime_database_role() -> None:
    """Refuse a production runtime connection that can bypass row-level security."""
    if get_settings().env.lower() in {"local", "dev", "development", "test"}:
        return
    async with get_sessionmaker()() as session:
        row = (
            await session.execute(
                text(
                    "SELECT current_user, rolsuper, rolbypassrls "
                    "FROM pg_roles WHERE rolname = current_user"
                )
            )
        ).one()
    role, is_superuser, bypasses_rls = row
    if is_superuser or bypasses_rls:
        raise RuntimeError(
            f"Production DATABASE_URL role {role!r} bypasses row-level security; "
            "use the restricted runtime role"
        )


async def dispose_engine() -> None:
    """Tear down the engine + pool. Call on app/worker shutdown."""
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _sessionmaker = None
