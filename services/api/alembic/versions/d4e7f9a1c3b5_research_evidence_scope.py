"""Make ownership chronology and strategy-family scope deterministic.

Revision ID: d4e7f9a1c3b5
Revises: c6f8a0b2d4e7
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "d4e7f9a1c3b5"
down_revision = "c6f8a0b2d4e7"
branch_labels = None
depends_on = None

_TABLE = "research_strategy_trials"
_OLD_POLICY = "research_strategy_trials_tenant_market_isolation"
_TENANT_SCOPE = (
    "tenant_id = current_setting('app.research_tenant_id', true) "
    "AND market = current_setting('app.research_market', true)"
)
_USER_ID = "NULLIF(current_setting('app.research_user_id', true), '')::integer"
_ORG_ACCESS = (
    "EXISTS (SELECT 1 FROM research_organization_memberships rom "
    f"WHERE rom.organization_id = {_TABLE}.organization_id "
    f"AND rom.tenant_id = {_TABLE}.tenant_id AND rom.market = {_TABLE}.market "
    f"AND rom.user_id = {_USER_ID} AND rom.status = 'active')"
)
_WORKSPACE_ACCESS = (
    "EXISTS (SELECT 1 FROM research_organization_memberships rom "
    f"WHERE rom.organization_id = {_TABLE}.organization_id "
    f"AND rom.tenant_id = {_TABLE}.tenant_id AND rom.market = {_TABLE}.market "
    f"AND rom.user_id = {_USER_ID} AND rom.status = 'active' "
    "AND (rom.role IN ('owner', 'admin') OR EXISTS ("
    "SELECT 1 FROM research_workspace_memberships rwm "
    f"WHERE rwm.workspace_id = {_TABLE}.workspace_id "
    f"AND rwm.organization_id = {_TABLE}.organization_id "
    f"AND rwm.tenant_id = {_TABLE}.tenant_id AND rwm.market = {_TABLE}.market "
    f"AND rwm.user_id = {_USER_ID} AND rwm.status = 'active')))"
)


def _create_trial_policies() -> None:
    read_scope = f"{_TENANT_SCOPE} AND ({_ORG_ACCESS})"
    write_scope = f"{_TENANT_SCOPE} AND ({_WORKSPACE_ACCESS})"
    op.execute(
        sa.text(
            f'CREATE POLICY "{_TABLE}_organization_read" ON "{_TABLE}" '
            f"FOR SELECT USING ({read_scope})"
        )
    )
    op.execute(
        sa.text(
            f'CREATE POLICY "{_TABLE}_workspace_insert" ON "{_TABLE}" '
            f"FOR INSERT WITH CHECK ({write_scope})"
        )
    )
    op.execute(
        sa.text(
            f'CREATE POLICY "{_TABLE}_workspace_update" ON "{_TABLE}" '
            f"FOR UPDATE USING ({write_scope}) WITH CHECK ({write_scope})"
        )
    )
    op.execute(
        sa.text(
            f'CREATE POLICY "{_TABLE}_workspace_delete" ON "{_TABLE}" '
            f"FOR DELETE USING ({write_scope})"
        )
    )


def upgrade() -> None:
    op.add_column(
        "shareholding_snapshots",
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.add_column(
        "institutional_holding_summaries",
        sa.Column("share_basis_comparable", sa.Boolean(), nullable=True),
    )
    op.create_index(
        "ix_research_strategy_trials_org_family",
        _TABLE,
        ["organization_id", "tenant_id", "market", "strategy_key"],
    )
    op.execute(sa.text(f'DROP POLICY IF EXISTS "{_OLD_POLICY}" ON "{_TABLE}"'))
    _create_trial_policies()


def downgrade() -> None:
    for suffix in (
        "organization_read",
        "workspace_insert",
        "workspace_update",
        "workspace_delete",
    ):
        op.execute(sa.text(f'DROP POLICY IF EXISTS "{_TABLE}_{suffix}" ON "{_TABLE}"'))
    old_scope = f"{_TENANT_SCOPE} AND ({_WORKSPACE_ACCESS})"
    op.execute(
        sa.text(
            f'CREATE POLICY "{_OLD_POLICY}" ON "{_TABLE}" '
            f"USING ({old_scope}) WITH CHECK ({old_scope})"
        )
    )
    op.drop_index("ix_research_strategy_trials_org_family", table_name=_TABLE)
    op.drop_column("institutional_holding_summaries", "share_basis_comparable")
    op.drop_column("shareholding_snapshots", "first_seen_at")
