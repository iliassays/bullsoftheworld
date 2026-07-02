"""quiz_questions + quiz_answers, seeded with the starter bilingual question bank

Revision ID: b9c0d1e2f3a4
Revises: a8b9c0d1e2f3
"""

import sqlalchemy as sa
from alembic import op

revision = "b9c0d1e2f3a4"
down_revision = "a8b9c0d1e2f3"
branch_labels = None
depends_on = None


def _q(topic: str, en_q: str, bn_q: str, en_c: list, bn_c: list, ans: int, en_e: str, bn_e: str):
    # Values stay Python dicts — the sa.JSON columns in bulk_insert serialize them once.
    return {
        "topic": topic,
        "question_i18n": {"en": en_q, "bn": bn_q},
        "choices_i18n": {"en": en_c, "bn": bn_c},
        "answer_idx": ans,
        "explanation_i18n": {"en": en_e, "bn": bn_e},
        "is_active": True,
    }


# Starter bank: market literacy for the Dhaka retail reader. Descriptive education only —
# no question or explanation ever implies a buy/sell action.
SEED = [
    _q(
        "valuation",
        "A stock trades at a P/E of 18. What does that mean?",
        "একটি শেয়ারের P/E ১৮। এর মানে কী?",
        [
            "The share price is ৳18",
            "The share trades at 18 times its yearly earnings per share",
            "The company's profit grew 18%",
        ],
        [
            "শেয়ারের দাম ১৮ টাকা",
            "বার্ষিক শেয়ারপ্রতি আয়ের ১৮ গুণ দামে শেয়ারটি কেনাবেচা হচ্ছে",
            "কোম্পানির লাভ ১৮% বেড়েছে",
        ],
        1,
        "P/E = price ÷ earnings per share. Lower isn't automatically better — compare with the sector median.",
        "P/E = দাম ÷ শেয়ারপ্রতি আয়। কম মানেই ভালো নয় — সেক্টরের মিডিয়ানের সাথে তুলনা করুন।",
    ),
    _q(
        "market_basics",
        "What does a circuit breaker on DSE do?",
        "DSE-তে সার্কিট ব্রেকার কী করে?",
        [
            "Halts the whole exchange for the day",
            "Caps how far a stock's price can move in one day",
            "Blocks foreign investors from trading",
        ],
        [
            "পুরো এক্সচেঞ্জ সারাদিন বন্ধ করে",
            "একদিনে একটি শেয়ারের দাম কতদূর যেতে পারে তা সীমিত করে",
            "বিদেশিদের লেনদেন আটকে দেয়",
        ],
        1,
        "Each stock has a daily price band. Hitting the limit halts moves beyond it — that's why some stocks close pinned at the cap.",
        "প্রতিটি শেয়ারের দৈনিক প্রাইস ব্যান্ড আছে। সীমায় পৌঁছালে এর বাইরে দাম যায় না — তাই কিছু শেয়ার ক্যাপে আটকে বন্ধ হয়।",
    ),
    _q(
        "market_basics",
        "A stock makes a new 52-week high. What is that, on its own?",
        "একটি শেয়ার নতুন ৫২-সপ্তাহের সর্বোচ্চে। এটি নিজে নিজে কী?",
        [
            "A buy signal",
            "A milestone: the highest price in a year",
            "Proof the company is profitable",
        ],
        ["কেনার সংকেত", "একটি মাইলফলক: এক বছরের সর্বোচ্চ দাম", "কোম্পানি লাভজনক হওয়ার প্রমাণ"],
        1,
        "It's a fact about price history, not a recommendation. Traders watch whether the level holds — you should read why it moved.",
        "এটি দামের ইতিহাসের একটি তথ্য, কোনো পরামর্শ নয়। লেভেলটি টেকে কিনা তা দেখা হয় — কেন বাড়ল সেটাই পড়ে দেখুন।",
    ),
    _q(
        "valuation",
        "Dividend yield 8% on a stock. What should you check before celebrating?",
        "একটি শেয়ারে ডিভিডেন্ড ইল্ড ৮%। খুশি হওয়ার আগে কী দেখবেন?",
        [
            "Whether earnings actually cover that dividend",
            "Nothing — 8% is always good",
            "The color of the company logo",
        ],
        ["আয় দিয়ে আসলেই ডিভিডেন্ড কভার হয় কিনা", "কিছুই না — ৮% সবসময় ভালো", "কোম্পানির লোগোর রঙ"],
        0,
        "A high yield can mean a falling price or an unsustainable payout. Check EPS vs dividend per share.",
        "উঁচু ইল্ড মানে হতে পারে দাম পড়ছে বা পেআউট টেকসই নয়। EPS বনাম শেয়ারপ্রতি ডিভিডেন্ড দেখুন।",
    ),
    _q(
        "risk",
        "Why does thin liquidity (low daily turnover) matter for a small investor?",
        "কম লিকুইডিটি (কম দৈনিক লেনদেন) ছোট বিনিয়োগকারীর জন্য কেন গুরুত্বপূর্ণ?",
        [
            "It means the stock is cheap",
            "Selling later may move the price against you or take days",
            "It guarantees higher returns",
        ],
        [
            "মানে শেয়ারটি সস্তা",
            "পরে বিক্রি করতে গেলে দাম আপনার বিপক্ষে যেতে পারে বা দিন লেগে যেতে পারে",
            "বেশি রিটার্নের নিশ্চয়তা",
        ],
        1,
        "Thin stocks are easy to buy into and hard to get out of — and they're the favourite playground for manipulation.",
        "কম লেনদেনের শেয়ারে ঢোকা সহজ, বের হওয়া কঠিন — আর ম্যানিপুলেশনের প্রিয় জায়গাও এগুলোই।",
    ),
    _q(
        "ownership",
        "Sponsor/director holding in a company keeps falling for months. What is that?",
        "কোনো কোম্পানিতে স্পনসর/পরিচালকদের অংশ মাসের পর মাস কমছে। এটি কী?",
        [
            "A disclosed fact worth reading into — insiders are reducing",
            "Always a reason to sell immediately",
            "Meaningless noise",
        ],
        [
            "একটি প্রকাশিত তথ্য যা পড়ে দেখা উচিত — অভ্যন্তরীণরা কমাচ্ছেন",
            "সবসময় সাথে সাথে বিক্রির কারণ",
            "অর্থহীন শব্দ",
        ],
        0,
        "Ownership changes are public disclosures. Insiders selling steadily is one input to research — not an instruction.",
        "মালিকানার পরিবর্তন প্রকাশ্য ডিসক্লোজার। অভ্যন্তরীণদের ধারাবাহিক বিক্রি গবেষণার একটি সূত্র — কোনো নির্দেশ নয়।",
    ),
    _q(
        "market_basics",
        "What does 'free float' mean?",
        "'ফ্রি ফ্লোট' মানে কী?",
        [
            "Shares available for public trading (not locked with sponsors/govt)",
            "Shares given away for free",
            "The company's cash reserve",
        ],
        [
            "পাবলিক লেনদেনের জন্য উন্মুক্ত শেয়ার (স্পনসর/সরকারের হাতে আটকে নেই)",
            "বিনামূল্যে দেওয়া শেয়ার",
            "কোম্পানির নগদ রিজার্ভ",
        ],
        0,
        "Small free float + excitement = wild price swings. It's why some small stocks hit circuits so easily.",
        "ছোট ফ্রি ফ্লোট + উত্তেজনা = বন্য দামের ওঠানামা। এ কারণেই কিছু ছোট শেয়ার সহজে সার্কিটে পৌঁছে যায়।",
    ),
    _q(
        "risk",
        "A Facebook group promises a stock will double next week. What does BSEC say about tips like this?",
        "একটি ফেসবুক গ্রুপ বলছে আগামী সপ্তাহে শেয়ারটির দাম দ্বিগুণ হবে। এমন টিপ নিয়ে BSEC কী বলে?",
        [
            "Trust groups with many members",
            "Don't invest based on unverified social-media information",
            "Only trust tips posted on Fridays",
        ],
        [
            "বেশি সদস্যের গ্রুপ বিশ্বাস করুন",
            "যাচাই না করা সোশ্যাল মিডিয়ার তথ্যে বিনিয়োগ করবেন না",
            "শুধু শুক্রবারের টিপ বিশ্বাস করুন",
        ],
        1,
        "The regulator itself warns against acting on unverified tips. Check disclosures and data — that's exactly what this app is for.",
        "নিয়ন্ত্রক সংস্থা নিজেই যাচাইহীন টিপে কাজ করতে নিষেধ করে। ডিসক্লোজার ও ডেটা দেখুন — এই অ্যাপ ঠিক সেজন্যই।",
    ),
    _q(
        "valuation",
        "EPS is ৳5 and the share price is ৳100. What's the P/E?",
        "EPS ৳৫ এবং শেয়ারের দাম ৳১০০। P/E কত?",
        ["5", "20", "500"],
        ["৫", "২০", "৫০০"],
        1,
        "P/E = 100 ÷ 5 = 20. You're paying ৳20 for every ৳1 of yearly earnings.",
        "P/E = ১০০ ÷ ৫ = ২০। প্রতি ৳১ বার্ষিক আয়ের জন্য আপনি ৳২০ দিচ্ছেন।",
    ),
    _q(
        "market_basics",
        "Category Z on DSE usually signals what?",
        "DSE-তে জেড ক্যাটাগরি সাধারণত কী বোঝায়?",
        [
            "The market's best performers",
            "Companies failing on dividends/AGMs or operations — extra caution",
            "Newly listed companies",
        ],
        [
            "বাজারের সেরা পারফরমার",
            "ডিভিডেন্ড/এজিএম বা কার্যক্রমে ব্যর্থ কোম্পানি — বাড়তি সতর্কতা",
            "নতুন তালিকাভুক্ত কোম্পানি",
        ],
        1,
        "Z-category companies missed dividends or AGMs, or halted operations. Their rallies are where pump-and-dumps live.",
        "জেড ক্যাটাগরির কোম্পানি ডিভিডেন্ড বা এজিএম দেয়নি, বা কার্যক্রম বন্ধ। এদের র‍্যালিতেই পাম্প-অ্যান্ড-ডাম্প বাসা বাঁধে।",
    ),
]


def upgrade() -> None:
    op.create_table(
        "quiz_questions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("topic", sa.String(length=32), nullable=False),
        sa.Column("question_i18n", sa.JSON(), nullable=False),
        sa.Column("choices_i18n", sa.JSON(), nullable=False),
        sa.Column("answer_idx", sa.Integer(), nullable=False),
        sa.Column("explanation_i18n", sa.JSON(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "quiz_answers",
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("answered_on", sa.Date(), nullable=False),
        sa.Column("question_id", sa.Integer(), sa.ForeignKey("quiz_questions.id"), nullable=False),
        sa.Column("choice_idx", sa.Integer(), nullable=False),
        sa.Column("correct", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("user_id", "answered_on"),
    )
    qt = sa.table(
        "quiz_questions",
        sa.column("topic", sa.String),
        sa.column("question_i18n", sa.JSON),
        sa.column("choices_i18n", sa.JSON),
        sa.column("answer_idx", sa.Integer),
        sa.column("explanation_i18n", sa.JSON),
        sa.column("is_active", sa.Boolean),
    )
    op.bulk_insert(qt, SEED)


def downgrade() -> None:
    op.drop_table("quiz_answers")
    op.drop_table("quiz_questions")
