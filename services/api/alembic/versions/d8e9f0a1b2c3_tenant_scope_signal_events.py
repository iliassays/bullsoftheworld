"""tenant-scope signal dedupe and evidence rows

Revision ID: d8e9f0a1b2c3
Revises: c7d8e9f0a1b2
"""

import sqlalchemy as sa
from alembic import op

revision = "d8e9f0a1b2c3"
down_revision = "c7d8e9f0a1b2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "signal_events", sa.Column("tenant_id", sa.String(length=64), nullable=True)
    )
    op.execute(
        "UPDATE signal_events SET tenant_id = posts.tenant_id "
        "FROM posts WHERE signal_events.post_id = posts.id"
    )
    op.execute(
        "UPDATE signal_events SET tenant_id = "
        "CASE WHEN market = 'US' THEN 'bullsofwallst' ELSE 'bullsofdhaka' END "
        "WHERE tenant_id IS NULL"
    )
    op.alter_column("signal_events", "tenant_id", nullable=False)
    op.create_index("ix_signal_events_tenant_id", "signal_events", ["tenant_id"])
    op.drop_constraint("uq_signal_event", "signal_events", type_="unique")
    op.create_unique_constraint(
        "uq_signal_event",
        "signal_events",
        ["tenant_id", "market", "code", "event_type", "occurrence_key"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_signal_event", "signal_events", type_="unique")
    op.create_unique_constraint(
        "uq_signal_event",
        "signal_events",
        ["market", "code", "event_type", "occurrence_key"],
    )
    op.drop_index("ix_signal_events_tenant_id", table_name="signal_events")
    op.drop_column("signal_events", "tenant_id")
