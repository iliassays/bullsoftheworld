"""Add tenant-scoped product events and institutional leads.

Revision ID: 5e6f7a8b9c0d
Revises: 4d5e6f7a8b9c
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "5e6f7a8b9c0d"
down_revision = "4d5e6f7a8b9c"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "product_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("market", sa.String(length=8), nullable=False),
        sa.Column("name", sa.String(length=48), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("session_hash", sa.String(length=64), nullable=True),
        sa.Column("locale", sa.String(length=8), nullable=False),
        sa.Column("path", sa.String(length=512), nullable=True),
        sa.Column("properties", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_product_events_tenant_id", "product_events", ["tenant_id"])
    op.create_index(
        "ix_product_events_tenant_name_created",
        "product_events",
        ["tenant_id", "name", "created_at"],
    )
    op.create_table(
        "institutional_leads",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("market", sa.String(length=8), nullable=False),
        sa.Column("organization", sa.String(length=160), nullable=False),
        sa.Column("contact_name", sa.String(length=120), nullable=False),
        sa.Column("work_email", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=80), nullable=False),
        sa.Column("use_case", sa.String(length=1200), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="new", nullable=False),
        sa.Column("consented_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('new', 'contacted', 'qualified', 'closed')",
            name="ck_institutional_leads_status",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_institutional_leads_tenant_id", "institutional_leads", ["tenant_id"])
    op.create_index(
        "ix_institutional_leads_tenant_status_created",
        "institutional_leads",
        ["tenant_id", "status", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_institutional_leads_tenant_status_created", table_name="institutional_leads")
    op.drop_index("ix_institutional_leads_tenant_id", table_name="institutional_leads")
    op.drop_table("institutional_leads")
    op.drop_index("ix_product_events_tenant_name_created", table_name="product_events")
    op.drop_index("ix_product_events_tenant_id", table_name="product_events")
    op.drop_table("product_events")
