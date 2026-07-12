"""Enforce valid shareholding compositions.

Revision ID: 8b9c0d1e2f3a
Revises: 7a8b9c0d1e2f
"""

from alembic import op

revision = "8b9c0d1e2f3a"
down_revision = "7a8b9c0d1e2f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Historical all-zero rows are known parser failures, not genuine disclosures. Remove every
    # impossible composition before installing the invariant so stale bad data cannot reach users.
    op.execute(
        """
        delete from shareholding_snapshots
        where sponsor_director is null
           or institute is null
           or foreign_pct is null
           or public is null
           or sponsor_director not between 0 and 100
           or coalesce(govt, 0) not between 0 and 100
           or institute not between 0 and 100
           or foreign_pct not between 0 and 100
           or public not between 0 and 100
           or sponsor_director + coalesce(govt, 0) + institute + foreign_pct + public
              not between 99 and 101
        """
    )
    op.create_check_constraint(
        "ck_shareholding_category_percentages",
        "shareholding_snapshots",
        "sponsor_director is not null and institute is not null and "
        "foreign_pct is not null and public is not null and "
        "sponsor_director between 0 and 100 and "
        "coalesce(govt, 0) between 0 and 100 and "
        "institute between 0 and 100 and foreign_pct between 0 and 100 and "
        "public between 0 and 100",
    )
    op.create_check_constraint(
        "ck_shareholding_composition_total",
        "shareholding_snapshots",
        "sponsor_director + coalesce(govt, 0) + institute + foreign_pct + public "
        "between 99 and 101",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_shareholding_composition_total",
        "shareholding_snapshots",
        type_="check",
    )
    op.drop_constraint(
        "ck_shareholding_category_percentages",
        "shareholding_snapshots",
        type_="check",
    )
