"""Market metadata shared by API, ingestion, analytics, and UI contracts.

The database is already keyed by ``market``. This module gives that key real semantics: currency,
timezone, benchmark labels, settlement, and feature availability. DSE remains the default so the
current product behavior is unchanged; US is intentionally a profile only until a provider is wired.
"""

from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass, field
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class MarketFeatures:
    intraday_quotes: bool = False
    curated_screens: bool = False
    strategy_scanner: bool = False
    official_disclosures: bool = False
    company_fundamentals: bool = False
    automated_desks: bool = False
    learning_quiz: bool = False
    interpreted_analytics: bool = False
    price_alerts: bool = False
    dse_categories: bool = False
    circuit_breakers: bool = False
    shareholding_breakdown: bool = False
    sponsor_director_disclosures: bool = False
    block_trades: bool = False
    sec_filings: bool = False
    institutional_holdings: bool = False
    finra_short_volume: bool = False
    extended_hours: bool = False
    security_master_product_gate: bool = False


@dataclass(frozen=True)
class MoneyUnit:
    min_value_mn: float
    divisor_mn: float
    suffix: str
    decimals: int


@dataclass(frozen=True)
class MarketProfile:
    market: str
    exchange_code: str
    exchange_label_bn: str | None
    exchange_name: str
    exchange_name_bn: str | None
    country_code: str
    currency_code: str
    currency_symbol: str
    timezone: str
    timezone_label: str
    place_label_en: str
    place_label_bn: str
    open_time: dt.time
    close_time: dt.time
    analytics_ready_utc: dt.time
    trading_isoweekdays: frozenset[int]
    holidays: frozenset[dt.date] = field(default_factory=frozenset)
    early_closes: dict[dt.date, dt.time] = field(default_factory=dict)
    settlement_cycle: str = "T+2"
    benchmark_label: str = "Market"
    default_locale: str = "en"
    price_alert_evaluation: str = "session_close"
    price_decimals: int = 2
    compact_money_units: tuple[MoneyUnit, ...] = field(default_factory=tuple)
    market_cap_money_units: tuple[MoneyUnit, ...] = field(default_factory=tuple)
    # Ordered (tier, inclusive lower bound in currency-millions), largest first. The single
    # source of truth for size classification — plain-read prose, screener filters, browse pages
    # and onboarding bands must all derive from this, never restate thresholds locally.
    # Calibrated against the live market_cap_mn distribution (2026-07); boundaries are
    # market-specific because a "large" Dhaka company is a micro-cap in dollars.
    cap_tiers: tuple[tuple[str, float], ...] = field(default_factory=tuple)
    features: MarketFeatures = field(default_factory=MarketFeatures)

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)

    def exchange_label(self, lang: str = "en") -> str:
        if lang == "bn" and self.exchange_label_bn:
            return self.exchange_label_bn
        return self.exchange_code

    def exchange_name_label(self, lang: str = "en") -> str:
        if lang == "bn" and self.exchange_name_bn:
            return self.exchange_name_bn
        return self.exchange_name

    def place_label(self, lang: str = "en") -> str:
        return self.place_label_bn if lang == "bn" else self.place_label_en

    def close_time_on(self, date: dt.date) -> dt.time:
        return self.early_closes.get(date, self.close_time)


DSE_HOLIDAYS_2026: frozenset[dt.date] = frozenset(
    {
        dt.date(2026, 7, 1),  # DSE confirmed closed; keep this list conservative.
    }
)

