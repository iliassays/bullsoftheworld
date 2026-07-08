"""Research brief guardrails.

These tests are pure: no DB, no LLM. The endpoint does DB retrieval, but the retail-safety behavior
that must not drift lives in the ranking/render helpers.
"""

from __future__ import annotations

import datetime as dt

from api.routers.research import (
    _ADVICE_RE,
    ResearchSource,
    _dedupe_sources,
    _intent,
    _is_recent_official,
    _quality,
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


def test_vector_and_sql_sources_are_deduped_by_source_identity():
    vector_hit = _src(id="10", snippet="Vector chunk from the same announcement.")
    sql_hit = _src(id="10", snippet="SQL fallback source from the same announcement.")
    other = _src(type="post", id="10", reliability="crowd", title="Recent platform post")

    out = _dedupe_sources([vector_hit, sql_hit, other])

    assert out == [vector_hit, other]
