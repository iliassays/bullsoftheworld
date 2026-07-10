"""tenant-scope account identifiers and version reset tokens

Revision ID: e3f4a5b6c7d8
Revises: d2e3f4a5b6c7
"""

import sqlalchemy as sa
from alembic import op

revision = "e3f4a5b6c7d8"
down_revision = "d2e3f4a5b6c7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("ix_users_handle", table_name="users")
    op.drop_constraint("uq_users_email", "users", type_="unique")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_index("ix_users_phone", table_name="users")

    op.create_unique_constraint(
        "uq_users_tenant_handle", "users", ["tenant_id", "handle"]
    )
    op.create_unique_constraint(
        "uq_users_tenant_email", "users", ["tenant_id", "email"]
    )
    op.create_unique_constraint(
        "uq_users_tenant_phone", "users", ["tenant_id", "phone"]
    )
    op.add_column(
        "users",
        sa.Column("auth_version", sa.Integer(), server_default="0", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("users", "auth_version")
    op.drop_constraint("uq_users_tenant_phone", "users", type_="unique")
    op.drop_constraint("uq_users_tenant_email", "users", type_="unique")
    op.drop_constraint("uq_users_tenant_handle", "users", type_="unique")

    op.create_index("ix_users_phone", "users", ["phone"], unique=True)
    op.create_index("ix_users_email", "users", ["email"], unique=False)
    op.create_unique_constraint("uq_users_email", "users", ["email"])
    op.create_index("ix_users_handle", "users", ["handle"], unique=True)
