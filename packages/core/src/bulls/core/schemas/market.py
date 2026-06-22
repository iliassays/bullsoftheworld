"""Wire schemas for market data (kept separate from ORM models)."""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, ConfigDict


class SymbolOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    market: str
    code: str
    name_en: str
    name_bn: str | None = None
    sector: str | None = None
    category: str | None = None
    is_active: bool


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
