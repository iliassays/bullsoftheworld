"""Private refresh support for explicitly staged exchange-status restricted US equities."""

from __future__ import annotations

from sqlalchemy import select

from bulls.core.db import get_sessionmaker
from bulls.core.models import SecurityMaster, Symbol
from ingestion.analytics import compute_all
from ingestion.history import US_DAILY_LOOKBACK_DAYS
from ingestion.history import collect as collect_history

MARKET = "US"


async def restricted_research_codes() -> list[str]:
    """Return only private common stocks staged under a financial-status restriction."""
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
                    Symbol.is_hidden.is_(True),
                    Symbol.data_status.in_(("onboarding", "degraded")),
                    SecurityMaster.is_active.is_(True),
                    SecurityMaster.is_product_eligible.is_(False),
                    SecurityMaster.instrument_type == "common_stock",
                    SecurityMaster.exclude_reason.like("financial_status_%"),
                )
                .order_by(Symbol.code)
            )
        )


async def refresh_restricted_market_data() -> dict[str, object]:
    """Refresh prices and analytics without publishing hidden names or running agents."""
    codes = await restricted_research_codes()
    if not codes:
        return {"symbols": 0, "history": {}, "analytics": {}}
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
    return {"symbols": len(codes), "history": history, "analytics": analytics}
