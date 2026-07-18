"""Add Atlas mandates, strategy trials, and append-only decision lineage.

Revision ID: c8f2d5a7e9b1
Revises: b7e1c4d6f8a0
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "c8f2d5a7e9b1"
down_revision = "b7e1c4d6f8a0"
branch_labels = None
depends_on = None

_USER_ID = "NULLIF(current_setting('app.research_user_id', true), '')::integer"
_TENANT_SCOPE = (
    "tenant_id = current_setting('app.research_tenant_id', true) "
    "AND market = current_setting('app.research_market', true)"
)


def _workspace_access(table: str) -> str:
    return (
        "EXISTS (SELECT 1 FROM research_organization_memberships rom "
        f"WHERE rom.organization_id = {table}.organization_id "
        f"AND rom.tenant_id = {table}.tenant_id AND rom.market = {table}.market "
        f"AND rom.user_id = {_USER_ID} AND rom.status = 'active' "
        "AND (rom.role IN ('owner', 'admin') OR EXISTS ("
        "SELECT 1 FROM research_workspace_memberships rwm "
        f"WHERE rwm.workspace_id = {table}.workspace_id "
        f"AND rwm.organization_id = {table}.organization_id "
        f"AND rwm.tenant_id = {table}.tenant_id AND rwm.market = {table}.market "
        f"AND rwm.user_id = {_USER_ID} AND rwm.status = 'active')))"
    )


def _enable_rls(table: str) -> None:
    policy = f"{table}_tenant_market_isolation"
    predicate = f"{_TENANT_SCOPE} AND ({_workspace_access(table)})"
    op.execute(sa.text(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY'))
    op.execute(sa.text(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY'))
    op.execute(
        sa.text(
            f'CREATE POLICY "{policy}" ON "{table}" USING ({predicate}) WITH CHECK ({predicate})'
        )
    )


def _json(name: str) -> sa.Column:
    return sa.Column(
        name,
        postgresql.JSONB(astext_type=sa.Text()),
        server_default=sa.text("'{}'::jsonb"),
        nullable=False,
    )


def upgrade() -> None:
    op.create_table(
        "research_investment_mandates",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("market", sa.String(8), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), server_default="active", nullable=False),
        sa.Column("objective", sa.Text(), nullable=False),
        sa.Column("benchmark_key", sa.String(64), nullable=False),
        sa.Column("max_gross_exposure_pct", sa.Numeric(7, 3), nullable=False),
        sa.Column("min_cash_reserve_pct", sa.Numeric(7, 3), nullable=False),
        sa.Column("max_position_weight_pct", sa.Numeric(7, 3), nullable=False),
        sa.Column("max_sector_weight_pct", sa.Numeric(7, 3), nullable=False),
        sa.Column("max_adv_participation_pct", sa.Numeric(7, 3), nullable=False),
        sa.Column("portfolio_drawdown_brake_pct", sa.Numeric(7, 3), nullable=False),
        sa.Column("stress_loss_limit_pct", sa.Numeric(7, 3), nullable=False),
        sa.Column("specification_hash", sa.String(64), nullable=False),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('active', 'superseded')",
            name="ck_research_investment_mandates_status",
        ),
        sa.CheckConstraint("version >= 1", name="ck_research_investment_mandates_version"),
        sa.CheckConstraint(
            "max_gross_exposure_pct > 0 AND max_gross_exposure_pct <= 100 "
            "AND min_cash_reserve_pct >= 0 AND min_cash_reserve_pct < 100 "
            "AND max_gross_exposure_pct + min_cash_reserve_pct <= 100 "
            "AND max_position_weight_pct > 0 AND max_position_weight_pct <= 100 "
            "AND max_position_weight_pct <= max_gross_exposure_pct "
            "AND max_sector_weight_pct > 0 AND max_sector_weight_pct <= 100 "
            "AND max_sector_weight_pct >= max_position_weight_pct "
            "AND max_adv_participation_pct > 0 AND max_adv_participation_pct <= 100 "
            "AND portfolio_drawdown_brake_pct > 0 AND portfolio_drawdown_brake_pct <= 100 "
            "AND stress_loss_limit_pct > 0 AND stress_loss_limit_pct <= 100",
            name="ck_research_investment_mandates_limits",
        ),
        sa.CheckConstraint(
            "specification_hash ~ '^[0-9a-f]{64}$'",
            name="ck_research_investment_mandates_hash",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "organization_id", "tenant_id", "market"],
            [
                "research_workspaces.id",
                "research_workspaces.organization_id",
                "research_workspaces.tenant_id",
                "research_workspaces.market",
            ],
            name="fk_research_investment_mandates_workspace",
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
            name="fk_research_investment_mandates_creator",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "id",
            "organization_id",
            "tenant_id",
            "market",
            name="uq_research_investment_mandates_security_scope",
        ),
        sa.UniqueConstraint(
            "workspace_id", "version", name="uq_research_investment_mandates_version"
        ),
    )
    op.create_index(
        "ix_research_investment_mandates_workspace_status",
        "research_investment_mandates",
        ["workspace_id", "status"],
    )
    op.create_index(
        "uq_research_investment_mandates_active_workspace",
        "research_investment_mandates",
        ["workspace_id"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )

    op.create_table(
        "research_strategy_trials",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("market", sa.String(8), nullable=False),
        sa.Column("source_run_id", sa.Uuid(), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=False),
        sa.Column("strategy_key", sa.String(48), nullable=False),
        sa.Column("strategy_version", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), server_default="registered", nullable=False),
        sa.Column("registration_state", sa.String(24), nullable=False),
        sa.Column("trial_sequence", sa.Integer(), nullable=False),
        sa.Column("multiple_testing_policy", sa.String(64), nullable=False),
        sa.Column("economic_hypothesis", sa.Text(), nullable=False),
        _json("specification"),
        sa.Column("specification_hash", sa.String(64), nullable=False),
        _json("outcome"),
        sa.Column("registered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('registered', 'diagnostic', 'shadow', 'eligible', 'rejected', 'retired')",
            name="ck_research_strategy_trials_status",
        ),
        sa.CheckConstraint(
            "registration_state IN ('preregistered', 'legacy_reconstructed')",
            name="ck_research_strategy_trials_registration_state",
        ),
        sa.CheckConstraint("trial_sequence >= 1", name="ck_research_strategy_trials_sequence"),
        sa.CheckConstraint(
            "multiple_testing_policy <> ''",
            name="ck_research_strategy_trials_multiple_testing_policy",
        ),
        sa.CheckConstraint(
            "specification_hash ~ '^[0-9a-f]{64}$'",
            name="ck_research_strategy_trials_hash",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "organization_id", "tenant_id", "market"],
            [
                "research_workspaces.id",
                "research_workspaces.organization_id",
                "research_workspaces.tenant_id",
                "research_workspaces.market",
            ],
            name="fk_research_strategy_trials_workspace",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_run_id", "organization_id", "tenant_id", "market"],
            [
                "research_runs.id",
                "research_runs.organization_id",
                "research_runs.tenant_id",
                "research_runs.market",
            ],
            name="fk_research_strategy_trials_source_run",
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
            name="fk_research_strategy_trials_creator",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "id",
            "organization_id",
            "tenant_id",
            "market",
            name="uq_research_strategy_trials_security_scope",
        ),
        sa.UniqueConstraint("source_run_id", name="uq_research_strategy_trials_source_run"),
        sa.UniqueConstraint(
            "workspace_id",
            "strategy_key",
            "trial_sequence",
            name="uq_research_strategy_trials_family_sequence",
        ),
    )
    op.create_index(
        "ix_research_strategy_trials_workspace_status",
        "research_strategy_trials",
        ["workspace_id", "status", "registered_at"],
    )

    op.create_table(
        "research_decision_events",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("market", sa.String(8), nullable=False),
        sa.Column("portfolio_id", sa.Uuid(), nullable=False),
        sa.Column("snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("correlation_id", sa.Uuid(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("event_key", sa.String(160), nullable=False),
        sa.Column("caused_by_event_key", sa.String(160), nullable=True),
        sa.Column("event_type", sa.String(16), nullable=False),
        sa.Column("event_state", sa.String(16), nullable=False),
        sa.Column("code", sa.String(32), nullable=True),
        sa.Column("effective_date", sa.Date(), nullable=False),
        _json("payload"),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("sequence >= 0", name="ck_research_decision_events_sequence"),
        sa.CheckConstraint(
            "event_type IN ('signal', 'target', 'order', 'rejection', 'fill', 'position', 'risk', 'outcome')",
            name="ck_research_decision_events_type",
        ),
        sa.CheckConstraint(
            "event_state IN ('observed', 'intended', 'constrained', 'executed', 'open', 'closed', 'measured')",
            name="ck_research_decision_events_state",
        ),
        sa.CheckConstraint("event_key <> ''", name="ck_research_decision_events_key"),
        sa.CheckConstraint(
            "payload_hash ~ '^[0-9a-f]{64}$'",
            name="ck_research_decision_events_payload_hash",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "organization_id", "tenant_id", "market"],
            [
                "research_workspaces.id",
                "research_workspaces.organization_id",
                "research_workspaces.tenant_id",
                "research_workspaces.market",
            ],
            name="fk_research_decision_events_workspace",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["portfolio_id", "organization_id", "tenant_id", "market"],
            [
                "research_shadow_portfolios.id",
                "research_shadow_portfolios.organization_id",
                "research_shadow_portfolios.tenant_id",
                "research_shadow_portfolios.market",
            ],
            name="fk_research_decision_events_portfolio",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["snapshot_id", "organization_id", "tenant_id", "market"],
            [
                "research_shadow_snapshots.id",
                "research_shadow_snapshots.organization_id",
                "research_shadow_snapshots.tenant_id",
                "research_shadow_snapshots.market",
            ],
            name="fk_research_decision_events_snapshot",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "id",
            "organization_id",
            "tenant_id",
            "market",
            name="uq_research_decision_events_security_scope",
        ),
        sa.UniqueConstraint(
            "portfolio_id", "sequence", name="uq_research_decision_events_sequence"
        ),
        sa.UniqueConstraint("portfolio_id", "event_key", name="uq_research_decision_events_key"),
    )
    op.create_index(
        "ix_research_decision_events_workspace_recorded",
        "research_decision_events",
        ["workspace_id", "recorded_at"],
    )
    op.create_index(
        "ix_research_decision_events_portfolio_effective",
        "research_decision_events",
        ["portfolio_id", "effective_date", "sequence"],
    )

    # Existing workspaces receive the same conservative limits already used by the deterministic
    # engine. This does not change any active strategy or claim historical preregistration.
    op.execute(
        sa.text(
            "INSERT INTO research_investment_mandates ("
            "organization_id, workspace_id, tenant_id, market, created_by_user_id, version, "
            "status, objective, benchmark_key, max_gross_exposure_pct, min_cash_reserve_pct, "
            "max_position_weight_pct, max_sector_weight_pct, max_adv_participation_pct, "
            "portfolio_drawdown_brake_pct, stress_loss_limit_pct, specification_hash, effective_at"
            ") SELECT organization_id, id, tenant_id, market, created_by_user_id, 1, 'active', "
            "'Capital preservation and benchmark-relative compounding through registered long-only strategies.', "
            "CASE WHEN market = 'DSE' THEN 'dsex_equal_weight_proxy' ELSE 'us_equal_weight_proxy' END, "
            "CASE WHEN market = 'DSE' THEN 85 ELSE 90 END, "
            "CASE WHEN market = 'DSE' THEN 15 ELSE 10 END, "
            "CASE WHEN market = 'DSE' THEN 12 ELSE 10 END, "
            "CASE WHEN market = 'DSE' THEN 30 ELSE 25 END, "
            "CASE WHEN market = 'DSE' THEN 2 ELSE 5 END, "
            "CASE WHEN market = 'DSE' THEN 15 ELSE 18 END, "
            "CASE WHEN market = 'DSE' THEN 12 ELSE 15 END, "
            "md5(market || '-atlas-default-mandate-v1') || "
            "md5('atlas-' || market || '-atlas-default-mandate-v1'), now() "
            "FROM research_workspaces"
        )
    )
    op.execute(
        sa.text(
            "INSERT INTO research_strategy_trials ("
            "organization_id, workspace_id, tenant_id, market, source_run_id, created_by_user_id, "
            "strategy_key, strategy_version, status, registration_state, trial_sequence, "
            "multiple_testing_policy, economic_hypothesis, "
            "specification, specification_hash, outcome, registered_at, completed_at"
            ") SELECT r.organization_id, r.workspace_id, r.tenant_id, r.market, r.id, "
            "r.requested_by_user_id, COALESCE(r.parameters->>'strategy_key', 'unknown'), "
            "COALESCE(r.parameters#>>'{result_summary,strategy,methodology_version}', r.code_version), "
            "CASE WHEN EXISTS (SELECT 1 FROM research_shadow_portfolios p WHERE p.source_run_id = r.id) "
            "THEN 'shadow' ELSE 'diagnostic' END, 'legacy_reconstructed', "
            "(row_number() OVER (PARTITION BY r.workspace_id, r.parameters->>'strategy_key' "
            "ORDER BY r.requested_at, r.id))::integer, 'family_gate_v1', "
            "'Legacy experiment reconstructed after execution; no preregistration claim is made.', "
            "jsonb_build_object('parameters', r.parameters - 'result_summary', "
            "'code_version', r.code_version, 'evidence_snapshot_hash', r.evidence_snapshot_hash), "
            "md5((r.parameters - 'result_summary')::text || r.code_version) || "
            "md5('atlas-' || (r.parameters - 'result_summary')::text || r.code_version), "
            "COALESCE(r.parameters->'result_summary', '{}'::jsonb), r.requested_at, r.completed_at "
            "FROM research_runs r WHERE r.run_kind = 'hypothesis'"
        )
    )
    op.execute(
        sa.text(
            "UPDATE research_shadow_portfolios p SET configuration = p.configuration || "
            "jsonb_build_object('mandate_binding', 'legacy_migration', 'mandate', "
            "jsonb_build_object('id', m.id::text, 'workspace_id', m.workspace_id::text, "
            "'tenant_id', m.tenant_id, 'market', m.market, 'version', m.version, "
            "'status', m.status, 'objective', m.objective, 'benchmark_key', m.benchmark_key, "
            "'max_gross_exposure_pct', m.max_gross_exposure_pct, "
            "'min_cash_reserve_pct', m.min_cash_reserve_pct, "
            "'max_position_weight_pct', m.max_position_weight_pct, "
            "'max_sector_weight_pct', m.max_sector_weight_pct, "
            "'max_adv_participation_pct', m.max_adv_participation_pct, "
            "'portfolio_drawdown_brake_pct', m.portfolio_drawdown_brake_pct, "
            "'stress_loss_limit_pct', m.stress_loss_limit_pct, "
            "'specification_hash', m.specification_hash, "
            "'effective_at', m.effective_at, 'superseded_at', m.superseded_at)) "
            "FROM research_investment_mandates m WHERE m.workspace_id = p.workspace_id "
            "AND m.organization_id = p.organization_id AND m.tenant_id = p.tenant_id "
            "AND m.market = p.market AND m.status = 'active'"
        )
    )

    for table in (
        "research_investment_mandates",
        "research_strategy_trials",
        "research_decision_events",
    ):
        _enable_rls(table)

    op.execute(
        sa.text(
            "CREATE FUNCTION reject_research_decision_event_mutation() RETURNS trigger "
            "LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION "
            "'research_decision_events are append-only'; END; $$"
        )
    )
    op.execute(
        sa.text(
            "CREATE TRIGGER research_decision_events_append_only "
            "BEFORE UPDATE OR DELETE ON research_decision_events "
            "FOR EACH ROW EXECUTE FUNCTION reject_research_decision_event_mutation()"
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "DROP TRIGGER IF EXISTS research_decision_events_append_only "
            "ON research_decision_events"
        )
    )
    op.execute(sa.text("DROP FUNCTION IF EXISTS reject_research_decision_event_mutation()"))
    for table in (
        "research_decision_events",
        "research_strategy_trials",
        "research_investment_mandates",
    ):
        op.execute(sa.text(f"DROP POLICY IF EXISTS {table}_tenant_market_isolation ON {table}"))
        op.drop_table(table)
