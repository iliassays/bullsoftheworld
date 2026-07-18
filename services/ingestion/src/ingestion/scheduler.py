"""Ingestion: poll a market's provider, persist to Postgres, publish ticks to Redis.

Providers WITHOUT subscribe() (the DSE scraper) are polled here. A future licensed provider with
subscribe() would push instead — the rest of the system reads quote_snapshots / listens on Redis
and can't tell the difference.

Persistence is upsert (ON CONFLICT) so each poll overwrites the latest snapshot. Every published
tick goes to channel `sym:<market>:<code>` for the WebSocket gateway to fan out.
"""

from __future__ import annotations

import logging

import redis.asyncio as aioredis
from sqlalchemy.dialects.postgresql import insert as pg_insert

from bulls.core.config import get_settings
from bulls.core.db import bind_tenant_context, get_sessionmaker
from bulls.core.models import QuoteSnapshot, Symbol
from bulls.market_data import Quote, get_provider
from bulls.market_data import Symbol as ProviderSymbol
from ingestion.alerts import check_price_alerts
from ingestion.intraday import persist_intraday_capture

logger = logging.getLogger(__name__)


async def _upsert_symbols(session, symbols: list[ProviderSymbol]) -> None:
    if not symbols:
        return
    stmt = pg_insert(Symbol).values([s.model_dump() for s in symbols])
    stmt = stmt.on_conflict_do_update(
        index_elements=["market", "code"],
        set_={"name_en": stmt.excluded.name_en, "is_active": True},
    )
    await session.execute(stmt)


async def _upsert_quotes(session, quotes: list[Quote]) -> None:
    if not quotes:
        return
    rows = [q.model_dump() for q in quotes]
    stmt = pg_insert(QuoteSnapshot).values(rows)
    update_cols = {c: getattr(stmt.excluded, c) for c in rows[0] if c not in ("market", "code")}
    stmt = stmt.on_conflict_do_update(index_elements=["market", "code"], set_=update_cols)
    await session.execute(stmt)


async def _publish_ticks(redis: aioredis.Redis, quotes: list[Quote]) -> None:
    pipe = redis.pipeline()
    for q in quotes:
        pipe.publish(f"sym:{q.market}:{q.code}", q.model_dump_json())
    await pipe.execute()


async def _persist_intraday_isolated(
    session,
    quotes: list[Quote],
    *,
    expected_symbol_count: int,
) -> int:
    """Keep optional intraday research writes from aborting the existing quote projection."""

    try:
        async with session.begin_nested():
            await persist_intraday_capture(
                session,
                quotes,
                expected_symbol_count=expected_symbol_count,
            )
    except Exception:  # The legacy quote path is the release-isolation boundary.
        logger.exception("intraday research capture failed; continuing latest-quote ingestion")
        return 1
    return 0


async def poll_market(market: str, *, tenant_id: str) -> dict[str, int]:
    """One ingestion cycle for a market. Returns counts for logging/monitoring."""
    provider = get_provider(market)
    symbols = await provider.list_symbols()
    quotes = await provider.get_quotes([])  # empty = all instruments

    async with get_sessionmaker()() as session:
        await bind_tenant_context(session, tenant_id)
        await _upsert_symbols(session, symbols)
        intraday_capture_failures = await _persist_intraday_isolated(
            session,
            quotes,
            expected_symbol_count=len(symbols),
        )
        await _upsert_quotes(session, quotes)
        # User-set price alerts fire off the same poll that persisted the quotes — one-shot
        # per alert, committed atomically with the snapshot they were judged against.
        await check_price_alerts(session, tenant_id, market, {q.code: q.ltp for q in quotes})
        await session.commit()

    redis = aioredis.from_url(get_settings().redis_url)
    try:
        await _publish_ticks(redis, quotes)
    finally:
        await redis.aclose()

    return {
        "symbols": len(symbols),
        "quotes": len(quotes),
        "intraday_capture_failures": intraday_capture_failures,
    }
