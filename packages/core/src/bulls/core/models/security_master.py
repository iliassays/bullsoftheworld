"""Security master — raw tradable-instrument identity before product filtering.

`symbols` is the product-facing universe. This table is the market-data control plane: every listed
instrument we know about, including ETFs, common shares, ADRs, preferreds, warrants, rights, units,
test issues, and inactive rows. Large markets need this layer so raw exchange listings never leak
directly into retail UX.
"""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import Boolean, DateTime, Index, Integer, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from bulls.core.db import Base


class SecurityMaster(Base):
    __tablename__ = "security_master"
    __table_args__ = (
        Index("ix_security_master_market_eligible", "market", "is_product_eligible"),
        Index("ix_security_master_market_instrument", "market", "instrument_type"),
        Index("ix_security_master_market_exchange", "market", "exchange"),
        Index("ix_security_master_cik", "cik"),
    )

    security_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        nullable=False,
        unique=True,
        index=True,
        server_default=func.gen_random_uuid(),
    )
    market: Mapped[str] = mapped_column(String(8), primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), primary_key=True)
    raw_symbol: Mapped[str] = mapped_column(String(32))
    security_name: Mapped[str] = mapped_column(Text)
    exchange: Mapped[str | None] = mapped_column(String(32))
    exchange_tier: Mapped[str | None] = mapped_column(String(48))
    cqs_symbol: Mapped[str | None] = mapped_column(String(32))
    nasdaq_symbol: Mapped[str | None] = mapped_column(String(32))
    cik: Mapped[int | None] = mapped_column(Integer)
    instrument_type: Mapped[str] = mapped_column(String(32))
    is_etf: Mapped[bool] = mapped_column(Boolean, default=False)
    is_test_issue: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_product_eligible: Mapped[bool] = mapped_column(Boolean, default=False)
    exclude_reason: Mapped[str | None] = mapped_column(String(64))
    round_lot_size: Mapped[int | None] = mapped_column(Integer)
    financial_status: Mapped[str | None] = mapped_column(String(8))
    source: Mapped[str] = mapped_column(String(32))
    source_file: Mapped[str] = mapped_column(String(32))
    first_seen_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_seen_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
