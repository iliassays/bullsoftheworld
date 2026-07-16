"""Record capital-constrained agent opportunities for counterfactual evaluation.

Revision ID: f9c2d3e4a5b6
Revises: f8c1d2e3a4b5
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "f9c2d3e4a5b6"
down_revision = "f8c1d2e3a4b5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_opportunities",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("market", sa.String(8), nullable=False),
        sa.Column("strategy", sa.String(24), nullable=False),
        sa.Column("code", sa.String(16), nullable=False),
        sa.Column("status", sa.String(12), server_default="open", nullable=False),
        sa.Column("signal_reason", sa.String(300), nullable=False),
        sa.Column("first_block_reason", sa.String(24), nullable=False),
        sa.Column("last_block_reason", sa.String(24), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("first_quote_as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_quote_as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("first_price", sa.Float(), nullable=False),
        sa.Column("last_price", sa.Float(), nullable=False),
        sa.Column("best_price", sa.Float(), nullable=False),
        sa.Column("worst_price", sa.Float(), nullable=False),
        sa.Column("first_rank", sa.Integer(), nullable=False),
        sa.Column("best_rank", sa.Integer(), nullable=False),
        sa.Column("last_rank", sa.Integer(), nullable=False),
        sa.Column("target_budget", sa.Float(), nullable=False),
        sa.Column("required_cash", sa.Float(), nullable=False),
        sa.Column("first_available_cash", sa.Float(), nullable=False),
        sa.Column("last_available_cash", sa.Float(), nullable=False),
        sa.Column("first_pending_cash", sa.Float(), nullable=False),
        sa.Column("last_pending_cash", sa.Float(), nullable=False),
        sa.Column("first_free_slots", sa.Integer(), nullable=False),
        sa.Column("last_free_slots", sa.Integer(), nullable=False),
        sa.Column("blocked_ticks", sa.Integer(), server_default="1", nullable=False),
        sa.Column("no_cash_ticks", sa.Integer(), server_default="0", nullable=False),
        sa.Column("no_slot_ticks", sa.Integer(), server_default="0", nullable=False),
        sa.Column("order_too_small_ticks", sa.Integer(), server_default="0", nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_price", sa.Float(), nullable=True),
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
        sa.CheckConstraint(
            "status IN ('open', 'entered', 'expired')",
            name="ck_agent_opportunities_status",
        ),
        sa.CheckConstraint(
            "first_block_reason IN ('no_cash', 'no_slot', 'order_too_small')",
            name="ck_agent_opportunities_first_block_reason",
        ),
        sa.CheckConstraint(
            "last_block_reason IN ('no_cash', 'no_slot', 'order_too_small')",
            name="ck_agent_opportunities_last_block_reason",
        ),
        sa.ForeignKeyConstraint(
            ["user_id", "tenant_id"],
            ["users.id", "users.tenant_id"],
            name="fk_agent_opportunities_user_tenant",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_agent_opportunities_open_episode",
        "agent_opportunities",
        ["tenant_id", "user_id", "market", "strategy", "code"],
        unique=True,
        postgresql_where=sa.text("status = 'open'"),
    )
    op.create_index(
        "ix_agent_opportunities_scope_status_seen",
        "agent_opportunities",
        ["tenant_id", "market", "status", "last_seen_at"],
    )
    predicate = "tenant_id = current_setting('app.tenant_id', true)"
    op.execute(sa.text("ALTER TABLE agent_opportunities ENABLE ROW LEVEL SECURITY"))
    op.execute(sa.text("ALTER TABLE agent_opportunities FORCE ROW LEVEL SECURITY"))
    op.execute(
        sa.text(
            "CREATE POLICY agent_opportunities_tenant_isolation ON agent_opportunities "
            f"USING ({predicate}) WITH CHECK ({predicate})"
        )
    )


def downgrade() -> None:
    op.drop_table("agent_opportunities")
