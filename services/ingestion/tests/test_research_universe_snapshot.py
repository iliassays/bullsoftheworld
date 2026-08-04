import datetime as dt
import uuid

from sqlalchemy.dialects import postgresql

from bulls.analytics.universe_policy import (
    UniverseDecision,
    UniverseEvidence,
    evaluate_universe_security,
)
from ingestion.research_universe_snapshot import (
    BarState,
    CandidateState,
    ListingObservationState,
    _bar_batch_statement,
    _session_calendar_statement,
    build_policy_input,
    candidate_input_fingerprint,
    listing_observation_matches,
    snapshot_model_ready,
    snapshot_quality,
    summarize_recent_bars,
)


def _candidate(**changes) -> CandidateState:
    values = {
        "code": "TEST",
        "security_id": uuid.UUID("12345678-1234-5678-1234-567812345678"),
        "instrument_type": "common_stock",
        "exchange": "NASDAQ",
        "is_active": True,
        "is_product_eligible": True,
        "is_hidden": False,
        "is_etf": False,
        "is_test_issue": False,
        "financial_status": "N",
        "category": None,
        "market_cap_mn": 500.0,
        "analytics_point_in_time_complete": False,
    }
    values.update(changes)
    return CandidateState(**values)


def test_recent_bar_summary_uses_session_value_not_raw_share_volume() -> None:
    rows = [
        ("TEST", dt.date(2026, 7, 31), 2.0, 1_000_000),
        ("TEST", dt.date(2026, 8, 3), 4.0, 2_000_000),
    ]

    result = summarize_recent_bars(rows)["TEST"]

    assert result.latest_bar_date == dt.date(2026, 8, 3)
    assert result.last_close == 4.0
    assert result.recent_sessions_observed == 2
    assert result.recent_sessions_traded == 2
    assert result.median_traded_value_20_mn == 5.0


def test_candidate_fingerprint_is_order_independent_and_change_sensitive() -> None:
    first = _candidate(code="AAA")
    second = _candidate(code="BBB")

    assert candidate_input_fingerprint([first, second]) == candidate_input_fingerprint(
        [second, first]
    )
    assert candidate_input_fingerprint([first]) != candidate_input_fingerprint(
        [_candidate(code="AAA", is_hidden=True)]
    )


def test_listing_evidence_requires_the_latest_observation_to_match_projection() -> None:
    candidate = _candidate()
    matching = ListingObservationState(
        security_id=candidate.security_id,
        instrument_type="COMMON_STOCK",
        exchange="nasdaq",
        is_active=True,
        is_product_eligible=True,
    )

    assert listing_observation_matches(candidate, matching)
    assert not listing_observation_matches(
        candidate,
        ListingObservationState(
            security_id=candidate.security_id,
            instrument_type="common_stock",
            exchange="NASDAQ",
            is_active=False,
            is_product_eligible=True,
        ),
    )
    assert not listing_observation_matches(candidate, None)


def test_builder_does_not_claim_reverse_split_or_dse_adjustment_coverage() -> None:
    as_of = dt.date(2026, 8, 3)
    bars = BarState(
        latest_bar_date=as_of,
        last_close=4.0,
        history_sessions=260,
        adjusted_sessions=260,
        recent_sessions_observed=20,
        recent_sessions_traded=20,
        median_traded_value_20_mn=5.0,
    )

    us = build_policy_input(
        market="US",
        as_of_date=as_of,
        candidate=_candidate(),
        bars=bars,
        listing_point_in_time=True,
    )
    dse = build_policy_input(
        market="DSE",
        as_of_date=as_of,
        candidate=_candidate(
            instrument_type="listed_instrument",
            exchange="DSE",
            financial_status="A",
            category="A",
        ),
        bars=bars,
        listing_point_in_time=True,
    )

    assert not us.evidence.bars_point_in_time
    assert not us.evidence.corporate_actions_complete
    assert not us.evidence.reverse_split_history_complete
    assert not dse.evidence.corporate_actions_complete


