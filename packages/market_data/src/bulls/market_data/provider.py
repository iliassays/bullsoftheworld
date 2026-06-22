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


@runtime_checkable
class MarketDataProvider(Protocol):
    """Implemented per market. `subscribe` is optional (Protocol members can be absent)."""

    market: str

    async def list_symbols(self) -> list[Symbol]: ...

    async def get_quotes(self, codes: list[str]) -> list[Quote]: ...

    async def get_daily_bars(self, code: str, start: dt.date, end: dt.date) -> list[Bar]: ...

    # Optional live push. Providers without it (e.g. the scraper) are polled instead.
    # def subscribe(self, codes: list[str], on_tick: Callable[[Quote], None]) -> Unsubscribe: ...
