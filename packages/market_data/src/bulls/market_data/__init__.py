"""bulls.market_data — the only thing the app talks to for prices.

Swapping the DSE scraper for a licensed real-time feed = one change in `registry.py`.
"""

from bulls.market_data.provider import (
    Bar,
    MarketDataProvider,
    Quote,
    Symbol,
)
from bulls.market_data.registry import get_provider

__all__ = ["Bar", "MarketDataProvider", "Quote", "Symbol", "get_provider"]
