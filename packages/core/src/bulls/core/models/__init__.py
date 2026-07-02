"""ORM models. Import all here so Alembic autogenerate sees them."""

from bulls.core.models.announcement import Announcement
from bulls.core.models.company import (
    AnnualFinancial,
    CompanyProfile,
    DividendRecord,
    SectorPE,
    ShareholdingSnapshot,
)
from bulls.core.models.company_logo import CompanyLogo
from bulls.core.models.follow import Follow
from bulls.core.models.market_summary import MarketSummary
from bulls.core.models.moderation_event import ModerationEvent
from bulls.core.models.page_view_event import PageViewEvent
from bulls.core.models.post import Cashtag, Post, PostReaction
from bulls.core.models.quote import DailyBar, QuoteSnapshot
from bulls.core.models.signal_event import SignalEvent
from bulls.core.models.symbol import Symbol
from bulls.core.models.ticker_analytics import TickerAnalytics
from bulls.core.models.ticker_buzz_daily import TickerBuzzDaily
from bulls.core.models.trending import TrendingScore
from bulls.core.models.user import User
from bulls.core.models.watchlist import WatchlistItem

__all__ = [
    "Announcement",
    "AnnualFinancial",
    "Cashtag",
    "CompanyLogo",
    "CompanyProfile",
    "DailyBar",
    "DividendRecord",
    "Follow",
    "MarketSummary",
    "ModerationEvent",
    "PageViewEvent",
    "Post",
    "PostReaction",
    "QuoteSnapshot",
    "SectorPE",
    "ShareholdingSnapshot",
    "SignalEvent",
    "Symbol",
    "TickerAnalytics",
    "TickerBuzzDaily",
    "TrendingScore",
    "User",
    "WatchlistItem",
]