# Verified against the official NYSE 2025-2026 holiday and early-close calendars. Keep the
# worker's verified-year gate closed until each additional full year is reviewed and added here.
US_HOLIDAYS_2025_2026: frozenset[dt.date] = frozenset(
    {
        dt.date(2025, 1, 1),
        dt.date(2025, 1, 20),
        dt.date(2025, 2, 17),
        dt.date(2025, 4, 18),
        dt.date(2025, 5, 26),
        dt.date(2025, 6, 19),
        dt.date(2025, 7, 4),
        dt.date(2025, 9, 1),
        dt.date(2025, 11, 27),
        dt.date(2025, 12, 25),
        dt.date(2026, 1, 1),
        dt.date(2026, 1, 19),
        dt.date(2026, 2, 16),
        dt.date(2026, 4, 3),
        dt.date(2026, 5, 25),
        dt.date(2026, 6, 19),
        dt.date(2026, 7, 3),
        dt.date(2026, 9, 7),
        dt.date(2026, 11, 26),
        dt.date(2026, 12, 25),
    }
)
US_EARLY_CLOSES_2025_2026: dict[dt.date, dt.time] = {
    dt.date(2025, 7, 3): dt.time(13, 0),
    dt.date(2025, 11, 28): dt.time(13, 0),
    dt.date(2025, 12, 24): dt.time(13, 0),
    dt.date(2026, 11, 27): dt.time(13, 0),
    dt.date(2026, 12, 24): dt.time(13, 0),
}
US_VERIFIED_CALENDAR_YEARS = frozenset({2025, 2026})


MARKET_PROFILES: dict[str, MarketProfile] = {
    "DSE": MarketProfile(
        market="DSE",
        exchange_code="DSE",
        exchange_label_bn="ডিএসই",
        exchange_name="Dhaka Stock Exchange",
        exchange_name_bn="ঢাকা স্টক এক্সচেঞ্জ",
        country_code="BD",
        currency_code="BDT",
        currency_symbol="৳",
        timezone="Asia/Dhaka",
        timezone_label="BDT",
        place_label_en="Dhaka",
        place_label_bn="ঢাকা",
        open_time=dt.time(10, 0),
        close_time=dt.time(14, 30),
        # EOD analytics cron: 13:15 UTC, after bars and the market summary land.
        analytics_ready_utc=dt.time(13, 15),
        trading_isoweekdays=frozenset({7, 1, 2, 3, 4}),
        holidays=DSE_HOLIDAYS_2026,
        settlement_cycle="T+2",
        benchmark_label="DSEX",
        default_locale="bn",
        price_alert_evaluation="delayed_quote",
        price_decimals=1,
        compact_money_units=(
            MoneyUnit(min_value_mn=10, divisor_mn=10, suffix="cr", decimals=1),
            MoneyUnit(min_value_mn=0, divisor_mn=0.1, suffix="L", decimals=0),
        ),
        market_cap_money_units=(
            MoneyUnit(min_value_mn=0, divisor_mn=10, suffix=" Cr", decimals=0),
        ),
        # ৳ millions. Live distribution (395 names, 2026-07): large 69 / mid 165 / small 137 /
        # micro 24. No mega tier — DSE's largest is ~৳35k Cr.
        cap_tiers=(
            ("large", 10_000.0),  # ≥ ৳1,000 Cr
            ("mid", 2_000.0),  # ৳200-1,000 Cr
            ("small", 500.0),  # ৳50-200 Cr
            ("micro", 0.0),  # < ৳50 Cr
        ),
        features=MarketFeatures(
            intraday_quotes=True,
            curated_screens=True,
            strategy_scanner=True,
            official_disclosures=True,
            company_fundamentals=True,
            automated_desks=True,
            learning_quiz=True,
            interpreted_analytics=True,
            price_alerts=True,
            dse_categories=True,
            circuit_breakers=True,
            shareholding_breakdown=True,
            sponsor_director_disclosures=True,
            block_trades=True,
        ),
    ),
    "US": MarketProfile(
        market="US",
        exchange_code="US",
        exchange_label_bn="যুক্তরাষ্ট্রের শেয়ারবাজার",
        exchange_name="U.S. equities",
        exchange_name_bn="যুক্তরাষ্ট্রের শেয়ারবাজার",
        country_code="US",
        currency_code="USD",
        currency_symbol="$",
        timezone="America/New_York",
        timezone_label="ET",
        place_label_en="New York",
        place_label_bn="নিউ ইয়র্ক",
        open_time=dt.time(9, 30),
        close_time=dt.time(16, 0),
        # First US EOD publication attempt: 22:45 UTC, 1h45-2h45 after the regular close.
        analytics_ready_utc=dt.time(22, 45),
        trading_isoweekdays=frozenset({1, 2, 3, 4, 5}),
        holidays=US_HOLIDAYS_2025_2026,
        early_closes=US_EARLY_CLOSES_2025_2026,
        settlement_cycle="T+1",
        # The free EOD adapter stores SPY, not the cash S&P 500 index. Never present an ETF price
        # as the index level; relative-return comparisons remain valid when both use SPY.
        benchmark_label="SPY (S&P 500 ETF)",
        default_locale="en",
        price_alert_evaluation="session_close",
        price_decimals=2,
        compact_money_units=(
            MoneyUnit(min_value_mn=1000, divisor_mn=1000, suffix="B", decimals=1),
            MoneyUnit(min_value_mn=0, divisor_mn=1, suffix="M", decimals=1),
        ),
        market_cap_money_units=(
            MoneyUnit(min_value_mn=1000, divisor_mn=1000, suffix="B", decimals=1),
            MoneyUnit(min_value_mn=0, divisor_mn=1, suffix="M", decimals=0),
        ),
        # $ millions. Standard US buckets; small/mid bounds intentionally match the onboarding
        # DiscoveryPolicy bands so a stock's browse tier and its onboarding band never disagree.
        cap_tiers=(
            ("mega", 200_000.0),  # ≥ $200B
            ("large", 10_000.0),  # $10-200B
            ("mid", 2_000.0),  # $2-10B
            ("small", 300.0),  # $300M-2B
            ("micro", 0.0),  # < $300M
        ),
        features=MarketFeatures(
            curated_screens=True,
            strategy_scanner=True,
            official_disclosures=True,
            company_fundamentals=True,
            automated_desks=True,
            learning_quiz=True,
            interpreted_analytics=True,
            price_alerts=True,
            sec_filings=True,
            institutional_holdings=True,
            finra_short_volume=True,
            security_master_product_gate=True,
        ),
    ),
}


