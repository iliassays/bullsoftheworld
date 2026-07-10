"""Alembic environment — async, reads URL + metadata from the app."""

from __future__ import annotations

import asyncio

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

from bulls.core import models  # noqa: F401  (import registers all models on Base.metadata)
from bulls.core.config import get_settings
from bulls.core.db import Base

target_metadata = Base.metadata

_UNMANAGED_TABLES = {"hedge_log"}


def _include_object(obj, name, type_, reflected, compare_to):
    """Keep utility-owned tables outside the application migration boundary."""
    if reflected and type_ == "table" and name in _UNMANAGED_TABLES:
        return False

    table = getattr(obj, "table", None)
    return not (reflected and table is not None and table.name in _UNMANAGED_TABLES)


def _run(connection):
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        include_object=_include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_online():
    engine = create_async_engine(get_settings().database_url)
    async with engine.connect() as connection:
        await connection.run_sync(_run)
    await engine.dispose()


asyncio.run(run_online())
