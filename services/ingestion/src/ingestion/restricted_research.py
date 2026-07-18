"""Bounded market-data refresh support for private US research securities."""

from __future__ import annotations

import asyncio
import datetime as dt

from sqlalchemy import and_, or_, select

from bulls.core.db import get_sessionmaker
from bulls.core.models import SecurityMaster, Symbol
from bulls.market_data.calendar import most_recent_completed_session
from bulls.market_data.providers.us_yahoo import EOD_PUBLICATION_DELAY
from ingestion.analytics import compute_all
from ingestion.history import US_DAILY_LOOKBACK_DAYS
from ingestion.history import collect as collect_history
from ingestion.us_eod_snapshot import publish_quotes

MARKET = "US"
PRIVATE_REFRESH_BATCH_SIZE = 1_500


def _stale_private_research_stmt(session_date: dt.date, *, limit: int):
    """Select an oldest-first, product-eligible batch that the public EOD chain excludes."""
    return (
        select(Symbol.code)
        .join(
            SecurityMaster,
            (SecurityMaster.market == Symbol.market) & (SecurityMaster.symbol == Symbol.code),
        )
        .where(
            Symbol.market == MARKET,
            Symbol.is_active.is_(True),
            Symbol.is_hidden.is_(False),
            Symbol.data_status != "ready",
            Symbol.research_status.in_(("ready", "partial")),
            SecurityMaster.is_active.is_(True),
            SecurityMaster.is_product_eligible.is_(True),
            or_(Symbol.data_last_date.is_(None), Symbol.data_last_date < session_date),
        )
        .order_by(Symbol.data_last_date.asc().nulls_first(), Symbol.code)
        .limit(limit)
    )


async def stale_private_research_codes(
    session_date: dt.date,
    *,
    limit: int = PRIVATE_REFRESH_BATCH_SIZE,
) -> list[str]:
    """Return one resumable daily batch of stale Atlas-ready symbols."""
    sm = get_sessionmaker()
    async with sm() as session:
        return list(await session.scalars(_stale_private_research_stmt(session_date, limit=limit)))


async def restricted_research_codes() -> list[str]:
    """Return bounded high-risk research names that must stay fresh but out of agents."""
    sm = get_sessionmaker()
    async with sm() as session:
        return list(
            await session.scalars(
                select(Symbol.code)
                .join(
                    SecurityMaster,
                    (SecurityMaster.market == Symbol.market)
                    & (SecurityMaster.symbol == Symbol.code),
                )
                .where(
                    Symbol.market == MARKET,
                    Symbol.is_active.is_(True),
                    SecurityMaster.is_active.is_(True),
                    SecurityMaster.instrument_type == "common_stock",
                    or_(
                        and_(
                            Symbol.data_status == "research_only",
                            Symbol.is_hidden.is_(False),
                        ),
                        and_(
                            Symbol.is_hidden.is_(True),
                            Symbol.data_status.in_(("onboarding", "degraded")),
                            SecurityMaster.is_product_eligible.is_(False),
                            SecurityMaster.exclude_reason.like("financial_status_%"),
                        ),
                    ),
                )
                .order_by(Symbol.code)
            )
        )


async def refresh_restricted_market_data() -> dict[str, object]:
    """Refresh a bounded private batch without feeding Ideas, agents, or market aggregates."""
    session_date = most_recent_completed_session(
        dt.datetime.now(dt.UTC),
        market=MARKET,
        publication_delay=EOD_PUBLICATION_DELAY,
    )
    private_codes, restricted_codes = await asyncio.gather(
        stale_private_research_codes(session_date),
        restricted_research_codes(),
    )
    codes = sorted(set(private_codes) | set(restricted_codes))
    if not codes:
        return {
            "session_date": session_date.isoformat(),
            "symbols": 0,
            "private_symbols": 0,
            "restricted_symbols": 0,
            "history": {},
            "analytics": {},
            "quotes": 0,
        }
    history = await collect_history(
        MARKET,
        days=US_DAILY_LOOKBACK_DAYS,
        codes=codes,
        include_reference=True,
    )
    analytics = await compute_all(
        MARKET,
        codes=codes,
        include_onboarding=True,
        include_restricted=True,
    )
    quotes = await publish_quotes(codes=codes)
    return {
        "session_date": session_date.isoformat(),
        "symbols": len(codes),
        "private_symbols": len(private_codes),
        "restricted_symbols": len(restricted_codes),
        "history": history,
        "analytics": analytics,
        "quotes": quotes,
    }


def main() -> None:
    stats = asyncio.run(refresh_restricted_market_data())
    print(f"[restricted-research] done: {stats}")


if __name__ == "__main__":
    main()