def get_market_profile(market: str | None) -> MarketProfile:
    key = (market or "DSE").upper()
    try:
        return MARKET_PROFILES[key]
    except KeyError:
        raise ValueError(f"Unknown market profile {market!r}") from None


def is_market_session(date: dt.date, market: str | None) -> bool:
    """Return whether ``date`` is a configured exchange session."""

    profile = get_market_profile(market)
    return date.isoweekday() in profile.trading_isoweekdays and date not in profile.holidays


def add_market_sessions(date: dt.date, sessions: int, market: str | None) -> dt.date:
    """Resolve a contractual T+n date from the shared exchange calendar."""

    if sessions < 0:
        raise ValueError("sessions must be non-negative")
    resolved = date
    remaining = sessions
    while remaining:
        resolved += dt.timedelta(days=1)
        if is_market_session(resolved, market):
            remaining -= 1
    return resolved


def cap_tier(market_cap_mn: float | None, market: str | None) -> str | None:
    """Canonical size tier for a market cap, or None when it can't be classified honestly.

    Boundaries are inclusive lower bounds: a cap exactly on a boundary belongs to the tier above
    (৳1,000 Cr is large, not mid). None/zero/negative/non-finite caps return None — the caller
    must present that as "unclassified", never guess a tier (omit-over-mislead).
    """
    if market_cap_mn is None or not math.isfinite(market_cap_mn) or market_cap_mn <= 0:
        return None
    for tier, lower_bound_mn in get_market_profile(market).cap_tiers:
        if market_cap_mn >= lower_bound_mn:
            return tier
    return None


def format_price(value: float | None, market: str | None = "DSE") -> str:
    if value is None:
        return "—"
    profile = get_market_profile(market)
    return f"{profile.currency_symbol}{value:,.{profile.price_decimals}f}"


def format_money_millions(
    value_mn: float | None,
    market: str | None = "DSE",
    *,
    style: str = "compact",
    none: str = "—",
) -> str:
    if value_mn is None:
        return none
    profile = get_market_profile(market)
    units = profile.market_cap_money_units if style == "market_cap" else profile.compact_money_units
    if not units:
        return f"{profile.currency_symbol}{value_mn:,.1f}mn"
    unit = next((u for u in units if value_mn >= u.min_value_mn), units[-1])
    scaled = value_mn / unit.divisor_mn
    return f"{profile.currency_symbol}{scaled:,.{unit.decimals}f}{unit.suffix}"
