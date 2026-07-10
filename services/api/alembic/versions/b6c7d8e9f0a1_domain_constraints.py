"""enforce account, social and alert domain values

Revision ID: b6c7d8e9f0a1
Revises: a5b6c7d8e9f0
"""

from alembic import op

revision = "b6c7d8e9f0a1"
down_revision = "a5b6c7d8e9f0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_check_constraint("ck_users_role", "users", "role IN ('user', 'admin')")
    op.create_check_constraint("ck_users_locale", "users", "locale IN ('en', 'bn')")
    op.create_check_constraint("ck_users_auth_version", "users", "auth_version >= 0")
    op.create_check_constraint(
        "ck_posts_sentiment", "posts", "sentiment IS NULL OR sentiment IN ('bull', 'bear')"
    )
    op.create_check_constraint("ck_posts_kind", "posts", "kind IN ('user', 'note')")
    op.create_check_constraint(
        "ck_posts_moderation_status",
        "posts",
        "moderation_status IN ('published', 'pending', 'held', 'blocked', 'deleted')",
    )
    op.create_check_constraint(
        "ck_post_reactions_kind", "post_reactions", "kind IN ('agree', 'disagree')"
    )
    op.create_check_constraint(
        "ck_price_alerts_direction", "price_alerts", "direction IN ('above', 'below')"
    )
    op.create_check_constraint(
        "ck_price_alerts_level_positive", "price_alerts", "level > 0"
    )


def downgrade() -> None:
    op.drop_constraint("ck_price_alerts_level_positive", "price_alerts", type_="check")
    op.drop_constraint("ck_price_alerts_direction", "price_alerts", type_="check")
    op.drop_constraint("ck_post_reactions_kind", "post_reactions", type_="check")
    op.drop_constraint("ck_posts_moderation_status", "posts", type_="check")
    op.drop_constraint("ck_posts_kind", "posts", type_="check")
    op.drop_constraint("ck_posts_sentiment", "posts", type_="check")
    op.drop_constraint("ck_users_auth_version", "users", type_="check")
    op.drop_constraint("ck_users_locale", "users", type_="check")
    op.drop_constraint("ck_users_role", "users", type_="check")
