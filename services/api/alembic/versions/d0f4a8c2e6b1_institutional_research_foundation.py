"""Add tenant-bound institutional research and evidence lineage.

Revision ID: d0f4a8c2e6b1
Revises: caa7b5fd5b0b
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "d0f4a8c2e6b1"
down_revision = "caa7b5fd5b0b"
branch_labels = None
depends_on = None

_RESEARCH_TABLES = (
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


def _json_column(name: str) -> sa.Column:
    return sa.Column(
        name,
        postgresql.JSONB(astext_type=sa.Text()),
        server_default=sa.text("'{}'::jsonb"),
        nullable=False,
    )


def _enable_tenant_rls(table: str) -> None:
    policy = f"{table}_tenant_market_isolation"
    private_scope = _PRIVATE_SCOPES.get(table)
    predicate = _TENANT_SCOPE if private_scope is None else f"{_TENANT_SCOPE} AND ({private_scope})"
    op.execute(sa.text(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY'))
    op.execute(sa.text(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY'))
    op.execute(
        sa.text(
            f'CREATE POLICY "{policy}" ON "{table}" USING ({predicate}) WITH CHECK ({predicate})'
        )
    )


def upgrade() -> None:
    op.create_unique_constraint("uq_users_id_tenant", "users", ["id", "tenant_id"])

    op.create_table(
        "research_organizations",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("market", sa.String(8), nullable=False),
        sa.Column("slug", sa.String(64), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("status", sa.String(16), server_default="active", nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "slug ~ '^[a-z0-9]+(?:-[a-z0-9]+)*$'", name="ck_research_organizations_slug"
        ),
        sa.CheckConstraint(
            "status IN ('active', 'suspended', 'closed')",
            name="ck_research_organizations_status",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id", "tenant_id"],
            ["users.id", "users.tenant_id"],
            name="fk_research_organizations_creator_tenant",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "id", "tenant_id", "market", name="uq_research_organizations_security_scope"
        ),
        sa.UniqueConstraint("tenant_id", "slug", name="uq_research_organizations_tenant_slug"),
    )
    op.create_index(
        "ix_research_organizations_tenant_status",
        "research_organizations",
        ["tenant_id", "status"],
    )

    op.create_table(
        "research_organization_memberships",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("market", sa.String(8), nullable=False),
        sa.Column("role", sa.String(16), server_default="member", nullable=False),
        sa.Column("status", sa.String(16), server_default="invited", nullable=False),
        sa.Column("invited_by_user_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "role IN ('owner', 'admin', 'member')",
            name="ck_research_organization_memberships_role",
        ),
        sa.CheckConstraint(
            "status IN ('invited', 'active', 'disabled')",
            name="ck_research_organization_memberships_status",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "tenant_id", "market"],
            [
                "research_organizations.id",
                "research_organizations.tenant_id",
                "research_organizations.market",
            ],
            name="fk_research_org_memberships_organization_scope",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id", "tenant_id"],
            ["users.id", "users.tenant_id"],
            name="fk_research_org_memberships_user_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["invited_by_user_id", "tenant_id"],
            ["users.id", "users.tenant_id"],
            name="fk_research_org_memberships_inviter_tenant",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("organization_id", "user_id"),
        sa.UniqueConstraint(
            "organization_id",
            "user_id",
            "tenant_id",
            "market",
            name="uq_research_org_memberships_security_scope",
        ),
    )
    op.create_index(
        "ix_research_org_memberships_tenant_user_status",
        "research_organization_memberships",
        ["tenant_id", "user_id", "status"],
    )

    op.create_table(
        "research_workspaces",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("market", sa.String(8), nullable=False),
        sa.Column("slug", sa.String(64), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("status", sa.String(16), server_default="active", nullable=False),
        sa.Column("base_currency", sa.String(3), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "base_currency ~ '^[A-Z]{3}$'", name="ck_research_workspaces_base_currency"
        ),
        sa.CheckConstraint(
            "slug ~ '^[a-z0-9]+(?:-[a-z0-9]+)*$'", name="ck_research_workspaces_slug"
        ),
        sa.CheckConstraint(
            "status IN ('active', 'archived')", name="ck_research_workspaces_status"
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "tenant_id", "market"],
            [
                "research_organizations.id",
                "research_organizations.tenant_id",
                "research_organizations.market",
            ],
            name="fk_research_workspaces_organization_scope",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "created_by_user_id", "tenant_id", "market"],
            [
                "research_organization_memberships.organization_id",
                "research_organization_memberships.user_id",
                "research_organization_memberships.tenant_id",
                "research_organization_memberships.market",
            ],
            name="fk_research_workspaces_creator_membership",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "id",
            "organization_id",
            "tenant_id",
            "market",
            name="uq_research_workspaces_security_scope",
        ),
        sa.UniqueConstraint(
            "organization_id", "slug", name="uq_research_workspaces_organization_slug"
        ),
    )
    op.create_index(
        "ix_research_workspaces_tenant_organization_status",
        "research_workspaces",
        ["tenant_id", "organization_id", "status"],
    )

    op.create_table(
        "research_workspace_memberships",
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("market", sa.String(8), nullable=False),
        sa.Column("role", sa.String(24), nullable=False),
        sa.Column("status", sa.String(16), server_default="active", nullable=False),
        sa.Column("granted_by_user_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "role IN ('portfolio_manager', 'analyst', 'risk', 'viewer')",
            name="ck_research_workspace_memberships_role",
        ),
        sa.CheckConstraint(
            "status IN ('active', 'disabled')",
            name="ck_research_workspace_memberships_status",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "organization_id", "tenant_id", "market"],
            [
                "research_workspaces.id",
                "research_workspaces.organization_id",
                "research_workspaces.tenant_id",
                "research_workspaces.market",
            ],
            name="fk_research_workspace_memberships_workspace_scope",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "user_id", "tenant_id", "market"],
            [
                "research_organization_memberships.organization_id",
                "research_organization_memberships.user_id",
                "research_organization_memberships.tenant_id",
                "research_organization_memberships.market",
            ],
            name="fk_research_workspace_memberships_organization_member",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["granted_by_user_id", "tenant_id"],
            ["users.id", "users.tenant_id"],
            name="fk_research_workspace_memberships_granter_tenant",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("workspace_id", "user_id"),
    )
    op.create_index(
        "ix_research_workspace_memberships_tenant_user_status",
        "research_workspace_memberships",
        ["tenant_id", "user_id", "status"],
    )

    op.create_table(
        "research_runs",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("requested_by_user_id", sa.Integer(), nullable=False),
        sa.Column("run_kind", sa.String(24), nullable=False),
        sa.Column("status", sa.String(16), server_default="queued", nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("market", sa.String(8), nullable=False),
        sa.Column("code", sa.String(32), nullable=True),
        _json_column("parameters"),
        sa.Column("idempotency_key", sa.String(96), nullable=False),
        sa.Column("knowledge_cutoff_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("provider", sa.String(32), nullable=True),
        sa.Column("model", sa.String(96), nullable=True),
        sa.Column("prompt_version", sa.String(64), nullable=True),
        sa.Column("code_version", sa.String(64), nullable=False),
        sa.Column("evidence_snapshot_hash", sa.String(64), nullable=True),
        sa.Column(
            "requested_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.CheckConstraint("idempotency_key <> ''", name="ck_research_runs_idempotency_key"),
        sa.CheckConstraint("code_version <> ''", name="ck_research_runs_code_version"),
        sa.CheckConstraint(
            "evidence_snapshot_hash IS NULL OR evidence_snapshot_hash ~ '^[0-9a-f]{64}$'",
            name="ck_research_runs_evidence_snapshot_hash",
        ),
        sa.CheckConstraint(
            "run_kind IN ('dossier', 'deep_research', 'hypothesis', 'monitor', 'portfolio')",
            name="ck_research_runs_kind",
        ),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled')",
            name="ck_research_runs_status",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "organization_id", "tenant_id", "market"],
            [
                "research_workspaces.id",
                "research_workspaces.organization_id",
                "research_workspaces.tenant_id",
                "research_workspaces.market",
            ],
            name="fk_research_runs_workspace",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "requested_by_user_id", "tenant_id", "market"],
            [
                "research_organization_memberships.organization_id",
                "research_organization_memberships.user_id",
                "research_organization_memberships.tenant_id",
                "research_organization_memberships.market",
            ],
            name="fk_research_runs_requester_membership",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "id",
            "organization_id",
            "tenant_id",
            "market",
            name="uq_research_runs_security_scope",
        ),
        sa.UniqueConstraint(
            "workspace_id", "idempotency_key", name="uq_research_runs_workspace_idempotency_key"
        ),
    )
    op.create_index(
        "ix_research_runs_tenant_organization_status",
        "research_runs",
        ["tenant_id", "organization_id", "status"],
    )
    op.create_index(
        "ix_research_runs_security_cutoff",
        "research_runs",
        ["market", "code", "knowledge_cutoff_at"],
    )
    op.create_index(
        "ix_research_runs_workspace_requested",
        "research_runs",
        ["workspace_id", "requested_at"],
    )

    op.create_table(
        "research_run_steps",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("market", sa.String(8), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("step_kind", sa.String(48), nullable=False),
        sa.Column("status", sa.String(16), server_default="queued", nullable=False),
        sa.Column("input_hash", sa.String(64), nullable=True),
        _json_column("output"),
        _json_column("metrics"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.CheckConstraint("ordinal >= 0", name="ck_research_run_steps_ordinal"),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed', 'skipped')",
            name="ck_research_run_steps_status",
        ),
        sa.ForeignKeyConstraint(
            ["run_id", "organization_id", "tenant_id", "market"],
            [
                "research_runs.id",
                "research_runs.organization_id",
                "research_runs.tenant_id",
                "research_runs.market",
            ],
            name="fk_research_run_steps_run",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "id",
            "organization_id",
            "tenant_id",
            "market",
            name="uq_research_run_steps_security_scope",
        ),
        sa.UniqueConstraint("run_id", "ordinal", name="uq_research_run_steps_run_ordinal"),
    )
    op.create_index("ix_research_run_steps_run_status", "research_run_steps", ["run_id", "status"])

    op.create_table(
        "research_evidence_documents",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("market", sa.String(8), nullable=False),
        sa.Column("source_type", sa.String(48), nullable=False),
        sa.Column("source_record_id", sa.String(192), nullable=False),
        sa.Column("source_revision", sa.String(96), nullable=False),
        sa.Column("code", sa.String(32), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("known_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "ingested_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("object_key", sa.Text(), nullable=True),
        sa.Column("media_type", sa.String(96), nullable=False),
        _json_column("attributes"),
        sa.CheckConstraint(
            "content_hash ~ '^[0-9a-f]{64}$'", name="ck_research_evidence_content_hash"
        ),
        sa.CheckConstraint("source_revision <> ''", name="ck_research_evidence_source_revision"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "id",
            "tenant_id",
            "market",
            name="uq_research_evidence_documents_security_scope",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "market",
            "source_type",
            "source_record_id",
            "source_revision",
            name="uq_research_evidence_documents_source_revision",
        ),
    )
    op.create_index(
        "ix_research_evidence_documents_tenant_content_hash",
        "research_evidence_documents",
        ["tenant_id", "market", "content_hash"],
    )
    op.create_index(
        "ix_research_evidence_documents_tenant_security_known",
        "research_evidence_documents",
        ["tenant_id", "market", "code", "known_at"],
    )

    op.create_table(
        "research_evidence_spans",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("market", sa.String(8), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        _json_column("locator"),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("text_hash", sa.String(64), nullable=False),
        sa.Column("token_count", sa.Integer(), server_default="0", nullable=False),
        sa.CheckConstraint("ordinal >= 0", name="ck_research_evidence_spans_ordinal"),
        sa.CheckConstraint(
            "text_hash ~ '^[0-9a-f]{64}$'", name="ck_research_evidence_spans_text_hash"
        ),
        sa.CheckConstraint("token_count >= 0", name="ck_research_evidence_spans_token_count"),
        sa.ForeignKeyConstraint(
            ["document_id", "tenant_id", "market"],
            [
                "research_evidence_documents.id",
                "research_evidence_documents.tenant_id",
                "research_evidence_documents.market",
            ],
            name="fk_research_evidence_spans_document_scope",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "id", "tenant_id", "market", name="uq_research_evidence_spans_security_scope"
        ),
        sa.UniqueConstraint(
            "document_id", "ordinal", name="uq_research_evidence_spans_document_ordinal"
        ),
    )
    op.create_index(
        "ix_research_evidence_spans_document",
        "research_evidence_spans",
        ["document_id", "ordinal"],
    )

    op.create_table(
        "research_run_evidence",
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("evidence_document_id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("market", sa.String(8), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("disposition", sa.String(16), nullable=False),
        sa.Column("purpose", sa.String(16), nullable=True),
        sa.Column("retrieval_method", sa.String(48), nullable=False),
        sa.Column("retrieval_score", sa.Numeric(12, 8), nullable=True),
        sa.Column("rerank_score", sa.Numeric(12, 8), nullable=True),
        sa.Column("rationale", sa.Text(), nullable=True),
        _json_column("attributes"),
        sa.CheckConstraint("ordinal >= 0", name="ck_research_run_evidence_ordinal"),
        sa.CheckConstraint(
            "disposition IN ('selected', 'rejected', 'unused')",
            name="ck_research_run_evidence_disposition",
        ),
        sa.CheckConstraint(
            "purpose IS NULL OR purpose IN ('supporting', 'counter', 'context', 'calculation')",
            name="ck_research_run_evidence_purpose",
        ),
        sa.ForeignKeyConstraint(
            ["run_id", "organization_id", "tenant_id", "market"],
            [
                "research_runs.id",
                "research_runs.organization_id",
                "research_runs.tenant_id",
                "research_runs.market",
            ],
            name="fk_research_run_evidence_run_scope",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["evidence_document_id", "tenant_id", "market"],
            [
                "research_evidence_documents.id",
                "research_evidence_documents.tenant_id",
                "research_evidence_documents.market",
            ],
            name="fk_research_run_evidence_document_scope",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("run_id", "evidence_document_id"),
        sa.UniqueConstraint("run_id", "ordinal", name="uq_research_run_evidence_run_ordinal"),
    )
    op.create_index(
        "ix_research_run_evidence_document",
        "research_run_evidence",
        ["evidence_document_id"],
    )

    op.create_table(
        "research_claims",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("market", sa.String(8), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("claim_type", sa.String(48), nullable=False),
        sa.Column("statement", sa.Text(), nullable=False),
        sa.Column("verdict", sa.String(16), nullable=False),
        sa.Column("confidence", sa.Numeric(5, 4), nullable=False),
        sa.Column("as_of_at", sa.DateTime(timezone=True), nullable=False),
        _json_column("values"),
        _json_column("verification"),
        sa.CheckConstraint("ordinal >= 0", name="ck_research_claims_ordinal"),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 1", name="ck_research_claims_confidence"
        ),
        sa.CheckConstraint(
            "verdict IN ('supported', 'mixed', 'unsupported', 'unknown')",
            name="ck_research_claims_verdict",
        ),
        sa.ForeignKeyConstraint(
            ["run_id", "organization_id", "tenant_id", "market"],
            [
                "research_runs.id",
                "research_runs.organization_id",
                "research_runs.tenant_id",
                "research_runs.market",
            ],
            name="fk_research_claims_run_scope",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "id",
            "organization_id",
            "tenant_id",
            "market",
            name="uq_research_claims_security_scope",
        ),
        sa.UniqueConstraint("run_id", "ordinal", name="uq_research_claims_run_ordinal"),
    )
    op.create_index("ix_research_claims_run_verdict", "research_claims", ["run_id", "verdict"])

    op.create_table(
        "research_claim_citations",
        sa.Column("claim_id", sa.Uuid(), nullable=False),
        sa.Column("evidence_span_id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("market", sa.String(8), nullable=False),
        sa.Column("relation", sa.String(16), nullable=False),
        sa.Column("relevance", sa.Numeric(5, 4), nullable=False),
        sa.CheckConstraint(
            "relation IN ('supports', 'contradicts', 'context')",
            name="ck_research_claim_citations_relation",
        ),
        sa.CheckConstraint(
            "relevance >= 0 AND relevance <= 1",
            name="ck_research_claim_citations_relevance",
        ),
        sa.ForeignKeyConstraint(
            ["claim_id", "organization_id", "tenant_id", "market"],
            [
                "research_claims.id",
                "research_claims.organization_id",
                "research_claims.tenant_id",
                "research_claims.market",
            ],
            name="fk_research_claim_citations_claim_scope",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["evidence_span_id", "tenant_id", "market"],
            [
                "research_evidence_spans.id",
                "research_evidence_spans.tenant_id",
                "research_evidence_spans.market",
            ],
            name="fk_research_claim_citations_evidence_span_scope",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("claim_id", "evidence_span_id"),
    )
    op.create_index(
        "ix_research_claim_citations_evidence_span",
        "research_claim_citations",
        ["evidence_span_id"],
    )

    op.create_table(
        "research_audit_events",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("market", sa.String(8), nullable=False),
        sa.Column("actor_user_id", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("resource_type", sa.String(48), nullable=False),
        sa.Column("resource_id", sa.String(160), nullable=False),
        sa.Column("request_id", sa.String(128), nullable=True),
        _json_column("attributes"),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "event_type <> ''",
            name="ck_research_audit_events_event_type",
        ),
        sa.CheckConstraint(
            "resource_type <> ''",
            name="ck_research_audit_events_resource_type",
        ),
        sa.CheckConstraint(
            "resource_id <> ''",
            name="ck_research_audit_events_resource_id",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "organization_id", "tenant_id", "market"],
            [
                "research_workspaces.id",
                "research_workspaces.organization_id",
                "research_workspaces.tenant_id",
                "research_workspaces.market",
            ],
            name="fk_research_audit_events_workspace_scope",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "actor_user_id", "tenant_id", "market"],
            [
                "research_organization_memberships.organization_id",
                "research_organization_memberships.user_id",
                "research_organization_memberships.tenant_id",
                "research_organization_memberships.market",
            ],
            name="fk_research_audit_events_actor_scope",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_research_audit_events_workspace_occurred",
        "research_audit_events",
        ["workspace_id", "occurred_at"],
    )
    op.create_index(
        "ix_research_audit_events_org_actor_occurred",
        "research_audit_events",
        ["organization_id", "actor_user_id", "occurred_at"],
    )
    op.execute(
        sa.text(
            "CREATE FUNCTION reject_research_audit_mutation() RETURNS trigger "
            "LANGUAGE plpgsql AS $$ BEGIN "
            "IF current_user = pg_get_userbyid((SELECT relowner FROM pg_class WHERE oid = TG_RELID)) "
            "THEN RETURN OLD; END IF; "
            "RAISE EXCEPTION 'research audit events are append-only' USING ERRCODE = '55000'; "
            "END; $$"
        )
    )
    op.execute(
        sa.text(
            "CREATE TRIGGER research_audit_events_append_only "
            "BEFORE UPDATE OR DELETE ON research_audit_events "
            "FOR EACH ROW EXECUTE FUNCTION reject_research_audit_mutation()"
        )
    )

    for table in _RESEARCH_TABLES:
        _enable_tenant_rls(table)


def downgrade() -> None:
    # Several parent-table policies join membership/lineage tables. Remove every
    # policy before dropping tables so PostgreSQL does not retain cross-table
    # policy dependencies during the reverse migration.
    for table in _RESEARCH_TABLES:
        op.execute(
            sa.text(
                f'DROP POLICY IF EXISTS "{table}_tenant_market_isolation" ON "{table}"'
            )
        )
    for table in reversed(_RESEARCH_TABLES):
        op.drop_table(table)
    op.execute(sa.text("DROP FUNCTION reject_research_audit_mutation()"))
    op.drop_constraint("uq_users_id_tenant", "users", type_="unique")
