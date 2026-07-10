"""ORM models. Import all here so Alembic autogenerate sees them."""

from bulls.core.models.agent_portfolio import AgentLot, AgentPortfolio, AgentTrade
from bulls.core.models.alert import AlertEvent, PriceAlert
from bulls.core.models.announcement import Announcement
from bulls.core.models.block_trade import BlockTrade
from bulls.core.models.company import (
    AnnualFinancial,
    CompanyProfile,
    DividendRecord,
    SectorPE,
    ShareholdingSnapshot,
)
from bulls.core.models.company_logo import CompanyLogo
from bulls.core.models.follow import Follow
from bulls.core.models.knowledge import KnowledgeChunk
from bulls.core.models.market_summary import MarketSummary
from bulls.core.models.moderation_event import ModerationEvent
from bulls.core.models.page_view_event import PageViewEvent
from bulls.core.models.portfolio import PortfolioHolding, PortfolioSnapshot
from bulls.core.models.post import Cashtag, Post, PostReaction
from bulls.core.models.quiz import QuizAnswer, QuizQuestion
from bulls.core.models.quote import DailyBar, QuoteSnapshot
from bulls.core.models.refresh_session import RefreshSession
from bulls.core.models.sec import (
    InstitutionalHoldingSummary,
    InstitutionalManager,
    InstitutionalPosition,
    RegulatoryDataState,
    SecFiling,
    SecFinancialFact,
    SecurityIdentifier,
)
from bulls.core.models.security_master import SecurityMaster
from bulls.core.models.signal_event import SignalEvent
from bulls.core.models.symbol import Symbol
from bulls.core.models.ticker_analytics import TickerAnalytics
from bulls.core.models.ticker_buzz_daily import TickerBuzzDaily
from bulls.core.models.ticker_pattern import TickerPattern
from bulls.core.models.trending import TrendingScore
from bulls.core.models.user import User
from bulls.core.models.watchlist import WatchlistItem

__all__ = [
    "AgentLot",
    "AgentPortfolio",
    "AgentTrade",
    "AlertEvent",
    "Announcement",
    "AnnualFinancial",
    "BlockTrade",
    "Cashtag",
    "CompanyLogo",
    "CompanyProfile",
    "DailyBar",
    "DividendRecord",
    "Follow",
    "InstitutionalHoldingSummary",
    "InstitutionalManager",
    "InstitutionalPosition",
    "KnowledgeChunk",
    "MarketSummary",
    "ModerationEvent",
    "PageViewEvent",
    "PortfolioHolding",
    "PortfolioSnapshot",
    "Post",
    "PostReaction",
    "PriceAlert",
    "QuizAnswer",
    "QuizQuestion",
    "QuoteSnapshot",
    "RefreshSession",
    "RegulatoryDataState",
    "SecFiling",
    "SecFinancialFact",
    "SectorPE",
    "SecurityIdentifier",
    "SecurityMaster",
    "ShareholdingSnapshot",
    "SignalEvent",
    "Symbol",
    "TickerAnalytics",
    "TickerBuzzDaily",
    "TickerPattern",
    "TrendingScore",
    "User",
    "WatchlistItem",
]
