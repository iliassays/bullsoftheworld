"""Symbol model — the tradable universe for a market.

Keyed by (market, code). `name_bn` carries the Bangla name for Bulls of Dhaka.
"""

from __future__ import annotations

from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from bulls.core.db import Base


class Symbol(Base):
    __tablename__ = "symbols"

    market: Mapped[str] = mapped_column(String(8), primary_key=True)
    code: Mapped[str] = mapped_column(String(16), primary_key=True)
    name_en: Mapped[str] = mapped_column(String(160))
    name_bn: Mapped[str | None] = mapped_column(String(160))
    sector: Mapped[str | None] = mapped_column(String(80))
    category: Mapped[str | None] = mapped_column(String(2))  # DSE: A/B/G/N/Z
    # is_active: auto-managed by ingestion (seen in scrapes). is_hidden: manual admin override the
    # scraper never touches (e.g. hide bonds/funds). Visible = is_active AND NOT is_hidden.
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_hidden: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
