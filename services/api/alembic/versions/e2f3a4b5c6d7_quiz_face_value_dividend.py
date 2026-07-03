"""quiz: the face-value dividend convention — the most misread number on the DSE

A "10% cash dividend" is 10% of the ৳10 face value (= ৳1/share), not 10% of the market
price. Same lesson now taught by the dividend news explainer and the yield tooltip;
this makes it a quiz day too.

Revision ID: e2f3a4b5c6d7
Revises: d1e2f3a4b5c6
"""

import sqlalchemy as sa
from alembic import op

revision = "e2f3a4b5c6d7"
down_revision = "d1e2f3a4b5c6"
branch_labels = None
depends_on = None

_EN_Q = 'A DSE company declares a "10% cash dividend". How much cash is that per share?'

QUESTION = {
    "topic": "valuation",
    "question_i18n": {
        "en": _EN_Q,
        "bn": 'DSE-র একটি কোম্পানি "১০% নগদ লভ্যাংশ" ঘোষণা করল। শেয়ারপ্রতি কত টাকা নগদ পাবেন?',
    },
    "choices_i18n": {
        "en": [
            "10% of today's market price",
            "৳1 per share — 10% of the ৳10 face value",
            "10 bonus shares for every 100 held",
        ],
        "bn": [
            "আজকের বাজারদরের ১০%",
            "শেয়ারপ্রতি ৳১ — ফেস ভ্যালু ৳১০-এর ১০%",
            "প্রতি ১০০ শেয়ারে ১০টি বোনাস শেয়ার",
        ],
    },
    "answer_idx": 1,
    "explanation_i18n": {
        "en": (
            "DSE dividends are declared as a % of the ৳10 face value, never of the market "
            "price. So '10%' = ৳1 cash; if the share trades at ৳40, your real return (the "
            "yield) is ৳1 ÷ ৳40 ≈ 2.5% — which is why promoters love shouting the big number."
        ),
        "bn": (
            "DSE-তে লভ্যাংশ ঘোষণা হয় ফেস ভ্যালু ৳১০-এর শতাংশে, বাজারদরের নয়। তাই '১০%' = ৳১ নগদ; "
            "শেয়ারের দাম ৳৪০ হলে আপনার আসল রিটার্ন (ইল্ড) = ৳১ ÷ ৳৪০ ≈ ২.৫% — এ কারণেই প্রচারকারীরা "
            "বড় সংখ্যাটাই চেঁচিয়ে বলে।"
        ),
    },
    "is_active": True,
}


def upgrade() -> None:
    qt = sa.table(
        "quiz_questions",
        sa.column("topic", sa.String),
        sa.column("question_i18n", sa.JSON),
        sa.column("choices_i18n", sa.JSON),
        sa.column("answer_idx", sa.Integer),
        sa.column("explanation_i18n", sa.JSON),
        sa.column("is_active", sa.Boolean),
    )
    op.bulk_insert(qt, [QUESTION])


def downgrade() -> None:
    # Answers first (FK), then the question — matched by the English question text.
    op.execute(
        sa.text(
            "DELETE FROM quiz_answers WHERE question_id IN "
            "(SELECT id FROM quiz_questions WHERE question_i18n->>'en' = :q)"
        ).bindparams(q=_EN_Q)
    )
    op.execute(
        sa.text("DELETE FROM quiz_questions WHERE question_i18n->>'en' = :q").bindparams(q=_EN_Q)
    )
