"""Permit one-way release attestation of legacy unknown source manifests.

Revision ID: a4c6e8f0b2d1
Revises: f6d8a0c2e4b7
"""

from __future__ import annotations

from alembic import op
from sqlalchemy import text

revision = "a4c6e8f0b2d1"
down_revision = "f6d8a0c2e4b7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        text(
            "CREATE OR REPLACE FUNCTION reject_data_foundation_artifact_mutation() "
            "RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN "
            "IF TG_TABLE_NAME = 'data_source_snapshots' "
            "AND TG_OP = 'UPDATE' "
            "AND OLD.code_version = 'unknown' "
            "AND NEW.code_version <> 'unknown' "
            "AND NEW.code_version <> '' "
            "AND (to_jsonb(NEW) - 'code_version') "
            "IS NOT DISTINCT FROM (to_jsonb(OLD) - 'code_version') "
            "THEN RETURN NEW; END IF; "
            "RAISE EXCEPTION 'data foundation artifacts are append-only' "
            "USING ERRCODE = '55000'; END; $$"
        )
    )


def downgrade() -> None:
    op.execute(
        text(
            "CREATE OR REPLACE FUNCTION reject_data_foundation_artifact_mutation() "
            "RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN "
            "RAISE EXCEPTION 'data foundation artifacts are append-only' "
            "USING ERRCODE = '55000'; END; $$"
        )
    )
