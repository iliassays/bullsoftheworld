"""Wire schemas for market data (kept separate from ORM models)."""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, ConfigDict, Field


class SymbolOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    market: str
    code: str
    name_en: str
    name_bn: str | None = None
    sector: str | None = None
    category: str | None = None
    is_active: bool
    data_status: str


class QuoteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    market: str
    code: str
    ltp: float
    change: float
    change_pct: float
    open: float | None = None
    high: float
    low: float
    close: float
    prev_close: float | None = None
    volume: int
    trades: int
    as_of: dt.datetime
    is_delayed: bool


class SymbolDetail(BaseModel):
    symbol: SymbolOut
    quote: QuoteOut | None = None
    research_limitations: list[str] = Field(default_factory=list)


class BarOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    date: dt.date
    open: float
    high: float
    low: float
    close: float
    volume: int

    @classmethod
    def from_daily_bar(cls, bar) -> BarOut:
        """Return split/distribution-adjusted OHLC when the provider supplies an adjusted close."""
        factor = (
            bar.adjusted_close / bar.close
            if bar.adjusted_close is not None and bar.close > 0
            else 1.0
        )
        return cls(
            date=bar.date,
            open=bar.open * factor,
            high=bar.high * factor,
            low=bar.low * factor,
            close=bar.close * factor,
            volume=bar.volume,
        )
