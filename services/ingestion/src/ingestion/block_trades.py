"""Pull the daily per-scrip block-market list (internal dataset — admin surface only).

One fetch per trading day, after the session. Codes are filtered against our symbol master so
CSE-only or renamed scrips never pollute the table; upsert makes re-runs safe.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from bulls.core.db import get_sessionmaker
from bulls.core.models import BlockTrade, Symbol
from bulls.market_data.providers.lankabd import fetch_block_trades


async def pull_block_trades(market: str = "DSE") -> dict[str, int]:
    rows = await fetch_block_trades()
    if not rows:
        return {"fetched": 0, "stored": 0}

    async with get_sessionmaker()() as session:
        known = set(await session.scalars(select(Symbol.code).where(Symbol.market == market)))
        keep = [r for r in rows if r.code in known]
        for r in keep:
            stmt = pg_insert(BlockTrade).values(
                market=market,
                code=r.code,
                trade_date=r.trade_date,
                quantity=r.quantity,
                value_mn=r.value_mn,
                trades=r.trades,
                max_price=r.max_price,
                min_price=r.min_price,
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["market", "code", "trade_date"],
                set_={
                    "quantity": stmt.excluded.quantity,
                    "value_mn": stmt.excluded.value_mn,
                    "trades": stmt.excluded.trades,
                    "max_price": stmt.excluded.max_price,
                    "min_price": stmt.excluded.min_price,
                },
            )
            await session.execute(stmt)
        await session.commit()
    return {"fetched": len(rows), "stored": len(keep)}
