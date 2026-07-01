"""feed moderation: posts.moderation_status/reason/hash + moderation_events

Revision ID: d5e6f7a8b9c0
Revises: c4d5e6f7a8b9
"""

import sqlalchemy as sa
from alembic import op

revision = "d5e6f7a8b9c0"
down_revision = "c4d5e6f7a8b9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "posts",
        sa.Column(
            "moderation_status", sa.String(length=10), nullable=False, server_default="published"
        ),
    )
    op.add_column("posts", sa.Column("moderation_reason", sa.String(length=32), nullable=True))
    op.add_column("posts", sa.Column("normalized_hash", sa.String(length=64), nullable=True))
    op.create_index("ix_posts_moderation_status", "posts", ["moderation_status"])
    op.create_index("ix_posts_normalized_hash", "posts", ["normalized_hash"])

    op.create_table(
        "moderation_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("post_id", sa.Integer(), sa.ForeignKey("posts.id"), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("decision", sa.String(length=10), nullable=False),
        sa.Column("layer", sa.Integer(), nullable=False),
        sa.Column("risk_score", sa.Numeric(4, 3), nullable=True),
        sa.Column("categories", sa.JSON(), nullable=True),
        sa.Column("rule_ids", sa.JSON(), nullable=True),
        sa.Column("reason_code", sa.String(length=32), nullable=True),
        sa.Column("model", sa.String(length=48), nullable=True),
        sa.Column("tokens", sa.Integer(), nullable=True),
        sa.Column("cost", sa.Numeric(10, 6), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("actor", sa.String(length=16), nullable=False, server_default="system"),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_moderation_events_post_id", "moderation_events", ["post_id"])
    op.create_index("ix_moderation_events_tenant_id", "moderation_events", ["tenant_id"])
    op.create_index("ix_moderation_events_created_at", "moderation_events", ["created_at"])


def downgrade() -> None:
    op.drop_table("moderation_events")
    op.drop_index("ix_posts_normalized_hash", table_name="posts")
    op.drop_index("ix_posts_moderation_status", table_name="posts")
    op.drop_column("posts", "normalized_hash")
    op.drop_column("posts", "moderation_reason")
    op.drop_column("posts", "moderation_status")
