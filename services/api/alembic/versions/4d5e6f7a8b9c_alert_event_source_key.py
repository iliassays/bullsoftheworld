"""Add idempotent source keys for external evidence alerts."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "4d5e6f7a8b9c"
down_revision = "3c4d5e6f7a8b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("alert_events", sa.Column("source_key", sa.String(length=160), nullable=True))
    op.create_index(
        "uq_alert_events_user_source",
        "alert_events",
        ["tenant_id", "user_id", "source_key"],
        unique=True,
        postgresql_where=sa.text("source_key IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_alert_events_user_source", table_name="alert_events")
    op.drop_column("alert_events", "source_key")
