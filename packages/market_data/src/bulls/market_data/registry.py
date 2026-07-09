"""Market -> provider registry.

THIS is the swap point. To go from scraped/delayed DSE data to a licensed real-time feed, change
one line here — no app, api, or ingestion code changes.
"""

from __future__ import annotations

from bulls.market_data.provider import MarketDataProvider
from bulls.market_data.providers.dse_scrape import DseScrapeProvider
from bulls.market_data.providers.us_yahoo import YahooUsEodProvider

_REGISTRY: dict[str, MarketDataProvider] = {
    "DSE": DseScrapeProvider(),
    # "DSE": DseLicensedProvider(),   # ← swap here when the real-time feed lands
    "US": YahooUsEodProvider(),       # free EOD bootstrap; swap for a licensed feed later
    # "BSE": BseProvider(),           # ← add markets here (Bulls of Mumbai, ...)
}


def get_provider(market: str) -> MarketDataProvider:
    try:
        return _REGISTRY[market]
    except KeyError:
        raise ValueError(f"No market-data provider registered for market {market!r}") from None
