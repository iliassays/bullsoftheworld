"""Enforce tenant ownership for identities, sessions, and private account data.

Revision ID: e1a5c7d9f2b4
Revises: d0f4a8c2e6b1
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "e1a5c7d9f2b4"
down_revision = "d0f4a8c2e6b1"
branch_labels = None
depends_on = None

_BACKFILLED_TABLES = (
    "refresh_sessions",
    "watchlist_items",
    "portfolio_holdings",
    "portfolio_snapshots",
    "post_reactions",
    "quiz_answers",
    "follows",
)

_RLS_TABLES = (
    "users",
    "refresh_sessions",
    "watchlist_items",
    "portfolio_holdings",
    "portfolio_snapshots",
    "post_reactions",
    "quiz_answers",
    "follows",
    "alert_events",
    "price_alerts",
    "on_demand_research_requests",
)

_LEGACY_USER_FKS = {
    "refresh_sessions": "refresh_sessions_user_id_fkey",
    "watchlist_items": "watchlist_items_user_id_fkey",
    "portfolio_holdings": "portfolio_holdings_user_id_fkey",
    "portfolio_snapshots": "portfolio_snapshots_user_id_fkey",
    "post_reactions": "post_reactions_user_id_fkey",
    "quiz_answers": "quiz_answers_user_id_fkey",
    "alert_events": "alert_events_user_id_fkey",
    "price_alerts": "price_alerts_user_id_fkey",
    "on_demand_research_requests": "on_demand_research_requests_user_id_fkey",
}

_COMPOSITE_USER_FKS = {
    "refresh_sessions": "fk_refresh_sessions_user_tenant",
    "watchlist_items": "fk_watchlist_items_user_tenant",
    "portfolio_holdings": "fk_portfolio_holdings_user_tenant",
    "portfolio_snapshots": "fk_portfolio_snapshots_user_tenant",
    "post_reactions": "fk_post_reactions_user_tenant",
    "quiz_answers": "fk_quiz_answers_user_tenant",
    "alert_events": "fk_alert_events_user_tenant",
    "price_alerts": "fk_price_alerts_user_tenant",
    "on_demand_research_requests": "fk_on_demand_research_requests_user_tenant",
}


def _add_tenant_column(table: str, user_column: str = "user_id") -> None:
    op.add_column(table, sa.Column("tenant_id", sa.String(length=64), nullable=True))
    op.execute(
        sa.text(
            f'UPDATE "{table}" AS owned SET tenant_id = users.tenant_id '
            f'FROM users WHERE owned."{user_column}" = users.id'
        )
    )
    op.alter_column(table, "tenant_id", nullable=False)
    op.create_index(f"ix_{table}_tenant_id", table, ["tenant_id"])


def _drop_constraint_if_exists(table: str, constraint: str) -> None:
    op.execute(sa.text(f'ALTER TABLE "{table}" DROP CONSTRAINT IF EXISTS "{constraint}"'))


def _enable_tenant_rls(table: str) -> None:
    policy = f"{table}_tenant_isolation"
    predicate = "tenant_id = current_setting('app.tenant_id', true)"
    op.execute(sa.text(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY'))
    op.execute(sa.text(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY'))
    op.execute(
        sa.text(
            f'CREATE POLICY "{policy}" ON "{table}" USING ({predicate}) WITH CHECK ({predicate})'
        )
    )


def upgrade() -> None:
    for table in _BACKFILLED_TABLES:
        _add_tenant_column(table, "follower_id" if table == "follows" else "user_id")

    op.create_unique_constraint("uq_posts_id_tenant", "posts", ["id", "tenant_id"])

    for table, legacy_fk in _LEGACY_USER_FKS.items():
        _drop_constraint_if_exists(table, legacy_fk)
        op.create_foreign_key(
            _COMPOSITE_USER_FKS[table],
            table,
            "users",
            ["user_id", "tenant_id"],
            ["id", "tenant_id"],
            ondelete="CASCADE",
        )

    _drop_constraint_if_exists("post_reactions", "post_reactions_post_id_fkey")
    op.create_foreign_key(
        "fk_post_reactions_post_tenant",
        "post_reactions",
        "posts",
        ["post_id", "tenant_id"],
        ["id", "tenant_id"],
        ondelete="CASCADE",
    )

    _drop_constraint_if_exists("follows", "follows_follower_id_fkey")
    _drop_constraint_if_exists("follows", "follows_followee_id_fkey")
    op.create_foreign_key(
        "fk_follows_follower_tenant",
        "follows",
        "users",
        ["follower_id", "tenant_id"],
        ["id", "tenant_id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_follows_followee_tenant",
        "follows",
        "users",
        ["followee_id", "tenant_id"],
        ["id", "tenant_id"],
        ondelete="CASCADE",
    )

    for table in _RLS_TABLES:
        _enable_tenant_rls(table)


def downgrade() -> None:
    for table in reversed(_RLS_TABLES):
        op.execute(sa.text(f'DROP POLICY IF EXISTS "{table}_tenant_isolation" ON "{table}"'))
        op.execute(sa.text(f'ALTER TABLE "{table}" NO FORCE ROW LEVEL SECURITY'))
        op.execute(sa.text(f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY'))

    _drop_constraint_if_exists("post_reactions", "fk_post_reactions_post_tenant")
    op.create_foreign_key(
        "post_reactions_post_id_fkey",
        "post_reactions",
        "posts",
        ["post_id"],
        ["id"],
    )

    _drop_constraint_if_exists("follows", "fk_follows_follower_tenant")
    _drop_constraint_if_exists("follows", "fk_follows_followee_tenant")
    _drop_constraint_if_exists("follows", "follows_follower_id_fkey")
    _drop_constraint_if_exists("follows", "follows_followee_id_fkey")
    op.create_foreign_key("follows_follower_id_fkey", "follows", "users", ["follower_id"], ["id"])
    op.create_foreign_key("follows_followee_id_fkey", "follows", "users", ["followee_id"], ["id"])

    for table, composite_fk in reversed(tuple(_COMPOSITE_USER_FKS.items())):
        _drop_constraint_if_exists(table, composite_fk)
        op.create_foreign_key(
            _LEGACY_USER_FKS[table],
            table,
            "users",
            ["user_id"],
            ["id"],
        )

    op.drop_constraint("uq_posts_id_tenant", "posts", type_="unique")
    for table in reversed(_BACKFILLED_TABLES):
        op.execute(sa.text(f'DROP INDEX IF EXISTS "ix_{table}_tenant_id"'))
        op.execute(sa.text(f'ALTER TABLE "{table}" DROP COLUMN IF EXISTS tenant_id'))
