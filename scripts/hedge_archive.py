"""Point-in-time daily publications for the private Quality Reversal monitor."""

from __future__ import annotations

import hashlib
import json

from hedge_history import STRATEGY_KEY
from sqlalchemy import select

from bulls.core.db import bind_tenant_context, get_sessionmaker
from bulls.core.models import HedgeDailyScanSnapshot

TENANT_ID = "bullsofdhaka"
MARKET = "DSE"


def content_hash(payload: dict) -> str:
    """Stable evidence fingerprint for one JSON-safe monitor publication."""
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


async def read_daily_snapshots(
    *,
    tenant_id: str = TENANT_ID,
    market: str = MARKET,
    limit: int = 60,
) -> list[HedgeDailyScanSnapshot]:
    """Newest daily publications first. HTTP uses this bounded read only."""
    async with get_sessionmaker()() as session:
        await bind_tenant_context(session, tenant_id)
        return list(
            await session.scalars(
                select(HedgeDailyScanSnapshot)
                .where(
                    HedgeDailyScanSnapshot.tenant_id == tenant_id,
                    HedgeDailyScanSnapshot.market == market,
                    HedgeDailyScanSnapshot.strategy == STRATEGY_KEY,
                )
                .order_by(HedgeDailyScanSnapshot.as_of_date.desc())
                .limit(max(1, min(limit, 250)))
            )
        )
