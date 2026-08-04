"""Immutable, policy-versioned Atlas universe decisions."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from bulls.core.db import Base


class ResearchUniverseSnapshot(Base):
    """One immutable universe evaluation for one market and completed session."""

    __tablename__ = "research_universe_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "id",
            "market",
            name="uq_research_universe_snapshots_market_scope",
        ),
        UniqueConstraint(
            "market",
            "as_of_date",
            "policy_key",
            "policy_version",
            "input_fingerprint",
            name="uq_research_universe_snapshots_input",
        ),
        CheckConstraint(
            "source_mode IN ('point_in_time', 'current_projection')",
            name="ck_research_universe_snapshots_source_mode",
        ),
        CheckConstraint(
            "market IN ('DSE', 'US')",
            name="ck_research_universe_snapshots_market",
        ),
        CheckConstraint(
            "candidate_count >= 0 AND eligible_count >= 0 AND ineligible_count >= 0 "
            "AND data_blocked_count >= 0 AND model_eligible_count >= 0 "
            "AND candidate_count = eligible_count + ineligible_count + data_blocked_count "
            "AND model_eligible_count <= eligible_count",
            name="ck_research_universe_snapshots_counts",
        ),
        CheckConstraint(
            "NOT model_ready OR (eligible_count > 0 AND data_blocked_count = 0 "
            "AND model_eligible_count = eligible_count)",
            name="ck_research_universe_snapshots_model_ready",
        ),
        CheckConstraint(
            "policy_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_research_universe_snapshots_policy_hash",
        ),
        CheckConstraint(
            "input_fingerprint ~ '^[0-9a-f]{64}$'",
            name="ck_research_universe_snapshots_input_hash",
        ),
        Index(
            "ix_research_universe_snapshots_market_date",
            "market",
            "as_of_date",
        ),
        Index(
            "ix_research_universe_snapshots_market_policy",
            "market",
            "policy_key",
            "policy_version",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    market: Mapped[str] = mapped_column(String(8))
    as_of_date: Mapped[dt.date] = mapped_column(Date)
    knowledge_cutoff: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    policy_key: Mapped[str] = mapped_column(String(64))
    policy_version: Mapped[str] = mapped_column(String(32))
    policy_sha256: Mapped[str] = mapped_column(String(64))
    input_fingerprint: Mapped[str] = mapped_column(String(64))
    source_mode: Mapped[str] = mapped_column(String(24))
    model_ready: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    candidate_count: Mapped[int] = mapped_column(Integer)
    eligible_count: Mapped[int] = mapped_column(Integer)
    ineligible_count: Mapped[int] = mapped_column(Integer)
    data_blocked_count: Mapped[int] = mapped_column(Integer)
    model_eligible_count: Mapped[int] = mapped_column(Integer)
    policy_parameters: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    quality_report: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    generated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ResearchUniverseMember(Base):
    """One security's auditable decision within an immutable universe snapshot."""

    __tablename__ = "research_universe_members"
    __table_args__ = (
        ForeignKeyConstraint(
            ["snapshot_id", "market"],
            ["research_universe_snapshots.id", "research_universe_snapshots.market"],
            name="fk_research_universe_members_snapshot_scope",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "decision IN ('eligible', 'ineligible', 'data_blocked')",
            name="ck_research_universe_members_decision",
        ),
        CheckConstraint(
            "market IN ('DSE', 'US')",
            name="ck_research_universe_members_market",
        ),
        CheckConstraint(
            "(market = 'DSE' AND (cohort IS NULL OR cohort = 'dse_liquid')) OR "
            "(market = 'US' AND (cohort IS NULL OR cohort IN "
            "('us_core', 'us_small', 'us_micro_penny')))",
            name="ck_research_universe_members_market_cohort",
        ),
        CheckConstraint(
            "input_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_research_universe_members_input_hash",
        ),
        CheckConstraint(
            "NOT model_eligible OR decision = 'eligible'",
            name="ck_research_universe_members_model_eligibility",
        ),
        Index(
            "ix_research_universe_members_snapshot_decision",
            "snapshot_id",
            "decision",
            "cohort",
        ),
        Index(
            "ix_research_universe_members_market_code",
            "market",
            "code",
        ),
    )

    snapshot_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    market: Mapped[str] = mapped_column(String(8), primary_key=True)
    code: Mapped[str] = mapped_column(String(32), primary_key=True)
    security_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("security_master.security_id", ondelete="RESTRICT"),
    )
    decision: Mapped[str] = mapped_column(String(16))
    cohort: Mapped[str | None] = mapped_column(String(32))
    cap_tier: Mapped[str | None] = mapped_column(String(16))
    model_eligible: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    reason_codes: Mapped[list[str]] = mapped_column(
        JSONB,
        default=list,
        server_default=text("'[]'::jsonb"),
    )
    model_blocker_codes: Mapped[list[str]] = mapped_column(
        JSONB,
        default=list,
        server_default=text("'[]'::jsonb"),
    )
    warning_codes: Mapped[list[str]] = mapped_column(
        JSONB,
        default=list,
        server_default=text("'[]'::jsonb"),
    )
    metrics: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    evidence: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    input_sha256: Mapped[str] = mapped_column(String(64))
    evaluated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))


__all__ = ["ResearchUniverseMember", "ResearchUniverseSnapshot"]
