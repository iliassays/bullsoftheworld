"""Give catalyst corrections a stable source-based identity.

Revision ID: c9e1f3a5b7d9
Revises: b8d0e2f4a6c8
Create Date: 2026-07-16
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "c9e1f3a5b7d9"
down_revision = "b8d0e2f4a6c8"
branch_labels = None
depends_on = None

_TABLE = "research_catalyst_events"
_CONSTRAINT = "uq_research_catalyst_source_event"


def upgrade() -> None:
    # Earlier timing-based identities could leave multiple rows when the same official source
    # corrected a date. Retain the most recently maintained row before enforcing source identity.
    op.execute(
        sa.text(
            f"""
            DELETE FROM {_TABLE}
            WHERE id IN (
                SELECT id
                FROM (
                    SELECT
                        id,
                        row_number() OVER (
                            PARTITION BY tenant_id, market, code, event_type, source_ref
                            ORDER BY
                                (outcome IS NOT NULL) DESC,
                                (status = 'cancelled') DESC,
                                updated_at DESC,
                                created_at DESC,
                                id DESC
                        ) AS duplicate_rank
                    FROM {_TABLE}
                ) ranked
                WHERE duplicate_rank > 1
            )
            """
        )
    )
    op.create_unique_constraint(
        _CONSTRAINT,
        _TABLE,
        ["tenant_id", "market", "code", "event_type", "source_ref"],
    )


def downgrade() -> None:
    op.drop_constraint(_CONSTRAINT, _TABLE, type_="unique")
