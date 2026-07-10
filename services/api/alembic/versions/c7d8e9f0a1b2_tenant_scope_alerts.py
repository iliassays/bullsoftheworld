"""tenant-scope alert inbox and price-alert rows

Revision ID: c7d8e9f0a1b2
Revises: b6c7d8e9f0a1
"""

import sqlalchemy as sa
from alembic import op

revision = "c7d8e9f0a1b2"
down_revision = "b6c7d8e9f0a1"
branch_labels = None
depends_on = None


def _tenant_column(table: str) -> None:
    op.add_column(table, sa.Column("tenant_id", sa.String(length=64), nullable=True))
    op.execute(
        f"UPDATE {table} SET tenant_id = users.tenant_id "
        f"FROM users WHERE {table}.user_id = users.id"
    )
    op.alter_column(table, "tenant_id", nullable=False)
    op.create_index(f"ix_{table}_tenant_id", table, ["tenant_id"])


def upgrade() -> None:
    _tenant_column("alert_events")
    _tenant_column("price_alerts")


def downgrade() -> None:
    op.drop_index("ix_price_alerts_tenant_id", table_name="price_alerts")
    op.drop_column("price_alerts", "tenant_id")
    op.drop_index("ix_alert_events_tenant_id", table_name="alert_events")
    op.drop_column("alert_events", "tenant_id")