def test_builder_promotes_adjusted_us_bars_only_after_explicit_pit_certification() -> None:
    as_of = dt.date(2026, 8, 3)
    item = build_policy_input(
        market="US",
        as_of_date=as_of,
        candidate=_candidate(analytics_point_in_time_complete=True),
        bars=BarState(
            latest_bar_date=as_of,
            last_close=4.0,
            history_sessions=260,
            adjusted_sessions=260,
            recent_sessions_observed=20,
            recent_sessions_traded=20,
            median_traded_value_20_mn=5.0,
        ),
        listing_point_in_time=True,
    )

    assert item.evidence.bars_point_in_time
    assert item.evidence.corporate_actions_complete
    assert not item.evidence.reverse_split_history_complete


def test_bar_query_is_lateral_and_bounded_per_symbol() -> None:
    statement = _bar_batch_statement(
        "US",
        ["AAA", "BBB"],
        through_date=dt.date(2026, 8, 3),
    )
    sql = str(statement.compile(dialect=postgresql.dialect())).upper()

    assert "JOIN LATERAL" in sql
    assert "LIMIT" in sql
    assert "GROUP BY" not in sql


def test_session_calendar_combines_summary_and_configured_benchmark() -> None:
    statement = _session_calendar_statement(
        "US",
        through_date=dt.date(2026, 8, 3),
    )
    sql = str(
        statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    ).upper()

    assert "UNION" in sql
    assert "MARKET_SUMMARY" in sql
    assert "DAILY_BARS" in sql
    assert "SPY" in sql
    assert "LIMIT 20" in sql


def test_quality_report_keeps_research_and_model_readiness_separate() -> None:
    as_of = dt.date(2026, 8, 3)
    bars = BarState(
        latest_bar_date=as_of,
        last_close=4.0,
        history_sessions=260,
        adjusted_sessions=260,
        recent_sessions_observed=20,
        recent_sessions_traded=20,
        median_traded_value_20_mn=5.0,
    )
    item = build_policy_input(
        market="US",
        as_of_date=as_of,
        candidate=_candidate(),
        bars=bars,
        listing_point_in_time=True,
    )
    result = evaluate_universe_security(item)

    report = snapshot_quality([result])

    assert result.decision == UniverseDecision.ELIGIBLE
    assert not result.model_eligible
    assert report["decisions"] == {"eligible": 1}
    assert report["cohorts"] == {"us_small": 1}
    assert report["model_blockers"] == {
        "bars_evidence_not_point_in_time": 1,
        "corporate_action_history_incomplete": 1,
        "reverse_split_history_incomplete": 1,
    }


def test_snapshot_model_readiness_fails_closed_on_any_unknown_member() -> None:
    as_of = dt.date(2026, 8, 3)
    current = build_policy_input(
        market="US",
        as_of_date=as_of,
        candidate=_candidate(analytics_point_in_time_complete=True),
        bars=BarState(
            latest_bar_date=as_of,
            last_close=4.0,
            history_sessions=260,
            adjusted_sessions=260,
            recent_sessions_observed=20,
            recent_sessions_traded=20,
            median_traded_value_20_mn=5.0,
        ),
        listing_point_in_time=True,
    )
    certified = current.model_copy(
        update={
            "recent_reverse_split": False,
            "evidence": UniverseEvidence(
                listing_point_in_time=True,
                bars_point_in_time=True,
                capitalization_point_in_time=True,
                corporate_actions_complete=True,
                reverse_split_history_complete=True,
            ),
        }
    )
    complete = evaluate_universe_security(certified)
    blocked = evaluate_universe_security(
        certified.model_copy(update={"code": "BLOCKED", "market_cap_mn": None})
    )

    assert complete.model_eligible
    assert snapshot_model_ready([complete])
    assert not snapshot_model_ready([complete, blocked])
