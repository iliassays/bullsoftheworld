"""Research brief guardrails.

These tests are pure: no DB, no LLM. The endpoint does DB retrieval, but the retail-safety behavior
that must not drift lives in the ranking/render helpers.
"""

from __future__ import annotations

import datetime as dt

from api.routers.research import (
    _ADVICE_RE,
    ResearchSource,
    _build_insights,
    _dedupe_sources,
    _intent,
    _is_recent_official,
    _is_risk_source,
    _quality,
    _rank_sources,
    _render_answer,
    _source_score,
)


def _src(**overrides) -> ResearchSource:
    today = dt.datetime.now(dt.UTC).date()
    base = dict(
        type="announcement",
        id="1",
        title="Earnings: EPS increased year over year",
        date=str(today),
        snippet="The company reported EPS of 2.10 compared with 1.20 for the same period.",
        reliability="official",
    )
    base.update(overrides)
    return ResearchSource(**base)


def test_intent_routing_keeps_common_retail_questions_constrained():
    assert _intent("why is GP moving today?") == "why_moving"
    assert _intent("explain the dividend and record date") == "dividend"
    assert _intent("what changed in EPS?") == "earnings"
    assert _intent("what are people saying?") == "crowd"
    assert _intent("any red flags or risks?") == "red_flags"


def test_advice_questions_are_redirected_not_answered_as_recommendations():
    assert _ADVICE_RE.search("should I buy GP now?")
    answer = _render_answer(
        code="GP",
        question="should I buy GP now?",
        intent="why_moving",
        facts=["$GP last traded at ৳207 (+2.00% today, volume 10,000, as of 2026-07-08)."],
        sources=[_src()],
        official_catalyst=True,
        evidence_quality="strong",
        blocked_advice=True,
    )
    assert answer.startswith("I cannot tell you whether to buy, sell, hold, or set a target.")
    assert "recent official source" in answer
    assert "buy GP" not in answer


def test_official_sources_rank_above_crowd_posts():
    official = _src(title="Dividend: 10% cash dividend declared")
    crowd = _src(
        type="post",
        id="2",
        title="Recent platform post (bull)",
        snippet="Everyone says dividend is coming.",
        reliability="crowd",
    )
    question = "explain dividend"
    assert _source_score(official, question) > _source_score(crowd, question)
    assert _quality([official, crowd], official_catalyst=True, intent="dividend") == "strong"


def test_no_official_catalyst_is_called_out_for_moving_question():
    answer = _render_answer(
        code="GP",
        question="why is this moving?",
        intent="why_moving",
        facts=["$GP last traded at ৳207 (+2.00% today, volume 10,000, as of 2026-07-08)."],
        sources=[
            _src(
                type="post",
                id="2",
                title="Recent platform post (bull)",
                snippet="Retail discussion is active.",
                reliability="crowd",
            )
        ],
        official_catalyst=False,
        evidence_quality="weak",
        blocked_advice=False,
    )
    assert "do not see a recent official DSE catalyst" in answer
    assert "Evidence quality: weak" in answer


def test_old_official_news_is_context_not_today_catalyst():
    old_day = dt.datetime.now(dt.UTC).date() - dt.timedelta(days=45)
    old = _src(date=str(old_day), title="Dividend: GP: Dividend Disbursement")
    assert not _is_recent_official(old, intent="why_moving")
    assert _is_recent_official(old, intent="dividend")
    answer = _render_answer(
        code="GP",
        question="why is this moving?",
        intent="why_moving",
        facts=["$GP last traded at ৳259.4 (+0.19% today, volume 119,160, as of 2026-07-08)."],
        sources=[old],
        official_catalyst=False,
        evidence_quality="weak",
        blocked_advice=False,
    )
    assert "not recent enough to treat as today's catalyst" in answer


def test_bangla_moving_answer_distinguishes_old_filing_from_fresh_catalyst():
    old_day = dt.datetime.now(dt.UTC).date() - dt.timedelta(days=45)
    old = _src(date=str(old_day), title="Earnings: SEAPEARL: Q3 Financials")
    answer = _render_answer(
        code="SEAPEARL",
        question="why is this moving?",
        intent="why_moving",
        facts=["$SEAPEARL সর্বশেষ ৳45 দরে ট্রেড করেছে।"],
        sources=[old],
        official_catalyst=False,
        evidence_quality="mixed",
        blocked_advice=False,
        lang="bn",
    )

    assert "সাম্প্রতিক অফিসিয়াল ডিএসই কারণ দেখছি না" in answer
    assert "পুরোনো অফিসিয়াল প্রসঙ্গ আছে" in answer
    assert "Evidence quality" not in answer
    assert "Bottom line" not in answer


