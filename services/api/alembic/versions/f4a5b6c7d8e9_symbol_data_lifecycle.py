"""separate security-master eligibility from retail data readiness

Revision ID: f4a5b6c7d8e9
Revises: e3f4a5b6c7d8
"""

import sqlalchemy as sa
from alembic import op

revision = "f4a5b6c7d8e9"
down_revision = "e3f4a5b6c7d8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "symbols",
        sa.Column("data_status", sa.String(length=20), server_default="ready", nullable=False),
    )
    op.add_column("symbols", sa.Column("data_first_date", sa.Date(), nullable=True))
    op.add_column("symbols", sa.Column("data_last_date", sa.Date(), nullable=True))
    op.create_index("ix_symbols_data_status", "symbols", ["data_status"])
    op.create_check_constraint(
        "ck_symbols_data_status",
        "symbols",
        "data_status IN ('reference_only', 'onboarding', 'ready', 'degraded')",
    )

    op.execute(
        "UPDATE symbols SET data_first_date = bars.first_date, data_last_date = bars.last_date "
        "FROM (SELECT market, code, min(date) AS first_date, max(date) AS last_date "
        "FROM daily_bars GROUP BY market, code) AS bars "
        "WHERE symbols.market = bars.market AND symbols.code = bars.code"
    )
    op.execute(
        "UPDATE symbols SET data_status = 'reference_only' "
        "WHERE market = 'US' AND NOT EXISTS ("
        "SELECT 1 FROM daily_bars WHERE daily_bars.market = symbols.market "
        "AND daily_bars.code = symbols.code GROUP BY daily_bars.market, daily_bars.code "
        "HAVING count(*) >= 252)"
    )


def downgrade() -> None:
    op.drop_constraint("ck_symbols_data_status", "symbols", type_="check")
    op.drop_index("ix_symbols_data_status", table_name="symbols")
    op.drop_column("symbols", "data_last_date")
    op.drop_column("symbols", "data_first_date")
    op.drop_column("symbols", "data_status")
