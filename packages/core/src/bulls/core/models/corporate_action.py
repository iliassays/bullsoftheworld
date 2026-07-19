"""Verified exchange corporate actions and their price-adjustment lineage."""

from __future__ import annotations

import datetime as dt
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    Index,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from bulls.core.db import Base


class CorporateAction(Base):
    """One verified bonus or rights entitlement with reproducible adjustment inputs.

    Cash dividends and every other action type are intentionally outside the first DSE policy.
    The raw daily close remains immutable; this row explains the derived ``adjusted_close`` series.
    """

    __tablename__ = "corporate_actions"
    __table_args__ = (
        UniqueConstraint(
            "market",
            "code",
            "action_type",
            "record_date",
            name="uq_corporate_actions_security_record_type",
        ),
        CheckConstraint(
            "action_type IN ('bonus', 'rights')",
            name="ck_corporate_actions_type",
        ),
        CheckConstraint(
            "status IN ('verified', 'applied')",
            name="ck_corporate_actions_status",
        ),
        CheckConstraint(
            "(action_type = 'bonus' AND bonus_ratio > 0 AND rights_ratio IS NULL "
            "AND rights_subscription_price IS NULL) OR "
            "(action_type = 'rights' AND bonus_ratio IS NULL AND rights_ratio > 0 "
            "AND rights_subscription_price >= 0)",
            name="ck_corporate_actions_terms",
        ),
        CheckConstraint(
            "adjustment_factor IS NULL OR adjustment_factor > 0",
            name="ck_corporate_actions_factor",
        ),
        CheckConstraint(
            "(status = 'verified') OR (effective_session IS NOT NULL "
            "AND reference_close > 0 AND adjustment_factor > 0)",
            name="ck_corporate_actions_applied_shape",
        ),
        Index("ix_corporate_actions_security_effective", "market", "code", "effective_session"),
        Index("ix_corporate_actions_record_date", "market", "record_date"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    market: Mapped[str] = mapped_column(String(8))
    code: Mapped[str] = mapped_column(String(16))
    action_type: Mapped[str] = mapped_column(String(12))
    record_date: Mapped[dt.date] = mapped_column(Date)
    effective_session: Mapped[dt.date | None] = mapped_column(Date)
    bonus_ratio: Mapped[float | None] = mapped_column(Float)
    rights_ratio: Mapped[float | None] = mapped_column(Float)
    rights_subscription_price: Mapped[float | None] = mapped_column(Float)
    reference_close: Mapped[float | None] = mapped_column(Float)
    adjustment_factor: Mapped[float | None] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(12), default="verified", server_default="verified")
    source_announcement_ids: Mapped[list[int]] = mapped_column(JSONB)
    known_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    calculation_version: Mapped[str] = mapped_column(String(48))
    quality_flags: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, default=list, server_default="[]"
    )
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
