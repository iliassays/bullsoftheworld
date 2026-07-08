"""Daily portfolio value snapshot — lets Portfolio show growth over time.

We snapshot only the AGGREGATE (total value, total cost) per user per day, using the same
QuoteSnapshot prices the live Portfolio view already reads. We deliberately never backfill: a
holding's quantity/avg_cost can change at any point (add/edit/delete), so projecting today's
holdings backward across historical prices would show a fictional "what if you always held this"
line, not what the user actually experienced. Idempotent (upsert by user+market+date) — a re-run
the same day just refreshes that day's row with the latest prices.

    uv run python -m ingestion.portfolio_snapshot
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from bulls.core.db import get_sessionmaker
from bulls.core.models import PortfolioHolding, PortfolioSnapshot, QuoteSnapshot
from bulls.market_data.calendar import to_market_tz


async def run(market: str = "DSE") -> dict[str, int]:
    today = to_market_tz(dt.datetime.now(dt.UTC)).date()
    sm = get_sessionmaker()
    async with sm() as session:
        holdings = (
            await session.scalars(select(PortfolioHolding).where(PortfolioHolding.market == market))
        ).all()
        if not holdings:
            return {"users": 0}

        codes = {h.code for h in holdings}
        ltp_by_code = {
            q.code: q.ltp
            for q in await session.scalars(
                select(QuoteSnapshot).where(
                    QuoteSnapshot.market == market, QuoteSnapshot.code.in_(codes)
                )
            )
        }

        by_user: dict[int, list[PortfolioHolding]] = {}
        for h in holdings:
            by_user.setdefault(h.user_id, []).append(h)

        rows = []
        for user_id, hs in by_user.items():
            total_cost = sum(h.quantity * h.avg_cost for h in hs)
            priced = [h.quantity * ltp_by_code[h.code] for h in hs if h.code in ltp_by_code]
            total_value = sum(priced) if priced else None
            rows.append(
                {
                    "user_id": user_id,
                    "market": market,
                    "date": today,
                    "total_value": total_value,
                    "total_cost": total_cost,
                }
            )

        stmt = pg_insert(PortfolioSnapshot).values(rows)
        stmt = stmt.on_conflict_do_update(
            index_elements=["user_id", "market", "date"],
            set_={
                "total_value": stmt.excluded.total_value,
                "total_cost": stmt.excluded.total_cost,
            },
        )
        await session.execute(stmt)
        await session.commit()
    return {"users": len(by_user)}


if __name__ == "__main__":
    import asyncio

    print(asyncio.run(run()))
