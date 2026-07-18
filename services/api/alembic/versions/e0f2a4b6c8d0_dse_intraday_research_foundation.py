"""Add partitioned DSE intraday research observations and quality controls.

Revision ID: e0f2a4b6c8d0
Revises: c8f2d5a7e9b1
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "e0f2a4b6c8d0"
down_revision = "c8f2d5a7e9b1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "intraday_quote_observations",
        sa.Column("market", sa.String(length=8), nullable=False),
        sa.Column("code", sa.String(length=16), nullable=False),
        sa.Column("session_date", sa.Date(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("capture_slot", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ltp", sa.Float(), nullable=False),
        sa.Column("open", sa.Float(), nullable=True),
        sa.Column("high", sa.Float(), nullable=False),
        sa.Column("low", sa.Float(), nullable=False),
        sa.Column("close", sa.Float(), nullable=False),
        sa.Column("prev_close", sa.Float(), nullable=True),
        sa.Column("volume", sa.BigInteger(), nullable=False),
        sa.Column("trades", sa.Integer(), nullable=False),
        sa.Column("turnover_mn", sa.Float(), nullable=True),
        sa.Column("session_vwap", sa.Float(), nullable=True),
        sa.Column("is_delayed", sa.Boolean(), nullable=False),
        sa.Column("sequence_status", sa.String(length=16), nullable=False),
        sa.Column("time_quality", sa.String(length=32), nullable=False),
        sa.Column("source", sa.String(length=48), nullable=False),
        sa.Column(
            "ingested_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("ltp > 0", name="ck_intraday_quote_observations_ltp"),
        sa.CheckConstraint("high > 0 AND low > 0", name="ck_intraday_quote_observations_range"),
        sa.CheckConstraint("high >= low", name="ck_intraday_quote_observations_range_order"),
        sa.CheckConstraint(
            "volume >= 0 AND trades >= 0", name="ck_intraday_quote_observations_counts"
        ),
        sa.CheckConstraint(
            "sequence_status IN ('baseline', 'advanced', 'unchanged', 'regressed')",
            name="ck_intraday_quote_observations_sequence",
        ),
        sa.CheckConstraint(
            "time_quality IN ('source_timestamp', 'ingestion_upper_bound')",
            name="ck_intraday_quote_observations_time_quality",
        ),
        sa.ForeignKeyConstraint(
            ["source_snapshot_id"], ["data_source_snapshots.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint(
            "market", "code", "session_date", "observed_at", name="pk_intraday_quote_observations"
        ),
        postgresql_partition_by="RANGE (session_date)",
    )
    op.execute(
        "CREATE TABLE intraday_quote_observations_2026 "
        "PARTITION OF intraday_quote_observations "
        "FOR VALUES FROM ('2026-01-01') TO ('2027-01-01')"
    )
    op.execute(
        "CREATE TABLE intraday_quote_observations_default "
        "PARTITION OF intraday_quote_observations DEFAULT"
    )
    op.create_index(
        "ix_intraday_quote_observations_symbol_time",
        "intraday_quote_observations",
        ["market", "code", "observed_at"],
    )

    op.create_table(
        "intraday_bars",
        sa.Column("market", sa.String(length=8), nullable=False),
        sa.Column("code", sa.String(length=16), nullable=False),
        sa.Column("session_date", sa.Date(), nullable=False),
        sa.Column("interval_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("interval_minutes", sa.Integer(), server_default="15", nullable=False),
        sa.Column("open", sa.Float(), nullable=False),
        sa.Column("high", sa.Float(), nullable=False),
        sa.Column("low", sa.Float(), nullable=False),
        sa.Column("close", sa.Float(), nullable=False),
        sa.Column("volume_delta", sa.BigInteger(), nullable=True),
        sa.Column("trades_delta", sa.Integer(), nullable=True),
        sa.Column("turnover_delta_mn", sa.Float(), nullable=True),
        sa.Column("interval_vwap", sa.Float(), nullable=True),
        sa.Column("cumulative_volume", sa.BigInteger(), nullable=False),
        sa.Column("cumulative_trades", sa.Integer(), nullable=False),
        sa.Column("cumulative_turnover_mn", sa.Float(), nullable=True),
        sa.Column("session_vwap", sa.Float(), nullable=True),
        sa.Column("observation_count", sa.Integer(), nullable=False),
        sa.Column("data_quality", sa.String(length=24), nullable=False),
        sa.Column("time_quality", sa.String(length=32), nullable=False),
        sa.Column("source", sa.String(length=48), nullable=False),
        sa.Column("last_source_snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("known_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "open > 0 AND high > 0 AND low > 0 AND close > 0", name="ck_intraday_bars_ohlc"
        ),
        sa.CheckConstraint("high >= open AND high >= close", name="ck_intraday_bars_high"),
        sa.CheckConstraint("low <= open AND low <= close", name="ck_intraday_bars_low"),
        sa.CheckConstraint("interval_minutes > 0", name="ck_intraday_bars_interval"),
        sa.CheckConstraint("observation_count > 0", name="ck_intraday_bars_observations"),
        sa.CheckConstraint(
            "volume_delta IS NULL OR volume_delta >= 0", name="ck_intraday_bars_volume_delta"
        ),
        sa.CheckConstraint(
            "trades_delta IS NULL OR trades_delta >= 0", name="ck_intraday_bars_trades_delta"
        ),
        sa.CheckConstraint(
            "turnover_delta_mn IS NULL OR turnover_delta_mn >= 0",
            name="ck_intraday_bars_turnover_delta",
        ),
        sa.CheckConstraint(
            "data_quality IN ('baseline', 'complete_delta', 'missing_turnover', 'counter_regression')",
            name="ck_intraday_bars_quality",
        ),
        sa.CheckConstraint(
            "time_quality IN ('source_timestamp', 'ingestion_upper_bound')",
            name="ck_intraday_bars_time_quality",
        ),
        sa.ForeignKeyConstraint(
            ["last_source_snapshot_id"], ["data_source_snapshots.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint(
            "market", "code", "session_date", "interval_start", name="pk_intraday_bars"
        ),
        postgresql_partition_by="RANGE (session_date)",
    )
    op.execute(
        "CREATE TABLE intraday_bars_2026 PARTITION OF intraday_bars "
        "FOR VALUES FROM ('2026-01-01') TO ('2027-01-01')"
    )
    op.execute("CREATE TABLE intraday_bars_default PARTITION OF intraday_bars DEFAULT")
    op.create_index(
        "ix_intraday_bars_symbol_time",
        "intraday_bars",
        ["market", "code", "interval_start"],
    )

    op.create_table(
        "intraday_capture_sessions",
        sa.Column("market", sa.String(length=8), nullable=False),
        sa.Column("session_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("expected_slot_count", sa.Integer(), nullable=False),
        sa.Column("observed_slot_count", sa.Integer(), nullable=False),
        sa.Column("expected_symbol_count", sa.Integer(), nullable=False),
        sa.Column("observed_symbol_count", sa.Integer(), nullable=False),
        sa.Column("observation_count", sa.BigInteger(), nullable=False),
        sa.Column("bar_count", sa.BigInteger(), nullable=False),
        sa.Column("vwap_bar_count", sa.BigInteger(), nullable=False),
        sa.Column("counter_regression_count", sa.BigInteger(), nullable=False),
        sa.Column("slot_completeness_pct", sa.Float(), nullable=False),
        sa.Column("symbol_completeness_pct", sa.Float(), nullable=False),
        sa.Column("vwap_coverage_pct", sa.Float(), nullable=False),
        sa.Column("first_observed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("latest_observed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("maximum_capture_lag_seconds", sa.Float(), nullable=False),
        sa.Column("research_eligible", sa.Boolean(), server_default="false", nullable=False),
        sa.Column(
            "blockers",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "metrics",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('collecting', 'complete', 'incomplete')",
            name="ck_intraday_capture_sessions_status",
        ),
        sa.CheckConstraint(
            "expected_slot_count > 0 AND observed_slot_count >= 0",
            name="ck_intraday_capture_sessions_slots",
        ),
        sa.CheckConstraint(
            "expected_symbol_count >= 0 AND observed_symbol_count >= 0",
            name="ck_intraday_capture_sessions_symbols",
        ),
        sa.CheckConstraint(
            "slot_completeness_pct >= 0 AND slot_completeness_pct <= 100",
            name="ck_intraday_capture_sessions_slot_pct",
        ),
        sa.CheckConstraint(
            "symbol_completeness_pct >= 0 AND symbol_completeness_pct <= 100",
            name="ck_intraday_capture_sessions_symbol_pct",
        ),
        sa.CheckConstraint(
            "vwap_coverage_pct >= 0 AND vwap_coverage_pct <= 100",
            name="ck_intraday_capture_sessions_vwap_pct",
        ),
        sa.PrimaryKeyConstraint("market", "session_date", name="pk_intraday_capture_sessions"),
    )
    op.create_index(
        "ix_intraday_capture_sessions_market_status",
        "intraday_capture_sessions",
        ["market", "status", "session_date"],
    )
    op.execute(
        sa.text(
            "CREATE FUNCTION reject_intraday_quote_observation_mutation() RETURNS trigger "
            "LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION "
            "'intraday_quote_observations are append-only'; END; $$"
        )
    )
    op.execute(
        sa.text(
            "CREATE TRIGGER intraday_quote_observations_append_only "
            "BEFORE UPDATE OR DELETE ON intraday_quote_observations "
            "FOR EACH ROW EXECUTE FUNCTION reject_intraday_quote_observation_mutation()"
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "DROP TRIGGER IF EXISTS intraday_quote_observations_append_only "
            "ON intraday_quote_observations"
        )
    )
    op.execute(sa.text("DROP FUNCTION IF EXISTS reject_intraday_quote_observation_mutation()"))
    op.drop_table("intraday_capture_sessions")
    op.drop_table("intraday_bars_default")
    op.drop_table("intraday_bars_2026")
    op.drop_table("intraday_bars")
    op.drop_table("intraday_quote_observations_default")
    op.drop_table("intraday_quote_observations_2026")
    op.drop_table("intraday_quote_observations")
