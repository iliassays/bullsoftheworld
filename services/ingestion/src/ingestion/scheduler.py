"""Ingestion scheduler (build step 2).

Polls each registered MarketDataProvider on its cadence, writes snapshots to Postgres, and
publishes ticks to Redis. Providers WITHOUT subscribe() (the scraper) are polled here; a future
licensed provider with subscribe() pushes instead. The rest of the system can't tell the
difference — it just reads quotes / listens on Redis.

STATUS: STUB.
"""

from __future__ import annotations

from bulls.market_data import get_provider


async def poll_market(market: str) -> None:
    provider = get_provider(market)
    # step 2: codes = active symbols; quotes = await provider.get_quotes(codes)
    #         persist quotes; publish each to Redis channel sym:<market>:<code>
    _ = provider
    raise NotImplementedError("step 2: poll provider, persist, publish")
