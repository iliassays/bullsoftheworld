"""Symbol model — the tradable universe for a market.

Keyed by (market, code). `name_bn` carries the Bangla name for Bulls of Dhaka.
"""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    String,
    Text,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from bulls.core.db import Base


class Symbol(Base):
    __tablename__ = "symbols"
    __table_args__ = (
        CheckConstraint(
            "data_status IN ('reference_only', 'onboarding', 'ready', 'research_only', 'degraded')",
            name="ck_symbols_data_status",
        ),
        CheckConstraint(
            "research_status IN "
            "('reference_only', 'onboarding', 'ready', 'partial', 'degraded', 'unavailable')",
            name="ck_symbols_research_status",
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
    # `ready` participates in discovery/rankings. `research_only` has a public ticker page but is
    # deliberately excluded from screeners and agents because it failed a non-critical risk gate.
    data_status: Mapped[str] = mapped_column(
        String(20), default="ready", server_default="ready", index=True
    )
    # Atlas readiness is independent of public market-data publication and redistribution rights.
    research_status: Mapped[str] = mapped_column(
        String(20), default="ready", server_default="ready", index=True
    )
    research_status_updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: dt.datetime.now(dt.UTC), server_default=func.now()
    )
    data_first_date: Mapped[dt.date | None] = mapped_column(Date, default=None)
    data_last_date: Mapped[dt.date | None] = mapped_column(Date, default=None)

    @property
    def is_public_research(self) -> bool:
        return (
            self.is_active and not self.is_hidden and self.data_status in {"ready", "research_only"}
        )

    @property
    def is_private_research(self) -> bool:
        return self.is_active and self.research_status in {"ready", "partial"}
