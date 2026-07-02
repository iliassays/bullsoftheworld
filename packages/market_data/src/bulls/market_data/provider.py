"""The MarketDataProvider interface and its value types.

The app only ever sees Symbol / Quote / Bar — never DSE, never a scraper. A provider that can't
push live data simply omits `subscribe()`; the ingestion service then polls it on a schedule.

Honesty rule: every Quote carries `is_delayed` + `as_of`. The UI shows it. We never imply live
prices we don't have.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from typing import Protocol, runtime_checkable

from pydantic import BaseModel

Unsubscribe = Callable[[], None]


class Symbol(BaseModel):
    market: str
    code: str
    name_en: str
    name_bn: str | None = None
    sector: str | None = None
    category: str | None = None


class Quote(BaseModel):
    market: str
    code: str
    ltp: float  # last traded price
    change: float
    change_pct: float
    open: float | None = None  # not published on DSE's latest-price page
    high: float
    low: float
    close: float
    prev_close: float | None = None  # YCP — yesterday's close
    volume: int
    trades: int
    as_of: dt.datetime  # when we read it; pair with is_delayed
    is_delayed: bool  # surfaced in the UI — never lie about freshness


class Bar(BaseModel):
    market: str
    code: str
    date: dt.date
    open: float
    high: float
    low: float
    close: float
    volume: int


class MarketSummary(BaseModel):
    """Market-wide EOD aggregate for one trading day — index levels, turnover, breadth.

    Symbol-agnostic: one row per (market, date). Lets the app tell whether a stock's move was
    idiosyncratic or the whole market moving (relative strength, turnover trend, sentiment base).
    """

    market: str
    date: dt.date
    dsex: float | None = None  # broad index
    dsex_change: float | None = None
    ds30: float | None = None  # blue-chip index
    ds30_change: float | None = None
    total_trade: int | None = None
    total_value_mn: float | None = None  # turnover, Taka millions
    total_volume: int | None = None
    total_market_cap_mn: float | None = None  # Taka millions


class Shareholding(BaseModel):
    """Ownership breakdown as of one disclosure date (sums to ~100%). Slow-moving; one per filing."""

    market: str
    code: str
    as_of_date: dt.date  # the disclosure date the exchange published ('as on ...'), not scrape time
    sponsor_director: float | None = None
    govt: float | None = None
    institute: float | None = None
    foreign_pct: float | None = None  # 'foreign' is a SQL reserved word — keep the column queryable
    public: float | None = None


class CompanyProfile(BaseModel):
    """Slow-moving company reference + fundamentals from the exchange's company page.

    Structural (capital, float, sector) plus the latest declared dividend. Updated rarely (post-AGM /
    on record date), so this is reference data, not a market quote — `fetched_at` records the read.
    """

    market: str
    code: str
    sector: str | None = None
    market_category: str | None = None  # A / B / N / Z
    instrument_type: str | None = None  # Equity / Mutual Funds / ...
    listing_year: int | None = None
    face_value: float | None = None
    market_lot: int | None = None
    authorized_capital_mn: float | None = None
    paid_up_capital_mn: float | None = None
    outstanding_shares: int | None = None
    market_cap_mn: float | None = None
    free_float_mcap_mn: float | None = None
    year_end: str | None = None  # e.g. '31-Dec'
    latest_dividend: str | None = None  # raw, e.g. '27.00, 3%B for 2025'
    cash_dividend_pct: float | None = None  # parsed cash %, of face value (27.0 from the above)
    eps: float | None = None  # latest full-year EPS (continuing ops, basic)
    nav_per_share: float | None = None  # latest full-year net asset value per share
    short_term_loan_mn: float | None = None
    long_term_loan_mn: float | None = None
    reserve_surplus_mn: float | None = None  # retained earnings + reserves (book-value strength)
    oci_mn: float | None = None
    credit_rating_long: str | None = None  # often blank on dsebd; captured when present
    credit_rating_short: str | None = None
    operational_status: str | None = None


class AnnualFinancial(BaseModel):
    """One fiscal year of headline fundamentals — the series powers EPS/NAV growth factors."""

    market: str
    code: str
    fiscal_year: int
    eps: float | None = None
    nav_per_share: float | None = None
    profit_mn: float | None = None


class DividendRecord(BaseModel):
    """Declared dividend for one year — the series powers dividend consistency/growth factors."""

    market: str
    code: str
    year: int
    cash_pct: float | None = None  # % of face value
    bonus_pct: float | None = None  # stock dividend %


class SectorPE(BaseModel):
    """Sector-wide median P/E for relative valuation (cheap vs its sector, not just absolute)."""

    market: str
    sector: str
    median_pe: float | None = None


class CompanyInfo(BaseModel):
    """What the company page yields in one fetch: profile + shareholding/financial/dividend history."""

    profile: CompanyProfile
    shareholdings: list[Shareholding] = []
    financials: list[AnnualFinancial] = []
    dividends: list[DividendRecord] = []


class NewsItem(BaseModel):
    """One raw news/announcement row from the exchange — classified downstream at onboarding."""

    code: str
    published_at: dt.date
    headline: str
    body: str = ""  # full announcement text — decoded into structured fields at onboarding


@runtime_checkable
class MarketDataProvider(Protocol):
    """Implemented per market. `subscribe` is optional (Protocol members can be absent)."""

    market: str

    async def list_symbols(self) -> list[Symbol]: ...

    async def get_quotes(self, codes: list[str]) -> list[Quote]: ...

    async def get_daily_bars(self, code: str, start: dt.date, end: dt.date) -> list[Bar]: ...

    async def get_market_summary(self, start: dt.date, end: dt.date) -> list[MarketSummary]: ...

    async def get_company(self, code: str) -> CompanyInfo | None: ...

    async def get_sector_pe(self) -> list[SectorPE]: ...

    async def get_news(self, start: dt.date, end: dt.date) -> list[NewsItem]: ...

    # Optional historical archive for one-shot backfill (live get_news often only returns recent
    # items). Providers without it fall back to get_news.
    # async def get_news_archive(self, start: dt.date, end: dt.date) -> list[NewsItem]: ...

    # Optional live push. Providers without it (e.g. the scraper) are polled instead.
    # def subscribe(self, codes: list[str], on_tick: Callable[[Quote], None]) -> Unsubscribe: ...
