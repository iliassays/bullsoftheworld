"""Add verified DSE corporate-action adjustment lineage.

Revision ID: da2f4b6d8e0a
Revises: d9e1f3a5b7c9
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "da2f4b6d8e0a"
down_revision = "d9e1f3a5b7c9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "corporate_actions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("market", sa.String(length=8), nullable=False),
        sa.Column("code", sa.String(length=16), nullable=False),
        sa.Column("action_type", sa.String(length=12), nullable=False),
        sa.Column("record_date", sa.Date(), nullable=False),
        sa.Column("effective_session", sa.Date(), nullable=True),
        sa.Column("bonus_ratio", sa.Float(), nullable=True),
        sa.Column("rights_ratio", sa.Float(), nullable=True),
        sa.Column("rights_subscription_price", sa.Float(), nullable=True),
        sa.Column("reference_close", sa.Float(), nullable=True),
        sa.Column("adjustment_factor", sa.Float(), nullable=True),
        sa.Column("status", sa.String(length=12), server_default="verified", nullable=False),
        sa.Column(
            "source_announcement_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("known_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("calculation_version", sa.String(length=48), nullable=False),
        sa.Column(
            "quality_flags",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("action_type IN ('bonus', 'rights')", name="ck_corporate_actions_type"),
        sa.CheckConstraint("status IN ('verified', 'applied')", name="ck_corporate_actions_status"),
        sa.CheckConstraint(
            "(action_type = 'bonus' AND bonus_ratio > 0 AND rights_ratio IS NULL "
            "AND rights_subscription_price IS NULL) OR "
            "(action_type = 'rights' AND bonus_ratio IS NULL AND rights_ratio > 0 "
            "AND rights_subscription_price >= 0)",
            name="ck_corporate_actions_terms",
        ),
        sa.CheckConstraint(
            "adjustment_factor IS NULL OR adjustment_factor > 0",
            name="ck_corporate_actions_factor",
        ),
        sa.CheckConstraint(
            "(status = 'verified') OR (effective_session IS NOT NULL "
            "AND reference_close > 0 AND adjustment_factor > 0)",
            name="ck_corporate_actions_applied_shape",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "market",
            "code",
            "action_type",
            "record_date",
            name="uq_corporate_actions_security_record_type",
        ),
    )
    op.create_index(
        "ix_corporate_actions_security_effective",
        "corporate_actions",
        ["market", "code", "effective_session"],
    )
    op.create_index(
        "ix_corporate_actions_record_date",
        "corporate_actions",
        ["market", "record_date"],
    )


def downgrade() -> None:
    op.drop_index("ix_corporate_actions_record_date", table_name="corporate_actions")
    op.drop_index("ix_corporate_actions_security_effective", table_name="corporate_actions")
    op.drop_table("corporate_actions")
