"""Normalized SEC filings, financial facts, and bounded 13F holdings.

Revision ID: 2b3c4d5e6f7a
Revises: 1a2b3c4d5e6f
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "2b3c4d5e6f7a"
down_revision = "1a2b3c4d5e6f"
branch_labels = None
depends_on = None

US_QUIZ = [
    (
        "filings",
        "What is the main difference between a Form 10-Q and Form 10-K?",
        "Form 10-Q ও Form 10-K-এর প্রধান পার্থক্য কী?",
        [
            "10-Q is quarterly; 10-K is annual and audited",
            "10-Q is always audited",
            "10-K reports daily prices",
        ],
        ["10-Q ত্রৈমাসিক; 10-K বার্ষিক ও নিরীক্ষিত", "10-Q সবসময় নিরীক্ষিত", "10-K দৈনিক দাম জানায়"],
        0,
        "A 10-Q is a quarterly report and is generally unaudited; a 10-K is the audited annual report.",
        "10-Q ত্রৈমাসিক প্রতিবেদন এবং সাধারণত অনিরীক্ষিত; 10-K নিরীক্ষিত বার্ষিক প্রতিবেদন।",
    ),
    (
        "ownership",
        "What can a Form 13F tell you most reliably?",
        "Form 13F সবচেয়ে নির্ভরযোগ্যভাবে কী জানায়?",
        [
            "The manager's exact purchase date",
            "Reported long holdings at quarter-end",
            "All short positions",
        ],
        ["ম্যানেজারের সঠিক কেনার তারিখ", "ত্রৈমাসিক শেষে রিপোর্ট করা লং হোল্ডিং", "সব শর্ট পজিশন"],
        1,
        "13F shows reportable long holdings at quarter-end and can arrive up to 45 days later; it does not reveal exact trade dates.",
        "13F ত্রৈমাসিক শেষে রিপোর্টযোগ্য লং হোল্ডিং দেখায় এবং ৪৫ দিন পরে আসতে পারে; সঠিক ট্রেডের তারিখ দেখায় না।",
    ),
    (
        "fundamentals",
        "Free cash flow is commonly approximated as which calculation?",
        "ফ্রি ক্যাশ ফ্লো সাধারণত কোন হিসাব দিয়ে অনুমান করা হয়?",
        [
            "Revenue minus debt",
            "Operating cash flow minus capital expenditure",
            "Net income plus dividends",
        ],
        ["রাজস্ব বিয়োগ ঋণ", "অপারেটিং ক্যাশ ফ্লো বিয়োগ মূলধনী ব্যয়", "নিট আয় যোগ লভ্যাংশ"],
        1,
        "Operating cash flow minus capital expenditure estimates cash left after maintaining and growing the asset base.",
        "অপারেটিং ক্যাশ ফ্লো থেকে মূলধনী ব্যয় বাদ দিলে সম্পদ রক্ষা ও বৃদ্ধির পর অবশিষ্ট নগদের একটি ধারণা পাওয়া যায়।",
    ),
    (
        "valuation",
        "Why is a conventional P/E ratio not meaningful when EPS is negative?",
        "EPS ঋণাত্মক হলে প্রচলিত P/E কেন অর্থপূর্ণ নয়?",
        [
            "A loss creates a negative denominator, so the multiple does not represent a payback valuation",
            "The share has no price",
            "SEC blocks the calculation",
        ],
        [
            "লোকসান ঋণাত্মক হর তৈরি করে, তাই অনুপাতটি মূল্যায়নের পেব্যাক বোঝায় না",
            "শেয়ারের কোনো দাম নেই",
            "SEC হিসাবটি বন্ধ করে",
        ],
        0,
        "Negative earnings make the usual earnings multiple economically misleading; use other evidence and understand the loss.",
        "ঋণাত্মক আয় প্রচলিত আয়-ভিত্তিক অনুপাতকে বিভ্রান্তিকর করে; অন্য প্রমাণ দেখুন এবং লোকসানের কারণ বুঝুন।",
    ),
    (
        "risk",
        "What does RSI above 70 establish by itself?",
        "RSI ৭০-এর উপরে থাকলে একা কী প্রমাণ হয়?",
        [
            "The stock must fall tomorrow",
            "Recent momentum is stretched, but no future direction is guaranteed",
            "The company is profitable",
        ],
        [
            "শেয়ারটি কাল অবশ্যই পড়বে",
            "সাম্প্রতিক মোমেন্টাম প্রসারিত, কিন্তু ভবিষ্যৎ দিক নিশ্চিত নয়",
            "কোম্পানিটি লাভজনক",
        ],
        1,
        "RSI describes recent price momentum. Overbought can persist and is not a standalone sell signal.",
        "RSI সাম্প্রতিক দামের মোমেন্টাম বর্ণনা করে। অতিরিক্ত কেনা অবস্থা চলতে পারে এবং এটি একা বিক্রির সংকেত নয়।",
    ),
    (
        "market_basics",
        "Why are adjusted closes preferable for long-horizon return analysis?",
        "দীর্ঘমেয়াদি রিটার্ন বিশ্লেষণে সমন্বিত ক্লোজ কেন ভালো?",
        [
            "They account for splits and distributions",
            "They remove every market decline",
            "They are intraday quotes",
        ],
        ["এগুলো স্প্লিট ও বিতরণের প্রভাব সমন্বয় করে", "এগুলো বাজারের সব পতন সরিয়ে দেয়", "এগুলো ইন্ট্রাডে কোট"],
        0,
        "Adjusted prices reduce false jumps caused by splits and distributions, making historical comparisons more coherent.",
        "সমন্বিত দাম স্প্লিট ও বিতরণজনিত কৃত্রিম লাফ কমায়, ফলে ঐতিহাসিক তুলনা বেশি সঙ্গত হয়।",
    ),
    (
        "market_basics",
        "What does unusually high volume prove?",
        "অস্বাভাবিক বেশি ভলিউম কী প্রমাণ করে?",
        [
            "A guaranteed rally",
            "Unusual participation that needs price and news context",
            "Institutional buying only",
        ],
        ["নিশ্চিত মূল্যবৃদ্ধি", "অস্বাভাবিক অংশগ্রহণ, যা দাম ও খবরের প্রেক্ষাপট চায়", "শুধু প্রাতিষ্ঠানিক কেনা"],
        1,
        "Volume shows activity, not motive or direction. Pair it with price behavior and official evidence.",
        "ভলিউম কার্যকলাপ দেখায়, উদ্দেশ্য বা দিক নয়। দাম ও অফিসিয়াল প্রমাণের সাথে মিলিয়ে দেখুন।",
    ),
    (
        "risk",
        "What is a key risk of a market order in a thin stock?",
        "কম লিকুইড শেয়ারে মার্কেট অর্ডারের প্রধান ঝুঁকি কী?",
        [
            "Execution can occur far from the last displayed price",
            "The order can never fill",
            "The SEC changes the ticker",
        ],
        ["শেষ দেখা দাম থেকে অনেক দূরে অর্ডার কার্যকর হতে পারে", "অর্ডার কখনো পূরণ হবে না", "SEC টিকার বদলে দেয়"],
        0,
        "A wide spread and shallow order book can create substantial slippage. Order size and liquidity matter.",
        "বড় স্প্রেড ও পাতলা অর্ডার বুক উল্লেখযোগ্য স্লিপেজ তৈরি করতে পারে। অর্ডারের আকার ও লিকুইডিটি গুরুত্বপূর্ণ।",
    ),
]


def upgrade() -> None:
    op.add_column("company_dividends", sa.Column("cash_per_share", sa.Float(), nullable=True))
    op.add_column("market_summary", sa.Column("benchmark_code", sa.String(16), nullable=True))
    op.add_column("market_summary", sa.Column("benchmark_close", sa.Float(), nullable=True))
    op.add_column("market_summary", sa.Column("benchmark_change", sa.Float(), nullable=True))
    op.create_table(
        "sec_filings",
        sa.Column("market", sa.String(8), nullable=False),
        sa.Column("accession_number", sa.String(25), nullable=False),
        sa.Column("code", sa.String(16), nullable=False),
        sa.Column("cik", sa.BigInteger(), nullable=False),
        sa.Column("form", sa.String(16), nullable=False),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("filing_date", sa.Date(), nullable=False),
        sa.Column("report_date", sa.Date(), nullable=True),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("primary_document", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("items", sa.Text(), nullable=True),
        sa.Column("is_xbrl", sa.Boolean(), nullable=False),
        sa.Column("is_inline_xbrl", sa.Boolean(), nullable=False),
        sa.Column("filing_url", sa.Text(), nullable=False),
        sa.Column("source_updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("market", "code", "accession_number"),
    )
    op.create_index("ix_sec_filings_code", "sec_filings", ["code"])
    op.create_index("ix_sec_filings_cik", "sec_filings", ["cik"])
    op.create_index("ix_sec_filings_form", "sec_filings", ["form"])
    op.create_index("ix_sec_filings_filing_date", "sec_filings", ["filing_date"])
    op.create_index("ix_sec_filings_category", "sec_filings", ["category"])
    op.create_index("ix_sec_filings_symbol_date", "sec_filings", ["market", "code", "filing_date"])
    op.create_index("ix_sec_filings_symbol_form", "sec_filings", ["market", "code", "form"])

    op.create_table(
        "sec_financial_facts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("market", sa.String(8), nullable=False),
        sa.Column("code", sa.String(16), nullable=False),
        sa.Column("metric", sa.String(40), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("unit", sa.String(24), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=True),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("period_type", sa.String(12), nullable=False),
        sa.Column("fiscal_year", sa.Integer(), nullable=True),
        sa.Column("fiscal_period", sa.String(8), nullable=True),
        sa.Column("form", sa.String(16), nullable=False),
        sa.Column("filed_at", sa.Date(), nullable=False),
        sa.Column("accession_number", sa.String(25), nullable=False),
        sa.Column("taxonomy", sa.String(32), nullable=False),
        sa.Column("source_concept", sa.String(128), nullable=False),
        sa.Column("frame", sa.String(32), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "period_type IN ('instant', 'quarter', 'annual')",
            name="ck_sec_financial_fact_period_type",
        ),
        sa.UniqueConstraint(
            "market",
            "code",
            "metric",
            "period_end",
            "period_type",
            name="uq_sec_financial_fact_period",
        ),
    )
    op.create_index("ix_sec_financial_facts_market", "sec_financial_facts", ["market"])
    op.create_index("ix_sec_financial_facts_code", "sec_financial_facts", ["code"])
    op.create_index("ix_sec_financial_facts_metric", "sec_financial_facts", ["metric"])
    op.create_index(
        "ix_sec_financial_facts_symbol_period",
        "sec_financial_facts",
        ["market", "code", "period_end"],
    )
    op.create_index(
        "ix_sec_financial_facts_metric_period",
        "sec_financial_facts",
        ["market", "metric", "period_end"],
    )

    op.create_table(
        "security_identifiers",
        sa.Column("market", sa.String(8), nullable=False),
        sa.Column("code", sa.String(16), nullable=False),
        sa.Column("identifier_type", sa.String(16), nullable=False),
        sa.Column("identifier", sa.String(32), nullable=False),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("match_method", sa.String(32), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("market", "identifier_type", "identifier"),
    )
    op.create_index("ix_security_identifiers_code", "security_identifiers", ["code"])
    op.create_index("ix_security_identifiers_identifier", "security_identifiers", ["identifier"])

    op.create_table(
        "institutional_managers",
        sa.Column("cik", sa.BigInteger(), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("latest_report_date", sa.Date(), nullable=True),
        sa.Column("latest_filing_date", sa.Date(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "institutional_positions",
        sa.Column("market", sa.String(8), nullable=False),
        sa.Column("code", sa.String(16), nullable=False),
        sa.Column("report_date", sa.Date(), nullable=False),
        sa.Column(
            "manager_cik",
            sa.BigInteger(),
            sa.ForeignKey("institutional_managers.cik"),
            nullable=False,
        ),
        sa.Column("manager_name", sa.Text(), nullable=False),
        sa.Column("cusip", sa.String(9), nullable=False),
        sa.Column("shares", sa.BigInteger(), nullable=False),
        sa.Column("value_usd", sa.Float(), nullable=False),
        sa.Column("prior_shares", sa.BigInteger(), nullable=True),
        sa.Column("share_change", sa.BigInteger(), nullable=True),
        sa.Column("change_pct", sa.Float(), nullable=True),
        sa.Column("change_type", sa.String(12), nullable=False),
        sa.Column("filing_date", sa.Date(), nullable=False),
        sa.Column("accession_number", sa.String(25), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("value_rank", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "change_type IN ('new', 'increased', 'reduced', 'unchanged', 'exited')",
            name="ck_institutional_position_change_type",
        ),
        sa.PrimaryKeyConstraint("market", "code", "report_date", "manager_cik"),
    )
    op.create_index(
        "ix_institutional_positions_change_type", "institutional_positions", ["change_type"]
    )
    op.create_index(
        "ix_institutional_positions_symbol_period",
        "institutional_positions",
        ["market", "code", "report_date"],
    )
    op.create_index(
        "ix_institutional_positions_manager_period",
        "institutional_positions",
        ["manager_cik", "report_date"],
    )

    op.create_table(
        "institutional_holding_summaries",
        sa.Column("market", sa.String(8), nullable=False),
        sa.Column("code", sa.String(16), nullable=False),
        sa.Column("report_date", sa.Date(), nullable=False),
        sa.Column("prior_report_date", sa.Date(), nullable=True),
        sa.Column("latest_filing_date", sa.Date(), nullable=False),
        sa.Column("managers_count", sa.Integer(), nullable=False),
        sa.Column("total_shares", sa.BigInteger(), nullable=False),
        sa.Column("total_value_usd", sa.Float(), nullable=False),
        sa.Column("new_positions", sa.Integer(), nullable=False),
        sa.Column("increased_positions", sa.Integer(), nullable=False),
        sa.Column("reduced_positions", sa.Integer(), nullable=False),
        sa.Column("exited_positions", sa.Integer(), nullable=False),
        sa.Column("unchanged_positions", sa.Integer(), nullable=False),
        sa.Column("net_share_change", sa.BigInteger(), nullable=True),
        sa.Column("net_change_pct", sa.Float(), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("market", "code", "report_date"),
    )
    op.create_index(
        "ix_institutional_holding_summaries_symbol_period",
        "institutional_holding_summaries",
        ["market", "code", "report_date"],
    )

    op.create_table(
        "regulatory_data_state",
        sa.Column("market", sa.String(8), nullable=False),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("as_of_date", sa.Date(), nullable=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("records", sa.Integer(), nullable=False),
        sa.Column("symbols_covered", sa.Integer(), nullable=False),
        sa.Column("downloaded_bytes", sa.BigInteger(), nullable=False),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.PrimaryKeyConstraint("market", "source"),
    )
    quiz = sa.table(
        "quiz_questions",
        sa.column("market", sa.String),
        sa.column("topic", sa.String),
        sa.column("question_i18n", sa.JSON),
        sa.column("choices_i18n", sa.JSON),
        sa.column("answer_idx", sa.Integer),
        sa.column("explanation_i18n", sa.JSON),
        sa.column("is_active", sa.Boolean),
    )
    op.bulk_insert(
        quiz,
        [
            {
                "market": "US",
                "topic": topic,
                "question_i18n": {"en": question_en, "bn": question_bn},
                "choices_i18n": {"en": choices_en, "bn": choices_bn},
                "answer_idx": answer,
                "explanation_i18n": {"en": explanation_en, "bn": explanation_bn},
                "is_active": True,
            }
            for (
                topic,
                question_en,
                question_bn,
                choices_en,
                choices_bn,
                answer,
                explanation_en,
                explanation_bn,
            ) in US_QUIZ
        ],
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "DELETE FROM quiz_answers WHERE question_id IN "
            "(SELECT id FROM quiz_questions WHERE market = 'US')"
        )
    )
    op.execute(sa.text("DELETE FROM quiz_questions WHERE market = 'US'"))
    op.drop_table("regulatory_data_state")
    op.drop_index(
        "ix_institutional_holding_summaries_symbol_period",
        table_name="institutional_holding_summaries",
    )
    op.drop_table("institutional_holding_summaries")
    op.drop_index("ix_institutional_positions_manager_period", table_name="institutional_positions")
    op.drop_index("ix_institutional_positions_symbol_period", table_name="institutional_positions")
    op.drop_index("ix_institutional_positions_change_type", table_name="institutional_positions")
    op.drop_table("institutional_positions")
    op.drop_table("institutional_managers")
    op.drop_index("ix_security_identifiers_identifier", table_name="security_identifiers")
    op.drop_index("ix_security_identifiers_code", table_name="security_identifiers")
    op.drop_table("security_identifiers")
    op.drop_index("ix_sec_financial_facts_metric_period", table_name="sec_financial_facts")
    op.drop_index("ix_sec_financial_facts_symbol_period", table_name="sec_financial_facts")
    op.drop_index("ix_sec_financial_facts_metric", table_name="sec_financial_facts")
    op.drop_index("ix_sec_financial_facts_code", table_name="sec_financial_facts")
    op.drop_index("ix_sec_financial_facts_market", table_name="sec_financial_facts")
    op.drop_table("sec_financial_facts")
    op.drop_index("ix_sec_filings_symbol_form", table_name="sec_filings")
    op.drop_index("ix_sec_filings_symbol_date", table_name="sec_filings")
    op.drop_index("ix_sec_filings_category", table_name="sec_filings")
    op.drop_index("ix_sec_filings_filing_date", table_name="sec_filings")
    op.drop_index("ix_sec_filings_form", table_name="sec_filings")
    op.drop_index("ix_sec_filings_cik", table_name="sec_filings")
    op.drop_index("ix_sec_filings_code", table_name="sec_filings")
    op.drop_table("sec_filings")
    op.drop_column("company_dividends", "cash_per_share")
    op.drop_column("market_summary", "benchmark_change")
    op.drop_column("market_summary", "benchmark_close")
    op.drop_column("market_summary", "benchmark_code")
