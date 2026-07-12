"""Add tenant-scoped research-beta feedback.

Revision ID: 6f7a8b9c0d1e
Revises: 5e6f7a8b9c0d
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "6f7a8b9c0d1e"
down_revision = "5e6f7a8b9c0d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "beta_feedback",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("market", sa.String(length=8), nullable=False),
        sa.Column("locale", sa.String(length=8), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("message", sa.String(length=1200), nullable=False),
        sa.Column("path", sa.String(length=512), nullable=False),
        sa.Column("symbol_code", sa.String(length=32), nullable=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column(
            "contact_consent",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=16), server_default="new", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "kind IN ('useful', 'unclear', 'incorrect', 'missing', 'other')",
            name="ck_beta_feedback_kind",
        ),
        sa.CheckConstraint(
            "status IN ('new', 'reviewed', 'resolved')",
            name="ck_beta_feedback_status",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_beta_feedback_tenant_id", "beta_feedback", ["tenant_id"])
    op.create_index(
        "ix_beta_feedback_tenant_status_created",
        "beta_feedback",
        ["tenant_id", "status", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_beta_feedback_tenant_status_created", table_name="beta_feedback")
    op.drop_index("ix_beta_feedback_tenant_id", table_name="beta_feedback")
    op.drop_table("beta_feedback")
