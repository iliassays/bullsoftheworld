"""Provision the restricted PostgreSQL role used by APIs and workers.

Run after migrations with MIGRATION_DATABASE_URL and APP_DATABASE_PASSWORD set. The migration URL
must be an owner/admin connection; DATABASE_URL should then point at ``bulls_app``. No secret is
printed or stored by this script.
"""

from __future__ import annotations

import asyncio
import os

import asyncpg

from bulls.core.config import get_settings

_ROLE = "bulls_app"


def _asyncpg_dsn(url: str) -> str:
    return url.replace("postgresql+asyncpg://", "postgresql://", 1)


async def provision() -> None:
    owner_url = os.environ.get("MIGRATION_DATABASE_URL", "")
    password = os.environ.get("APP_DATABASE_PASSWORD", "")
    if not owner_url:
        raise RuntimeError("MIGRATION_DATABASE_URL is required")
    if len(password) < 32:
        raise RuntimeError("APP_DATABASE_PASSWORD must be a random value of at least 32 characters")

    connection = await asyncpg.connect(_asyncpg_dsn(owner_url))
    try:
        exists = await connection.fetchval("SELECT 1 FROM pg_roles WHERE rolname = $1", _ROLE)
        if not exists:
            await connection.execute(f"CREATE ROLE {_ROLE} LOGIN NOSUPERUSER NOBYPASSRLS")
        quoted_password = await connection.fetchval("SELECT quote_literal($1)", password)
        await connection.execute(
            f"ALTER ROLE {_ROLE} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT "
            f"NOREPLICATION NOBYPASSRLS PASSWORD {quoted_password}"
        )
        database = await connection.fetchval("SELECT current_database()")
        quoted_database = await connection.fetchval("SELECT quote_ident($1)", database)
        await connection.execute(f"GRANT CONNECT ON DATABASE {quoted_database} TO {_ROLE}")
        await connection.execute(f"REVOKE CREATE ON SCHEMA public FROM {_ROLE}")
        await connection.execute(f"GRANT USAGE ON SCHEMA public TO {_ROLE}")
        await connection.execute(
            f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {_ROLE}"
        )
        await connection.execute(
            f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {_ROLE}"
        )
        await connection.execute(
            f"ALTER DEFAULT PRIVILEGES IN SCHEMA public "
            f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {_ROLE}"
        )
        await connection.execute(
            f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO {_ROLE}"
        )
    finally:
        await connection.close()

    # Fail the release before systemd restarts anything when the application environment still
    # points at the owner role, has a stale password, or resolves to a role that can bypass RLS.
    runtime_url = get_settings().database_url
    runtime = await asyncpg.connect(_asyncpg_dsn(runtime_url))
    try:
        current_user, is_superuser, bypasses_rls = await runtime.fetchrow(
            "SELECT current_user, rolsuper, rolbypassrls "
            "FROM pg_roles WHERE rolname = current_user"
        )
        if current_user != _ROLE or is_superuser or bypasses_rls:
            raise RuntimeError(
                "DATABASE_URL must authenticate as the restricted bulls_app role before restart"
            )
    finally:
        await runtime.close()


if __name__ == "__main__":
    asyncio.run(provision())
