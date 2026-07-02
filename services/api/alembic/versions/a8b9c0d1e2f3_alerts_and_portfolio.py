"""alert_events + price_alerts + portfolio_holdings — the retention features

Revision ID: a8b9c0d1e2f3
Revises: f7a8b9c0d1e2
"""

import sqlalchemy as sa
from alembic import op

revision = "a8b9c0d1e2f3"
down_revision = "f7a8b9c0d1e2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "alert_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("market", sa.String(length=8), nullable=False),
        sa.Column("code", sa.String(length=16), nullable=True),
        sa.Column("kind", sa.String(length=24), nullable=False),
        sa.Column("title_i18n", sa.JSON(), nullable=False),
        sa.Column("body_i18n", sa.JSON(), nullable=True),
        sa.Column("ref_post_id", sa.Integer(), sa.ForeignKey("posts.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_alert_events_user_id", "alert_events", ["user_id"])
    op.create_index("ix_alert_events_user_created", "alert_events", ["user_id", "created_at"])

    op.create_table(
        "price_alerts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("market", sa.String(length=8), nullable=False),
        sa.Column("code", sa.String(length=16), nullable=False),
        sa.Column("level", sa.Float(), nullable=False),
        sa.Column("direction", sa.String(length=6), nullable=False),
        sa.Column("triggered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_price_alerts_user_id", "price_alerts", ["user_id"])
    op.create_index("ix_price_alerts_code", "price_alerts", ["code"])

    op.create_table(
        "portfolio_holdings",
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("market", sa.String(length=8), nullable=False),
        sa.Column("code", sa.String(length=16), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("avg_cost", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("user_id", "market", "code"),
    )


def downgrade() -> None:
    op.drop_table("portfolio_holdings")
    op.drop_index("ix_price_alerts_code", table_name="price_alerts")
    op.drop_index("ix_price_alerts_user_id", table_name="price_alerts")
    op.drop_table("price_alerts")
    op.drop_index("ix_alert_events_user_created", table_name="alert_events")
    op.drop_index("ix_alert_events_user_id", table_name="alert_events")
    op.drop_table("alert_events")
