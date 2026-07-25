"""Daily shortlist archive

The slate was recomputed live from ticker_analytics, which keeps one current row per symbol.
That made past slates unrecoverable and outcome tracking impossible. This archives one row per
slot per session so "what did you show me on Tuesday, and what happened next" is answerable.

Revision ID: b5e7d2f4a9c1
Revises: a3d9f1c5e7b2
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "b5e7d2f4a9c1"
down_revision = "a3d9f1c5e7b2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "daily_shortlist_states",
        sa.Column("market", sa.String(length=8), primary_key=True),
        sa.Column("as_of_date", sa.Date(), primary_key=True),
        sa.Column("code", sa.String(length=16), primary_key=True),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("attention_score", sa.Float(), nullable=False),
        # The ranked close — the reference every later outcome is measured against.
        sa.Column("close", sa.Float(), nullable=False),
        sa.Column("change_pct", sa.Float()),
        sa.Column("sector", sa.String(length=64)),
        sa.Column("pe", sa.Float()),
        sa.Column(
            "facts", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")
        ),
        sa.Column(
            "cautions", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")
        ),
        sa.Column("eligible_names", sa.Integer(), nullable=False),
        sa.Column(
            "evidence_mode", sa.String(length=16), nullable=False, server_default="forward"
        ),
        sa.Column("methodology_version", sa.String(length=48), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "evidence_mode IN ('forward', 'reconstructed')",
            name="ck_daily_shortlist_states_evidence_mode",
        ),
        sa.CheckConstraint("rank >= 1", name="ck_daily_shortlist_states_rank"),
    )
    op.create_index(
        "ix_daily_shortlist_states_market_date",
        "daily_shortlist_states",
        ["market", "as_of_date"],
    )


def downgrade() -> None:
    op.drop_index("ix_daily_shortlist_states_market_date", table_name="daily_shortlist_states")
    op.drop_table("daily_shortlist_states")
