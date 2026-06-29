"""Daily 'Watch today' ranking — stocks whose trading activity is unusual for themselves.

Precomputed nightly by the ingestion worker (the scoring is heavy; the frontend just reads the
ordered list). The score is a self-normalized volume + turnover surge — the only signals that
carried out-of-sample edge in the Phase-0 backtest. `reasons` holds language-neutral chip data
(volume multiple, turnover, 52-week proximity, move size); the frontend renders the human text per
locale. Descriptive only — this is 'what was unusually active', never a recommendation.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from sqlalchemy import Boolean, Date, DateTime, Float, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from bulls.core.db import Base


class TrendingScore(Base):
    __tablename__ = "trending_scores"

    market: Mapped[str] = mapped_column(String(8), primary_key=True)
    code: Mapped[str] = mapped_column(String(16), primary_key=True)
    as_of_date: Mapped[dt.date] = mapped_column(Date, index=True)
    rank: Mapped[int] = mapped_column(Integer, index=True)
    score: Mapped[float] = mapped_column(Float)  # composite activity z (vol + turnover surge)
    change_pct: Mapped[float] = mapped_column(Float)
    direction: Mapped[str] = mapped_column(String(4))  # up / down / flat
    heating_up: Mapped[bool] = mapped_column(Boolean, default=False)
    reasons: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)  # chip data, frontend renders text
    computed_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
