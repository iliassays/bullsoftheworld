"""Stable security IDs and auditable universe onboarding.

Revision ID: 3c4d5e6f7a8b
Revises: 2b3c4d5e6f7a
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "3c4d5e6f7a8b"
down_revision = "2b3c4d5e6f7a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "security_master",
        sa.Column(
            "security_id",
            sa.Uuid(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_security_master_security_id",
        "security_master",
        ["security_id"],
        unique=True,
    )
    op.add_column("symbols", sa.Column("security_id", sa.Uuid(), nullable=True))
    op.execute(
        "UPDATE symbols s SET security_id = sm.security_id "
        "FROM security_master sm WHERE s.market = sm.market AND s.code = sm.symbol"
    )
    op.create_index("ix_symbols_security_id", "symbols", ["security_id"], unique=False)
    op.create_foreign_key(
        "fk_symbols_security_id_security_master",
        "symbols",
        "security_master",
        ["security_id"],
        ["security_id"],
    )

    op.create_table(
        "universe_onboarding_runs",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("market", sa.String(length=8), nullable=False),
        sa.Column("cohort_name", sa.String(length=96), nullable=False),
        sa.Column("cohort_version", sa.String(length=32), nullable=False),
        sa.Column("manifest_sha256", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("promotion_requested", sa.Boolean(), nullable=False),
        sa.Column("requested_count", sa.Integer(), nullable=False),
        sa.Column("passed_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("failed_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("parameters", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('running', 'completed', 'failed')",
            name="ck_universe_onboarding_run_status",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_universe_onboarding_runs_market",
        "universe_onboarding_runs",
        ["market"],
    )
    op.create_index(
        "ix_universe_onboarding_runs_status",
        "universe_onboarding_runs",
        ["status"],
    )
    op.create_index(
        "uq_universe_onboarding_runs_active_manifest",
        "universe_onboarding_runs",
        ["manifest_sha256"],
        unique=True,
        postgresql_where=sa.text("status = 'running'"),
    )
    op.create_table(
        "universe_onboarding_results",
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("market", sa.String(length=8), nullable=False),
        sa.Column("code", sa.String(length=16), nullable=False),
        sa.Column("security_id", sa.Uuid(), nullable=True),
        sa.Column("decision", sa.String(length=16), nullable=False),
        sa.Column("required_gates_passed", sa.Boolean(), nullable=False),
        sa.Column("gates", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("failure_reasons", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("bar_count", sa.Integer(), nullable=False),
        sa.Column("first_bar_date", sa.Date(), nullable=True),
        sa.Column("last_bar_date", sa.Date(), nullable=True),
        sa.Column("adjusted_close_ratio", sa.Float(), nullable=True),
        sa.Column("nonzero_volume_ratio", sa.Float(), nullable=True),
        sa.Column("sec_filings_count", sa.Integer(), nullable=False),
        sa.Column("sec_facts_count", sa.Integer(), nullable=False),
        sa.Column("has_13f", sa.Boolean(), nullable=False),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "decision IN ('passed', 'failed')",
            name="ck_universe_onboarding_result_decision",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["universe_onboarding_runs.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["security_id"], ["security_master.security_id"]),
        sa.PrimaryKeyConstraint("run_id", "code"),
    )
    op.create_index(
        "ix_universe_onboarding_results_decision",
        "universe_onboarding_results",
        ["decision"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_universe_onboarding_results_decision",
        table_name="universe_onboarding_results",
    )
    op.drop_table("universe_onboarding_results")
    op.drop_index(
        "uq_universe_onboarding_runs_active_manifest",
        table_name="universe_onboarding_runs",
        postgresql_where=sa.text("status = 'running'"),
    )
    op.drop_index("ix_universe_onboarding_runs_status", table_name="universe_onboarding_runs")
    op.drop_index("ix_universe_onboarding_runs_market", table_name="universe_onboarding_runs")
    op.drop_table("universe_onboarding_runs")
    op.drop_constraint(
        "fk_symbols_security_id_security_master",
        "symbols",
        type_="foreignkey",
    )
    op.drop_index("ix_symbols_security_id", table_name="symbols")
    op.drop_column("symbols", "security_id")
    op.drop_index("ix_security_master_security_id", table_name="security_master")
    op.drop_column("security_master", "security_id")
