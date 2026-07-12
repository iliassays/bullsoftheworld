"""First-party product analytics and consented institutional enquiries."""

from __future__ import annotations

import datetime as dt

from sqlalchemy import JSON, Boolean, CheckConstraint, DateTime, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from bulls.core.db import Base


class ProductEvent(Base):
    """Bounded, append-only funnel event; never stores free-form user content or PII."""

    __tablename__ = "product_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    market: Mapped[str] = mapped_column(String(8))
    name: Mapped[str] = mapped_column(String(48))
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), default=None)
    session_hash: Mapped[str | None] = mapped_column(String(64), default=None)
    locale: Mapped[str] = mapped_column(String(8))
    path: Mapped[str | None] = mapped_column(String(512), default=None)
    properties: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        Index("ix_product_events_tenant_name_created", "tenant_id", "name", "created_at"),
    )


class InstitutionalLead(Base):
    """An explicit request for a business conversation, isolated to its originating tenant."""

    __tablename__ = "institutional_leads"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    market: Mapped[str] = mapped_column(String(8))
    organization: Mapped[str] = mapped_column(String(160))
    contact_name: Mapped[str] = mapped_column(String(120))
    work_email: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(80))
    use_case: Mapped[str] = mapped_column(String(1200))
    source: Mapped[str] = mapped_column(String(64), default="institutional_page")
    status: Mapped[str] = mapped_column(String(16), default="new", server_default="new")
    consented_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('new', 'contacted', 'qualified', 'closed')",
            name="ck_institutional_leads_status",
        ),
        Index(
            "ix_institutional_leads_tenant_status_created",
            "tenant_id",
            "status",
            "created_at",
        ),
    )


class BetaFeedback(Base):
    """Structured research-beta feedback with optional, consented account follow-up."""

    __tablename__ = "beta_feedback"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    market: Mapped[str] = mapped_column(String(8))
    locale: Mapped[str] = mapped_column(String(8))
    kind: Mapped[str] = mapped_column(String(16))
    message: Mapped[str] = mapped_column(String(1200), default="")
    path: Mapped[str] = mapped_column(String(512))
    symbol_code: Mapped[str | None] = mapped_column(String(32), default=None)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), default=None)
    contact_consent: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    status: Mapped[str] = mapped_column(String(16), default="new", server_default="new")
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "kind IN ('useful', 'unclear', 'incorrect', 'missing', 'other')",
            name="ck_beta_feedback_kind",
        ),
        CheckConstraint(
            "status IN ('new', 'reviewed', 'resolved')",
            name="ck_beta_feedback_status",
        ),
        Index("ix_beta_feedback_tenant_status_created", "tenant_id", "status", "created_at"),
    )
