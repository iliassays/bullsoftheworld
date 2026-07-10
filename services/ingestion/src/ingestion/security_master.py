"""US security-master onboarding.

This is intentionally separate from price ingestion. The job first builds a raw, auditable security
master, then publishes only eligible instruments into the product-facing `symbols` table. That keeps
warrants, rights, units, preferreds, test issues, and deficient listings out of retail discovery
without losing provenance.

    uv run python -m ingestion.security_master US
"""

from __future__ import annotations

import asyncio
import datetime as dt
import sys

from sqlalchemy import exists, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from bulls.core.config import get_settings
from bulls.core.db import get_sessionmaker
from bulls.core.models import SecurityMaster, Symbol
from bulls.market_data.providers.us_security_master import (
    UsSecurityRecord,
    fetch_us_security_master,
)

UPSERT_BATCH_SIZE = 1000


def _user_agent() -> str:
    settings = get_settings()
    contact = settings.sec_contact_email
    return f"BullsOfTheWorld/0.1 security-master {contact}"


def _security_rows(records: list[UsSecurityRecord], fetched_at: dt.datetime) -> list[dict]:
    return [
        {
            **record.model_dump(),
            "last_seen_at": fetched_at,
            "updated_at": fetched_at,
        }
        for record in records
    ]


def _symbol_rows(records: list[UsSecurityRecord]) -> list[dict]:
    return [
        {
            "market": record.market,
            "code": record.symbol,
            "name_en": record.security_name,
            "name_bn": None,
            "sector": None,
            "category": None,
            "is_active": True,
            "is_hidden": False,
            "data_status": "reference_only",
        }
        for record in records
        if record.is_product_eligible
    ]


def _chunks[T](rows: list[T], size: int = UPSERT_BATCH_SIZE) -> list[list[T]]:
    return [rows[i : i + size] for i in range(0, len(rows), size)]


async def _upsert_security_master(session, rows: list[dict]) -> None:
    for batch in _chunks(rows):
        stmt = pg_insert(SecurityMaster).values(batch)
        update_cols = {
            col: getattr(stmt.excluded, col)
            for col in batch[0]
            if col not in {"market", "symbol", "first_seen_at"}
        }
        stmt = stmt.on_conflict_do_update(index_elements=["market", "symbol"], set_=update_cols)
        await session.execute(stmt)


async def _upsert_product_symbols(session, rows: list[dict]) -> None:
    for batch in _chunks(rows):
        stmt = pg_insert(Symbol).values(batch)
        update_cols = {
            "name_en": stmt.excluded.name_en,
            "name_bn": stmt.excluded.name_bn,
            "sector": stmt.excluded.sector,
            "category": stmt.excluded.category,
            "is_active": stmt.excluded.is_active,
        }
        stmt = stmt.on_conflict_do_update(index_elements=["market", "code"], set_=update_cols)
        await session.execute(stmt)


async def persist_security_master(records: list[UsSecurityRecord]) -> dict[str, int]:
    fetched_at = dt.datetime.now(dt.UTC)
    security_rows = _security_rows(records, fetched_at)
    symbol_rows = _symbol_rows(records)

    sm = get_sessionmaker()
    async with sm() as session:
        await _upsert_security_master(session, security_rows)
        await _upsert_product_symbols(session, symbol_rows)
        if records:
            market = records[0].market
            await session.execute(
                update(SecurityMaster)
                .where(SecurityMaster.market == market, SecurityMaster.last_seen_at < fetched_at)
                .values(is_active=False, is_product_eligible=False, exclude_reason="not_seen")
            )
            await session.execute(
                update(Symbol)
                .where(
                    Symbol.market == market,
                    ~exists().where(
                        SecurityMaster.market == Symbol.market,
                        SecurityMaster.symbol == Symbol.code,
                        SecurityMaster.is_product_eligible.is_(True),
                    ),
                )
                .values(is_active=False)
            )
        await session.commit()

    return {
        "raw_securities": len(records),
        "product_symbols": len(symbol_rows),
        "common_stocks": sum(1 for r in records if r.instrument_type == "common_stock"),
        "adrs": sum(1 for r in records if r.instrument_type == "adr"),
        "etfs": sum(1 for r in records if r.instrument_type == "etf"),
        "excluded": sum(1 for r in records if not r.is_product_eligible),
        "with_cik": sum(1 for r in records if r.cik is not None),
    }


async def collect(market: str = "US") -> dict[str, int]:
    if market.upper() != "US":
        raise ValueError("security_master currently supports market='US' only")
    records = await fetch_us_security_master(_user_agent())
    return await persist_security_master(records)


def main() -> None:
    market = sys.argv[1] if len(sys.argv) > 1 else "US"
    print(f"[security-master] refreshing {market} listed universe")
    stats = asyncio.run(collect(market))
    print(f"[security-master] done: {stats}")


if __name__ == "__main__":
    main()
