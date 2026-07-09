"""Market metadata shared by API, ingestion, analytics, and UI contracts.

The database is already keyed by ``market``. This module gives that key real semantics: currency,
timezone, benchmark labels, settlement, and feature availability. DSE remains the default so the
current product behavior is unchanged; US is intentionally a profile only until a provider is wired.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class MarketFeatures:
    dse_categories: bool = False
    circuit_breakers: bool = False
    shareholding_breakdown: bool = False
    sponsor_director_disclosures: bool = False
    block_trades: bool = False
    sec_filings: bool = False
    extended_hours: bool = False


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
    trading_isoweekdays: frozenset[int]
    holidays: frozenset[dt.date] = field(default_factory=frozenset)
    settlement_cycle: str = "T+2"
    benchmark_label: str = "Market"
    default_locale: str = "en"
    price_decimals: int = 2
    compact_money_units: tuple[MoneyUnit, ...] = field(default_factory=tuple)
    market_cap_money_units: tuple[MoneyUnit, ...] = field(default_factory=tuple)
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


DSE_HOLIDAYS_2026: frozenset[dt.date] = frozenset(
    {
        dt.date(2026, 7, 1),  # DSE confirmed closed; keep this list conservative.
    }
)

# Seeded with the standard NYSE/Nasdaq full-day holidays for 2026. Early closes are not modeled yet;
# the US provider should still mark quote freshness honestly through Quote.is_delayed/as_of.
US_HOLIDAYS_2026: frozenset[dt.date] = frozenset(
    {
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
        trading_isoweekdays=frozenset({7, 1, 2, 3, 4}),
        holidays=DSE_HOLIDAYS_2026,
        settlement_cycle="T+2",
        benchmark_label="DSEX",
        default_locale="bn",
        price_decimals=1,
        compact_money_units=(
            MoneyUnit(min_value_mn=10, divisor_mn=10, suffix="cr", decimals=1),
            MoneyUnit(min_value_mn=0, divisor_mn=0.1, suffix="L", decimals=0),
        ),
        market_cap_money_units=(
            MoneyUnit(min_value_mn=0, divisor_mn=10, suffix=" Cr", decimals=0),
        ),
        features=MarketFeatures(
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
        trading_isoweekdays=frozenset({1, 2, 3, 4, 5}),
        holidays=US_HOLIDAYS_2026,
        settlement_cycle="T+1",
        benchmark_label="S&P 500",
        default_locale="en",
        price_decimals=2,
        compact_money_units=(
            MoneyUnit(min_value_mn=1000, divisor_mn=1000, suffix="B", decimals=1),
            MoneyUnit(min_value_mn=0, divisor_mn=1, suffix="M", decimals=1),
        ),
        market_cap_money_units=(
            MoneyUnit(min_value_mn=1000, divisor_mn=1000, suffix="B", decimals=1),
            MoneyUnit(min_value_mn=0, divisor_mn=1, suffix="M", decimals=0),
        ),
        features=MarketFeatures(sec_filings=True, extended_hours=True),
    ),
}


def get_market_profile(market: str | None) -> MarketProfile:
    key = (market or "DSE").upper()
    try:
        return MARKET_PROFILES[key]
    except KeyError:
        raise ValueError(f"Unknown market profile {market!r}") from None


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
