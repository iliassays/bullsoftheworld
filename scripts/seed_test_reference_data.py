"""Seed the minimal reference market data required by DB integration tests.

This is intentionally not a migration or development-data generator. It refuses to run unless the
application environment is explicitly ``test`` so production can never acquire fixture rows by
accident.
"""

from __future__ import annotations

import asyncio
import datetime as dt

from sqlalchemy.dialects.postgresql import insert as pg_insert

from bulls.core.config import get_settings
from bulls.core.db import dispose_engine, get_sessionmaker
from bulls.core.models import QuoteSnapshot, Symbol


async def seed() -> None:
    if get_settings().env.lower() != "test":
        raise RuntimeError("test reference data requires ENV=test")

    symbols = [
        {
            "market": "DSE",
            "code": "GP",
            "name_en": "Grameenphone Ltd",
            "name_bn": "গ্রামীণফোন লিমিটেড",
            "sector": "Telecommunication",
            "category": "A",
            "is_active": True,
            "is_hidden": False,
            "data_status": "ready",
        },
        {
            "market": "DSE",
            "code": "OLYMPIC",
            "name_en": "Olympic Industries Ltd",
            "name_bn": "অলিম্পিক ইন্ডাস্ট্রিজ লিমিটেড",
            "sector": "Food & Allied",
            "category": "A",
            "is_active": True,
            "is_hidden": False,
            "data_status": "ready",
        },
    ]
    now = dt.datetime.now(dt.UTC)
    quotes = [
        {
            "market": "DSE",
            "code": "GP",
            "ltp": 286.4,
            "change": 5.0,
            "change_pct": 1.78,
            "open": 281.0,
            "high": 288.0,
            "low": 280.0,
            "close": 286.4,
            "prev_close": 281.4,
            "volume": 100_000,
            "trades": 1_000,
            "as_of": now,
            "is_delayed": True,
        },
        {
            "market": "DSE",
            "code": "OLYMPIC",
            "ltp": 170.0,
            "change": -1.0,
            "change_pct": -0.58,
            "open": 171.0,
            "high": 172.0,
            "low": 169.0,
            "close": 170.0,
            "prev_close": 171.0,
            "volume": 50_000,
            "trades": 500,
            "as_of": now,
            "is_delayed": True,
        },
    ]

    sm = get_sessionmaker()
    async with sm() as session:
        symbol_stmt = pg_insert(Symbol).values(symbols)
        await session.execute(
            symbol_stmt.on_conflict_do_update(
                index_elements=["market", "code"],
                set_={
                    "name_en": symbol_stmt.excluded.name_en,
                    "name_bn": symbol_stmt.excluded.name_bn,
                    "sector": symbol_stmt.excluded.sector,
                    "category": symbol_stmt.excluded.category,
                    "is_active": symbol_stmt.excluded.is_active,
                    "is_hidden": symbol_stmt.excluded.is_hidden,
                    "data_status": symbol_stmt.excluded.data_status,
                },
            )
        )
        quote_stmt = pg_insert(QuoteSnapshot).values(quotes)
        await session.execute(
            quote_stmt.on_conflict_do_update(
                index_elements=["market", "code"],
                set_={
                    column: getattr(quote_stmt.excluded, column)
                    for column in quotes[0]
                    if column not in {"market", "code"}
                },
            )
        )
        await session.commit()
    await dispose_engine()


if __name__ == "__main__":
    asyncio.run(seed())
