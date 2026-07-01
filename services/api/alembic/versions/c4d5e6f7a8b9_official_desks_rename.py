"""users.is_official + rename agent handles to @BullsOfDhaka<Topic>

Revision ID: c4d5e6f7a8b9
Revises: b3c4d5e6f7a8
"""

import sqlalchemy as sa
from alembic import op

revision = "c4d5e6f7a8b9"
down_revision = "b3c4d5e6f7a8"
branch_labels = None
depends_on = None

# old handle -> new (StockTwits-convention) handle.
_RENAMES = {
    "bullsofdhaka-levels-agent": "BullsOfDhakaLevels",
    "bullsofdhaka-volume-agent": "BullsOfDhakaVolume",
    "bullsofdhaka-foreign-agent": "BullsOfDhakaForeign",
    "bullsofdhaka-institution-agent": "BullsOfDhakaInstitution",
    "bullsofdhaka-sponsor-agent": "BullsOfDhakaSponsor",
    "bullsofdhaka-dividend-agent": "BullsOfDhakaDividend",
    "bullsofdhaka-earnings-agent": "BullsOfDhakaEarnings",
    "bullsofdhaka-rating-agent": "BullsOfDhakaRating",
    "bullsofdhaka-market-update-agent": "BullsOfDhakaMarket",
    "bullsofdhaka-momentum-agent": "BullsOfDhakaMomentum",
    "bullsofdhaka-strength-agent": "BullsOfDhakaStrength",
    "bullsofdhaka-quality-agent": "BullsOfDhakaQuality",
    "bullsofdhaka-smartmoney-agent": "BullsOfDhakaSmartMoney",
    "bullsofdhaka-accumulation-agent": "BullsOfDhakaAccumulation",
    "bullsofdhaka-circuit-agent": "BullsOfDhakaCircuit",
    "bullsofdhaka-breakout-agent": "BullsOfDhakaBreakout",
}


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("is_official", sa.Boolean(), nullable=False, server_default="false"),
    )
    conn = op.get_bind()
    for old, new in _RENAMES.items():
        conn.execute(
            sa.text("UPDATE users SET handle = :new, is_official = true WHERE handle = :old"),
            {"new": new, "old": old},
        )


def downgrade() -> None:
    conn = op.get_bind()
    for old, new in _RENAMES.items():
        conn.execute(
            sa.text("UPDATE users SET handle = :old WHERE handle = :new"),
            {"old": old, "new": new},
        )
    op.drop_column("users", "is_official")
