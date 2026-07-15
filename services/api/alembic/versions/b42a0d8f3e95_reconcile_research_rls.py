"""Reconcile institutional research row-security policies.

Revision ID: b42a0d8f3e95
Revises: a31f9c7e2d84

Some early development databases applied tenant-only drafts of the private research policies.
Recreate every policy from the current fail-closed tenant/market/user contract without touching
table data.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "b42a0d8f3e95"
down_revision = "a31f9c7e2d84"
branch_labels = None
depends_on = None

_TABLES = (
    "research_organizations",
    "research_organization_memberships",
    "research_workspaces",
    "research_workspace_memberships",
    "research_runs",
    "research_run_steps",
    "research_evidence_documents",
    "research_evidence_spans",
    "research_run_evidence",
    "research_claims",
    "research_claim_citations",
    "research_audit_events",
)
_TENANT_SCOPE = (
    "tenant_id = current_setting('app.research_tenant_id', true) "
    "AND market = current_setting('app.research_market', true)"
)
_USER_ID = "NULLIF(current_setting('app.research_user_id', true), '')::integer"


def _workspace_access(table: str, workspace_reference: str) -> str:
    return (
        "EXISTS (SELECT 1 FROM research_organization_memberships rom "
        f"WHERE rom.organization_id = {table}.organization_id "
        f"AND rom.tenant_id = {table}.tenant_id AND rom.market = {table}.market "
        f"AND rom.user_id = {_USER_ID} AND rom.status = 'active' "
        "AND (rom.role IN ('owner', 'admin') OR EXISTS ("
        "SELECT 1 FROM research_workspace_memberships rwm "
        f"WHERE rwm.workspace_id = {workspace_reference} "
        f"AND rwm.organization_id = {table}.organization_id "
        f"AND rwm.tenant_id = {table}.tenant_id AND rwm.market = {table}.market "
        f"AND rwm.user_id = {_USER_ID} AND rwm.status = 'active')))"
    )


_PRIVATE_SCOPES = {
    "research_organizations": (
        f"created_by_user_id = {_USER_ID} OR "
        "EXISTS (SELECT 1 FROM research_organization_memberships rom "
        "WHERE rom.organization_id = research_organizations.id "
        "AND rom.tenant_id = research_organizations.tenant_id "
        "AND rom.market = research_organizations.market "
        f"AND rom.user_id = {_USER_ID} AND rom.status = 'active')"
    ),
    "research_organization_memberships": f"user_id = {_USER_ID}",
    "research_workspaces": _workspace_access("research_workspaces", "research_workspaces.id"),
    "research_workspace_memberships": f"user_id = {_USER_ID}",
    "research_runs": _workspace_access("research_runs", "research_runs.workspace_id"),
    "research_run_steps": (
        "EXISTS (SELECT 1 FROM research_runs rr "
        "WHERE rr.id = research_run_steps.run_id "
        "AND rr.organization_id = research_run_steps.organization_id "
        "AND rr.tenant_id = research_run_steps.tenant_id "
        "AND rr.market = research_run_steps.market)"
    ),
    "research_run_evidence": (
        "EXISTS (SELECT 1 FROM research_runs rr "
        "WHERE rr.id = research_run_evidence.run_id "
        "AND rr.organization_id = research_run_evidence.organization_id "
        "AND rr.tenant_id = research_run_evidence.tenant_id "
        "AND rr.market = research_run_evidence.market)"
    ),
    "research_claims": (
        "EXISTS (SELECT 1 FROM research_runs rr "
        "WHERE rr.id = research_claims.run_id "
        "AND rr.organization_id = research_claims.organization_id "
        "AND rr.tenant_id = research_claims.tenant_id "
        "AND rr.market = research_claims.market)"
    ),
    "research_claim_citations": (
        "EXISTS (SELECT 1 FROM research_claims rc "
        "WHERE rc.id = research_claim_citations.claim_id "
        "AND rc.organization_id = research_claim_citations.organization_id "
        "AND rc.tenant_id = research_claim_citations.tenant_id "
        "AND rc.market = research_claim_citations.market)"
    ),
    "research_audit_events": _workspace_access(
        "research_audit_events", "research_audit_events.workspace_id"
    ),
}


def upgrade() -> None:
    for table in _TABLES:
        policy = f"{table}_tenant_market_isolation"
        private_scope = _PRIVATE_SCOPES.get(table)
        predicate = (
            _TENANT_SCOPE
            if private_scope is None
            else f"{_TENANT_SCOPE} AND ({private_scope})"
        )
        op.execute(sa.text(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY'))
        op.execute(sa.text(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY'))
        op.execute(sa.text(f'DROP POLICY IF EXISTS "{policy}" ON "{table}"'))
        op.execute(
            sa.text(
                f'CREATE POLICY "{policy}" ON "{table}" '
                f"USING ({predicate}) WITH CHECK ({predicate})"
            )
        )


def downgrade() -> None:
    # Security reconciliation is forward-only; restoring weaker historical policies is unsafe.
    pass
