"""Bounded refresh support for high-risk and staged US equity research."""

from __future__ import annotations

import asyncio

from sqlalchemy import and_, or_, select

from bulls.core.db import get_sessionmaker
from bulls.core.models import SecurityMaster, Symbol
from ingestion.analytics import compute_all
from ingestion.history import US_DAILY_LOOKBACK_DAYS
from ingestion.history import collect as collect_history
from ingestion.us_eod_snapshot import publish_quotes

MARKET = "US"


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
    """Refresh prices and analytics without feeding Ideas, agents, or market aggregates."""
    codes = await restricted_research_codes()
    if not codes:
        return {"symbols": 0, "history": {}, "analytics": {}, "quotes": 0}
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
        "symbols": len(codes),
        "history": history,
        "analytics": analytics,
        "quotes": quotes,
    }


def main() -> None:
    stats = asyncio.run(refresh_restricted_market_data())
    print(f"[restricted-research] done: {stats}")


if __name__ == "__main__":
    main()