def test_bangla_insights_do_not_return_english_retail_copy():
    class Analytics:
        pe_ratio = 18.97
        pe_vs_sector = 0.71
        rsi_14 = 76.0
        relative_volume = 4.3
        cmf_20 = 0.31
        obv_slope = 0.27
        institute_delta = -0.21
        foreign_delta = 0.0

    insights = _build_insights(
        analytics=Analytics(),
        sources=[_src(title="Earnings: SEAPEARL: Q3 Financials")],
        posts_24h=4,
        chatter_x=2.7,
        lang="bn",
    )

    rendered = " ".join(f"{i.title} {i.detail} {i.evidence}" for i in insights)
    assert "Short-term move is crowded" not in rendered
    assert "Official disclosure" not in rendered
    assert "সূত্র" not in rendered or "Evidence" not in rendered
    assert "স্বল্পমেয়াদি মুভ ভিড়যুক্ত" in rendered


def test_vector_and_sql_sources_are_deduped_by_source_identity():
    vector_hit = _src(id="10", snippet="Vector chunk from the same announcement.")
    sql_hit = _src(id="10", snippet="SQL fallback source from the same announcement.")
    other = _src(type="post", id="10", reliability="crowd", title="Recent platform post")

    out = _dedupe_sources([vector_hit, sql_hit, other])

    assert out == [vector_hit, other]


def test_latest_news_is_date_led_not_hash_similarity_led():
    old_agm = _src(
        id="old",
        date=str(dt.datetime.now(dt.UTC).date() - dt.timedelta(days=200)),
        title="Corporate Action: BSC: Change of AGM Date",
        snippet="AGM date changed after earlier dividend declaration.",
    )
    latest_q3 = _src(
        id="new",
        date=str(dt.datetime.now(dt.UTC).date() - dt.timedelta(days=45)),
        title="Earnings: BSC: Q3 Financials",
        snippet="EPS was lower versus the same period last year.",
    )

    ranked = _rank_sources(
        [old_agm, latest_q3], question="Explain latest news", intent="latest_news"
    )

    assert ranked[0] == latest_q3


def test_red_flags_suppress_routine_record_date_halts():
    routine_halt = _src(
        title="Halt: BSC: Suspension for Record Date",
        snippet="Trading will remain suspended on the record date.",
    )
    overbought = _src(
        type="signal",
        id="sig",
        title="BullsOfDhakaLevels: rsi overbought",
        snippet="RSI overbought signal.",
        reliability="system",
    )

    assert not _is_risk_source(routine_halt)
    assert _is_risk_source(overbought)
    assert _rank_sources(
        [routine_halt, overbought], question="Any red flags?", intent="red_flags"
    ) == [overbought]


def test_crowd_question_does_not_claim_strong_official_evidence_without_posts():
    official = _src(title="Earnings: BSC: Q3 Financials")

    assert _rank_sources([official], question="What are people saying?", intent="crowd") == []
    assert _quality([], official_catalyst=False, intent="crowd") == "weak"


def test_financial_insights_surface_valuation_technical_and_disclosure_lenses():
    class Analytics:
        pe_ratio = 5.9
        pe_vs_sector = 0.62
        rsi_14 = 73.0
        relative_volume = 4.8
        cmf_20 = 0.12
        obv_slope = 0.31
        institute_delta = 0.42
        foreign_delta = None

    insights = _build_insights(
        analytics=Analytics(),
        sources=[_src(title="Earnings: BSC: Q3 Financials")],
        posts_24h=0,
        chatter_x=None,
    )

    by_lens = {i.lens: i for i in insights}
    assert by_lens["valuation"].stance == "constructive"
    assert "cheaper than sector" in by_lens["valuation"].title
    assert by_lens["technical"].stance == "risk"
    assert "crowded" in by_lens["technical"].title
    assert by_lens["disclosure"].evidence.startswith("Earnings: BSC")


def test_financial_insights_warn_when_no_official_source_anchors_the_read():
    class Analytics:
        pe_ratio = None
        pe_vs_sector = None
        rsi_14 = 55.0
        relative_volume = 1.0
        cmf_20 = None
        obv_slope = None
        institute_delta = None
        foreign_delta = None

    insights = _build_insights(
        analytics=Analytics(),
        sources=[],
        posts_24h=0,
        chatter_x=None,
    )

    disclosure = next(i for i in insights if i.lens == "disclosure")
    assert disclosure.stance == "risk"
    assert "No official source" in disclosure.title
