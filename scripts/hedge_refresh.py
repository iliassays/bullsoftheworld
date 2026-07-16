"""Batch refresh for the Hedge track-record read model.

Run after the DSE EOD chain. It loads the multi-year dataset once, computes the backtest, immutable
daily monitor publication, and signal ledger in memory, then commits the read models together.
"""

from __future__ import annotations

import asyncio
import datetime as dt

from hedge_archive import content_hash
from hedge_daily import build_scan_snapshot, load_profiles
from hedge_forward import build_rows, replace_rows
from hedge_history import STRATEGY_KEY, backtest_from_inputs, serialize_history
from portfolio_backtest import _load
from scheme2_value import _load_fundamentals
from scheme_lab import quality_reversal
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from bulls.core.db import bind_tenant_context, get_sessionmaker
from bulls.core.models import HedgeDailyScanSnapshot, HedgeTrackRecordSnapshot

TENANT_ID = "bullsofdhaka"
MARKET = "DSE"


async def refresh() -> dict:
    by_code, dsex = await _load()
    if not dsex:
        raise RuntimeError("Cannot refresh Hedge history without DSEX history")
    fin, div = await _load_fundamentals(MARKET)
    signals = quality_reversal(by_code, fin, div)
    history = backtest_from_inputs(by_code, dsex, signals)
    ledger = build_rows(by_code, signals)
    as_of = max(dsex)
    profiles = await load_profiles(MARKET)
    payload = serialize_history(history)

    async with get_sessionmaker()() as session:
        await bind_tenant_context(session, TENANT_ID)
        existing_daily = await session.get(
            HedgeDailyScanSnapshot,
            (TENANT_ID, MARKET, STRATEGY_KEY, as_of),
        )
        previous_daily = await session.scalar(
            select(HedgeDailyScanSnapshot)
            .where(
                HedgeDailyScanSnapshot.tenant_id == TENANT_ID,
                HedgeDailyScanSnapshot.market == MARKET,
                HedgeDailyScanSnapshot.strategy == STRATEGY_KEY,
                HedgeDailyScanSnapshot.as_of_date < as_of,
            )
            .order_by(HedgeDailyScanSnapshot.as_of_date.desc())
            .limit(1)
        )
        daily_scan = (
            existing_daily.payload
            if existing_daily is not None
            else build_scan_snapshot(
                by_code,
                fin,
                div,
                profiles,
                signals,
                ledger,
                previous=previous_daily.payload if previous_daily else None,
            )
        )
        if existing_daily is None:
            daily_stmt = insert(HedgeDailyScanSnapshot).values(
                tenant_id=TENANT_ID,
                market=MARKET,
                strategy=STRATEGY_KEY,
                as_of_date=as_of,
                payload=daily_scan,
                content_hash=content_hash(daily_scan),
                computed_at=dt.datetime.now(dt.UTC),
            )
            await session.execute(
                daily_stmt.on_conflict_do_nothing(
                    index_elements=["tenant_id", "market", "strategy", "as_of_date"]
                )
            )
        payload["daily_scan"] = daily_scan
        stmt = insert(HedgeTrackRecordSnapshot).values(
            tenant_id=TENANT_ID,
            market=MARKET,
            strategy=STRATEGY_KEY,
            as_of_date=as_of,
            payload=payload,
            computed_at=dt.datetime.now(dt.UTC),
        )
        await session.execute(
            stmt.on_conflict_do_update(
                index_elements=["tenant_id", "market", "strategy"],
                set_={
                    "as_of_date": stmt.excluded.as_of_date,
                    "payload": stmt.excluded.payload,
                    "computed_at": stmt.excluded.computed_at,
                },
            )
        )
        await replace_rows(session, ledger, tenant_id=TENANT_ID, market=MARKET)
        await session.commit()
    return {
        "as_of": as_of.isoformat(),
        "signals": len(ledger),
        "open": sum(row["status"] == "open" for row in ledger),
        "trades": history["stats"]["n_trades"],
        "new_today": len(daily_scan["new_signals"]),
        "watchlist": len(daily_scan["watchlist"]),
    }


if __name__ == "__main__":
    print(asyncio.run(refresh()))
