"""Wire schemas for market data (kept separate from ORM models)."""

from __future__ import annotations

import datetime as dt
from typing import Literal

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


class ResearchChartOverlayPointOut(BaseModel):
    date: dt.date
    value: float


class ResearchChartOverlaySeriesOut(BaseModel):
    key: Literal["ema20", "ema50"]
    label: str
    points: list[ResearchChartOverlayPointOut]


class ResearchChartConditionCheckOut(BaseModel):
    fact_key: str
    label: str
    observed: float | None
    expected: str
    unit: Literal["percent", "multiple"]
    passed: bool | None


class ResearchChartConditionTransitionOut(BaseModel):
    date: dt.date
    close: float
    sequence: int = Field(ge=1)


class ResearchChartConditionOut(BaseModel):
    key: Literal[
        "trend_alignment",
        "participation_expansion",
        "controlled_pullback_context",
    ]
    version: str
    title: str
    short_label: str
    category: str
    state: Literal["observed", "not_observed", "unavailable"]
    summary: str
    why_it_matters: str
    limitation: str
    checks: list[ResearchChartConditionCheckOut]
    transitions: list[ResearchChartConditionTransitionOut]


class VolumeProfileCapabilityOut(BaseModel):
    """Whether a defensible price-by-volume profile can be rendered for this response."""

    status: Literal["available", "unavailable"]
    method: Literal["trade_at_price", "intraday_bar_estimate", "not_available"]
    source_frequency: Literal["trades", "intraday", "none"]
    reason: str


class PublicResearchChartOut(BaseModel):
    """Small, read-only projection of the shared research-condition engine for Portal users."""

    market: str
    code: str
    source_frequency: Literal["completed_daily"]
    price_basis: Literal["corporate_action_adjusted"]
    methodology_version: str
    timeframe: Literal["1d"]
    as_of_date: dt.date | None
    history_start_date: dt.date | None
    disclaimer: str
    overlays: list[ResearchChartOverlaySeriesOut]
    conditions: list[ResearchChartConditionOut]
    volume_profile: VolumeProfileCapabilityOut
