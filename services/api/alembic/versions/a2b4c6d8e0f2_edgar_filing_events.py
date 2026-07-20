"""Append-only EDGAR filing-event stream: capture log, insider transactions, 13D/G events.

Revision ID: a2b4c6d8e0f2
Revises: f1e3a5c7d9b0
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "a2b4c6d8e0f2"
down_revision = "f1e3a5c7d9b0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "edgar_filing_events",
        sa.Column("accession_number", sa.String(25), primary_key=True),
        sa.Column("market", sa.String(8), nullable=False, server_default="US"),
        sa.Column("form", sa.String(16), nullable=False),
        sa.Column("cik", sa.BigInteger(), nullable=False),
        sa.Column("company_name", sa.Text(), nullable=True),
        sa.Column("filed_date", sa.Date(), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "captured_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("index_filename", sa.Text(), nullable=False),
        sa.Column("raw_object_key", sa.Text(), nullable=True),
        sa.Column("raw_sha256", sa.String(64), nullable=True),
        sa.Column("parse_status", sa.String(16), nullable=False, server_default="pending"),
        sa.CheckConstraint(
            "parse_status IN ('pending', 'parsed', 'failed', 'skipped')",
            name="ck_edgar_filing_events_parse_status",
        ),
        sa.CheckConstraint(
            "raw_sha256 IS NULL OR raw_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_edgar_filing_events_raw_hash",
        ),
    )
    op.create_index("ix_edgar_filing_events_form", "edgar_filing_events", ["form"])
    op.create_index("ix_edgar_filing_events_cik", "edgar_filing_events", ["cik"])
    op.create_index("ix_edgar_filing_events_filed_date", "edgar_filing_events", ["filed_date"])
    op.create_index(
        "ix_edgar_filing_events_form_date", "edgar_filing_events", ["form", "filed_date"]
    )
    op.create_index(
        "ix_edgar_filing_events_cik_date", "edgar_filing_events", ["cik", "filed_date"]
    )

    op.create_table(
        "insider_transactions",
        sa.Column(
            "id",
            sa.Uuid(),
            primary_key=True,
            server_default=sa.func.gen_random_uuid(),
        ),
        sa.Column("accession_number", sa.String(25), nullable=False),
        sa.Column("row_index", sa.Integer(), nullable=False),
        sa.Column("issuer_cik", sa.BigInteger(), nullable=False),
        sa.Column("issuer_symbol", sa.String(16), nullable=True),
        sa.Column("issuer_name", sa.Text(), nullable=True),
        sa.Column("owner_cik", sa.BigInteger(), nullable=False),
        sa.Column("owner_name", sa.Text(), nullable=True),
        sa.Column("is_director", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_officer", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "is_ten_percent_owner", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("officer_title", sa.Text(), nullable=True),
        sa.Column("is_10b5_1_plan", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("security_title", sa.Text(), nullable=True),
        sa.Column("transaction_date", sa.Date(), nullable=True),
        sa.Column("code", sa.String(4), nullable=True),
        sa.Column("shares", sa.Float(), nullable=True),
        sa.Column("price_per_share", sa.Float(), nullable=True),
        sa.Column("acquired_disposed", sa.String(1), nullable=True),
        sa.Column("shares_owned_after", sa.Float(), nullable=True),
        sa.Column("direct_or_indirect", sa.String(1), nullable=True),
        sa.Column(
            "has_derivative_transactions",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "captured_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "accession_number",
            "owner_cik",
            "row_index",
            name="uq_insider_transactions_row",
        ),
    )
    op.create_index(
        "ix_insider_transactions_accession", "insider_transactions", ["accession_number"]
    )
    op.create_index("ix_insider_transactions_issuer", "insider_transactions", ["issuer_cik"])
    op.create_index("ix_insider_transactions_symbol", "insider_transactions", ["issuer_symbol"])
    op.create_index("ix_insider_transactions_owner", "insider_transactions", ["owner_cik"])
    op.create_index(
        "ix_insider_transactions_issuer_date",
        "insider_transactions",
        ["issuer_cik", "transaction_date"],
    )
    op.create_index(
        "ix_insider_transactions_code_date",
        "insider_transactions",
        ["code", "transaction_date"],
    )

    op.create_table(
        "ownership_stake_events",
        sa.Column("accession_number", sa.String(25), primary_key=True),
        sa.Column("form", sa.String(16), nullable=False),
        sa.Column("subject_cik", sa.BigInteger(), nullable=False),
        sa.Column("subject_name", sa.Text(), nullable=False),
        sa.Column("filed_by_cik", sa.BigInteger(), nullable=True),
        sa.Column("filed_by_name", sa.Text(), nullable=True),
        sa.Column("filed_date", sa.Date(), nullable=True),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("percent_of_class", sa.Float(), nullable=True),
        sa.Column(
            "captured_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_ownership_stake_events_form", "ownership_stake_events", ["form"])
    op.create_index(
        "ix_ownership_stake_events_subject", "ownership_stake_events", ["subject_cik"]
    )
    op.create_index(
        "ix_ownership_stake_events_filer", "ownership_stake_events", ["filed_by_cik"]
    )
    op.create_index(
        "ix_ownership_stake_events_filed_date", "ownership_stake_events", ["filed_date"]
    )
    op.create_index(
        "ix_ownership_stake_events_subject_date",
        "ownership_stake_events",
        ["subject_cik", "filed_date"],
    )
    op.create_index(
        "ix_ownership_stake_events_filer_date",
        "ownership_stake_events",
        ["filed_by_cik", "filed_date"],
    )


def downgrade() -> None:
    op.drop_table("ownership_stake_events")
    op.drop_table("insider_transactions")
    op.drop_table("edgar_filing_events")
