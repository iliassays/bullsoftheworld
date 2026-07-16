"""Persisted, tenant-bound Hedge track record and signal ledger.

Revision ID: f8c1d2e3a4b5
Revises: e7b8c9d0a1f2
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "f8c1d2e3a4b5"
down_revision = "e7b8c9d0a1f2"
branch_labels = None
depends_on = None


def _tenant_rls(table: str) -> None:
    predicate = "tenant_id = current_setting('app.tenant_id', true)"
    op.execute(sa.text(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY'))
    op.execute(sa.text(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY'))
    op.execute(
        sa.text(
            f'CREATE POLICY "{table}_tenant_isolation" ON "{table}" '
            f"USING ({predicate}) WITH CHECK ({predicate})"
        )
    )


def upgrade() -> None:
    # A pre-migration utility table may exist on older hosts. It did not have tenant isolation
    # and is intentionally replaced; the refresh service rebuilds the complete ledger.
    op.execute(sa.text("DROP TABLE IF EXISTS hedge_log"))
    op.create_table(
        "hedge_track_record_snapshots",
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("market", sa.String(8), nullable=False),
        sa.Column("strategy", sa.String(32), nullable=False),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "computed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("tenant_id", "market", "strategy"),
    )
    op.create_table(
        "hedge_signals",
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("market", sa.String(8), nullable=False),
        sa.Column("strategy", sa.String(32), nullable=False),
        sa.Column("code", sa.String(16), nullable=False),
        sa.Column("signal_date", sa.Date(), nullable=False),
        sa.Column("entry", sa.Float(), nullable=False),
        sa.Column("stop", sa.Float(), nullable=False),
        sa.Column("target", sa.Float(), nullable=False),
        sa.Column("status", sa.String(12), nullable=False),
        sa.Column("exit_date", sa.Date(), nullable=True),
        sa.Column("exit_px", sa.Float(), nullable=True),
        sa.Column("result_pct", sa.Float(), nullable=True),
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
        sa.PrimaryKeyConstraint("tenant_id", "market", "strategy", "code", "signal_date"),
    )
    op.create_index(
        "ix_hedge_signals_scope_status_date",
        "hedge_signals",
        ["tenant_id", "market", "strategy", "status", "signal_date"],
    )
    op.create_index(
        "ix_agent_trades_user_market_settlement",
        "agent_trades",
        ["user_id", "market", "settled", "settles_on"],
    )
    op.create_index(
        "ix_agent_trades_user_market_date",
        "agent_trades",
        ["user_id", "market", "trade_date", "id"],
    )
    op.create_index(
        "ix_agent_lots_user_market_open",
        "agent_lots",
        ["user_id", "market", "quantity_left", "sellable_from"],
    )
    _tenant_rls("hedge_track_record_snapshots")
    _tenant_rls("hedge_signals")


def downgrade() -> None:
    op.drop_index("ix_agent_lots_user_market_open", table_name="agent_lots")
    op.drop_index("ix_agent_trades_user_market_date", table_name="agent_trades")
    op.drop_index("ix_agent_trades_user_market_settlement", table_name="agent_trades")
    op.drop_table("hedge_signals")
    op.drop_table("hedge_track_record_snapshots")
