"""Symbol model — the tradable universe for a market.

Keyed by (market, code). `name_bn` carries the Bangla name for Bulls of Dhaka.
"""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import Boolean, CheckConstraint, Date, ForeignKey, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from bulls.core.db import Base


class Symbol(Base):
    __tablename__ = "symbols"
    __table_args__ = (
        CheckConstraint(
            "data_status IN ('reference_only', 'onboarding', 'ready', 'degraded')",
            name="ck_symbols_data_status",
        ),
    )

    security_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("security_master.security_id"),
        nullable=True,
        index=True,
    )
    market: Mapped[str] = mapped_column(String(8), primary_key=True)
    code: Mapped[str] = mapped_column(String(16), primary_key=True)
    # Exchange issuer names can legitimately exceed 160 characters. Keep the full official name;
    # compact presentation belongs in the UI, not in the identity layer.
    name_en: Mapped[str] = mapped_column(Text)
    name_bn: Mapped[str | None] = mapped_column(String(160))
    sector: Mapped[str | None] = mapped_column(String(80))
    category: Mapped[str | None] = mapped_column(String(2))  # DSE: A/B/G/N/Z
    # is_active: auto-managed by ingestion (seen in scrapes). is_hidden: manual admin override the
    # scraper never touches (e.g. hide bonds/funds). Visible = is_active AND NOT is_hidden.
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_hidden: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    # Reference ingestion and price onboarding are separate. Only `ready` symbols are public.
    data_status: Mapped[str] = mapped_column(
        String(20), default="ready", server_default="ready", index=True
    )
    data_first_date: Mapped[dt.date | None] = mapped_column(Date, default=None)
    data_last_date: Mapped[dt.date | None] = mapped_column(Date, default=None)

    @property
    def is_retail_ready(self) -> bool:
        return self.is_active and not self.is_hidden and self.data_status == "ready"
