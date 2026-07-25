"""Repair impossible insider transaction dates and floor the column

Production held 32 ``insider_transactions`` rows whose ``transaction_date`` came from a filer
typo that is nonetheless valid ISO-8601 — years ranging from 0022 to 2033. They are nulled, not
corrected: the digits the filer intended are a guess, while the rest of the row (owner, code,
shares, price) is filed fact worth keeping. Re-parsing the archived dissemination bytes in the
object store is the only way to recover a true date, and that is a backfill, not a migration.

The floor is enforced as a CHECK. The ceiling ("not after the filing that reports it") cannot
be: it needs the joined filing date, and a CURRENT_DATE expression is not immutable enough for a
constraint. ``ingestion.edgar_events.parse_filing`` enforces the ceiling on write.

Revision ID: a3d9f1c5e7b2
Revises: f2c8e3a5b7d1
"""

from __future__ import annotations

from alembic import op

revision = "a3d9f1c5e7b2"
down_revision = "f2c8e3a5b7d1"
branch_labels = None
depends_on = None

_FLOOR = "DATE '1990-01-01'"


def upgrade() -> None:
    # Mistyped year digits (0022-10-12 for 2022-10-12 and friends).
    op.execute(
        f"UPDATE insider_transactions SET transaction_date = NULL WHERE transaction_date < {_FLOOR}"
    )

    # Dates after the filing that reports them. Section 16 allows two business days, so a
    # transaction cannot postdate its own filing; one day of tolerance absorbs timezone skew.
    op.execute(
        """
        UPDATE insider_transactions AS t
           SET transaction_date = NULL
          FROM edgar_filing_events AS e
         WHERE e.accession_number = t.accession_number
           AND t.transaction_date IS NOT NULL
           AND t.transaction_date > e.filed_date + INTERVAL '1 day'
        """
    )

    # Backstop for rows whose capture-log row is missing: a future date is impossible regardless
    # of which filing reported it.
    op.execute(
        "UPDATE insider_transactions SET transaction_date = NULL "
        "WHERE transaction_date > CURRENT_DATE + INTERVAL '1 day'"
    )

    op.create_check_constraint(
        "ck_insider_transactions_transaction_date_floor",
        "insider_transactions",
        f"transaction_date IS NULL OR transaction_date >= {_FLOOR}",
    )


def downgrade() -> None:
    # The nulled dates are not restorable — they were never recorded anywhere else.
    op.drop_constraint(
        "ck_insider_transactions_transaction_date_floor",
        "insider_transactions",
        type_="check",
    )
