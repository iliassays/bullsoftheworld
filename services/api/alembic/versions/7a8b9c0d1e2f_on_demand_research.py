"""Add deduplicated on-demand research jobs and tenant request audit.

Revision ID: 7a8b9c0d1e2f
Revises: 6f7a8b9c0d1e
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "7a8b9c0d1e2f"
down_revision = "6f7a8b9c0d1e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "on_demand_research_jobs",
        sa.Column(
            "id",
            sa.Uuid(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("market", sa.String(length=8), nullable=False),
        sa.Column("code", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=True),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("request_count", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "requested_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'review_required', 'ready', 'rejected', 'failed')",
            name="ck_on_demand_research_job_status",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["universe_onboarding_runs.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "market",
            "code",
            name="uq_on_demand_research_job_market_code",
        ),
    )
    op.create_index(
        "ix_on_demand_research_job_status_requested",
        "on_demand_research_jobs",
        ["status", "requested_at"],
    )
    op.create_table(
        "on_demand_research_requests",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("market", sa.String(length=8), nullable=False),
        sa.Column("code", sa.String(length=16), nullable=False),
        sa.Column("request_date", sa.Date(), nullable=False),
        sa.Column(
            "requested_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["on_demand_research_jobs.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "user_id",
            "market",
            "code",
            "request_date",
            name="uq_on_demand_research_request_user_symbol_day",
        ),
    )
    op.create_index(
        "ix_on_demand_research_requests_job_id",
        "on_demand_research_requests",
        ["job_id"],
    )
    op.create_index(
        "ix_on_demand_research_request_user_date",
        "on_demand_research_requests",
        ["tenant_id", "user_id", "request_date"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_on_demand_research_request_user_date",
        table_name="on_demand_research_requests",
    )
    op.drop_index(
        "ix_on_demand_research_requests_job_id",
        table_name="on_demand_research_requests",
    )
    op.drop_table("on_demand_research_requests")
    op.drop_index(
        "ix_on_demand_research_job_status_requested",
        table_name="on_demand_research_jobs",
    )
    op.drop_table("on_demand_research_jobs")
