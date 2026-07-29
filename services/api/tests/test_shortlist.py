"""Unit tests for the Daily Shortlist route helpers and response contract.

Pure functions plus model construction — no DB, so these always run. The slate ranking itself is
covered by packages/analytics/tests/test_daily_shortlist.py; what is locked in here is that the
route cannot present the slate as a return claim and cannot hide staleness.
"""

from __future__ import annotations

import datetime as dt

import pytest

from api.routers.shortlist import (
    ShortlistFactOut,
    ShortlistResponse,
    ShortlistRow,
    _archive_integrity,
    _fact_outputs,
    _measure_market_session_outcome,
    _measure_outcome,
    _outcome,
    _range_position_pct,
    _select_archive_date,
)
from bulls.analytics.daily_shortlist import BASE_RATES, METHODOLOGY_VERSION
from bulls.core.models import DailyBar, DailyShortlistState


class _Analytics:
    """Minimal stand-in for the TickerAnalytics columns the helper reads."""

    def __init__(self, last_close, week52_high, week52_low):
        self.last_close = last_close
        self.week52_high = week52_high
        self.week52_low = week52_low


@pytest.mark.parametrize(
    ("close", "high", "low", "expected"),
    [
        (100.0, 200.0, 100.0, 0.0),  # sitting exactly on the 52-week low
        (200.0, 200.0, 100.0, 100.0),  # exactly on the high
        (150.0, 200.0, 100.0, 50.0),  # mid-range
        (110.0, 200.0, 100.0, 10.0),  # bottom of the range
    ],
)
def test_range_position_maps_the_52_week_band(close, high, low, expected):
    assert _range_position_pct(_Analytics(close, high, low)) == pytest.approx(expected)


def test_range_position_returns_none_rather_than_guessing():
    # A missing bound, or a degenerate range (a stock that never moved), is unknowable — not zero.
    assert _range_position_pct(_Analytics(100.0, None, 50.0)) is None
    assert _range_position_pct(_Analytics(100.0, 200.0, None)) is None
    assert _range_position_pct(_Analytics(100.0, 100.0, 100.0)) is None


def _response(**overrides) -> ShortlistResponse:
    base = dict(
        market="DSE",
        as_of=dt.date(2026, 7, 23),
        quote_as_of=dt.datetime(2026, 7, 23, 10, 0, tzinfo=dt.UTC),
        is_delayed=True,
        size=5,
        rows=[
            ShortlistRow(
                code="GP",
                name_en="Grameenphone",
                rank=1,
                attention_score=0.9,
                close=300.0,
                change_pct=2.5,
                facts=[ShortlistFactOut(kind="move", value=2.5)],
                cautions=[],
                reasons=["rose 2.50% today"],
                unknowns=[],
            )
        ],
        eligible_names=381,
        excluded_illiquid=12,
        excluded_short_history=8,
        base_rates=dict(BASE_RATES),
        notes=["Attention ranking, not a forecast."],
    )
    base.update(overrides)
    return ShortlistResponse(**base)


def test_response_never_claims_a_return_by_default():
    """The measured finding is that ranking did WORSE than random; the payload must say so."""
    resp = _response()

    assert resp.is_return_claim is False
    assert resp.methodology_version == METHODOLOGY_VERSION
    # The base rates travel with every payload so a client cannot render the slate without them.
    assert resp.base_rates["return_rank_vs_random_pp"] == -1.24
    assert "random draw" in resp.base_rates["verdict"]


def test_freshness_is_explicit_and_defaults_to_delayed():
    """Platform rule: never fake data freshness. Absent quote data must not read as live."""
    resp = _response(quote_as_of=None)

    assert resp.quote_as_of is None
    assert resp.is_delayed is True

    # And a real quote timestamp is carried through rather than dropped.
    stamped = _response()
    assert stamped.quote_as_of == dt.datetime(2026, 7, 23, 10, 0, tzinfo=dt.UTC)


def test_exclusion_counts_survive_serialisation():
    """A reader must be able to see how much of the universe was filtered away."""
    payload = _response().model_dump()

    assert payload["eligible_names"] == 381
    assert payload["excluded_illiquid"] == 12
    assert payload["excluded_short_history"] == 8


def test_rows_carry_their_evidence_and_unknowns():
    row = ShortlistRow(
        code="X",
        rank=1,
        attention_score=0.5,
        close=10.0,
        change_pct=-12.0,
        facts=[ShortlistFactOut(kind="move", value=-12.0)],
        cautions=[ShortlistFactOut(kind="possible_corporate_action")],
        reasons=["fell 12.00% today"],
        unknowns=["large drop may be a corporate action — DSE closes are unadjusted"],
    )

    payload = row.model_dump()
    assert payload["reasons"] == ["fell 12.00% today"]
    assert "corporate action" in payload["unknowns"][0]


def test_facts_are_structured_so_a_bangla_client_can_localise():
    """A Bangla-first tenant must not receive English prose as its only evidence."""
    row = _response().rows[0]

    assert [f.kind for f in row.facts] == ["move"]
    assert row.facts[0].value == 2.5
    # The English rendering still travels, as the fallback for an unknown kind.
    assert row.reasons == ["rose 2.50% today"]


def test_cautions_are_structured_too():
    row = ShortlistRow(
        code="X",
        rank=1,
        attention_score=0.5,
        close=10.0,
        change_pct=-12.0,
        facts=[],
        cautions=[ShortlistFactOut(kind="extreme_pe", value=820.0)],
        reasons=[],
        unknowns=["P/E 820 — earnings are negligible against the price"],
    )

    assert row.cautions[0].kind == "extreme_pe"
    assert row.cautions[0].value == 820.0


def _bar(day: int, *, close: float, high: float, low: float | None = None) -> DailyBar:
    return DailyBar(
        market="DSE",
        code="GP",
        date=dt.date(2026, 7, day),
        open=close,
        high=high,
        low=close if low is None else low,
        close=close,
        volume=10_000,
        adjusted_close=None,
        source="test",
    )


def test_outcome_uses_later_bars_and_reports_the_latest_observation():
    result = _outcome(
        100.0,
        [
            _bar(25, close=104.0, high=107.0),
            _bar(24, close=102.0, high=105.0),
        ],
    )

    return_since, highest_since, sessions, outcome_as_of = result
    assert return_since == pytest.approx(4.0)
    assert highest_since == pytest.approx(7.0)
    assert sessions == 2
    assert outcome_as_of == dt.date(2026, 7, 25)


def test_outcome_does_not_manufacture_data_when_no_later_session_exists():
    assert _outcome(100.0, []) == (None, None, 0, None)


def test_outcome_story_uses_fixed_later_session_horizons_and_keeps_losses():
    measured = _measure_outcome(
        100.0,
        [
            _bar(19, close=103.0, high=105.0, low=98.0),
            _bar(20, close=97.0, high=104.0, low=95.0),
            _bar(21, close=101.0, high=103.0, low=96.0),
            _bar(22, close=99.0, high=102.0, low=94.0),
            _bar(23, close=108.0, high=110.0, low=98.0),
            _bar(24, close=106.0, high=109.0, low=104.0),
            _bar(25, close=105.0, high=107.0, low=103.0),
            _bar(26, close=107.0, high=108.0, low=104.0),
            _bar(27, close=109.0, high=110.0, low=106.0),
            _bar(28, close=112.0, high=114.0, low=108.0),
        ],
    )

    assert measured.latest_close == 112.0
    assert measured.return_since_pct == pytest.approx(12.0)
    assert measured.max_went_pct == pytest.approx(14.0)
    assert measured.min_went_pct == pytest.approx(-6.0)
    assert measured.sessions_since == 10
    assert [
        (item.sessions, item.close_return_pct, item.as_of) for item in measured.horizon_returns
    ] == [
        (1, pytest.approx(3.0), dt.date(2026, 7, 19)),
        (3, pytest.approx(1.0), dt.date(2026, 7, 21)),
        (5, pytest.approx(8.0), dt.date(2026, 7, 23)),
        (10, pytest.approx(12.0), dt.date(2026, 7, 28)),
    ]


def test_outcome_story_marks_unobserved_horizons_pending_instead_of_zero():
    measured = _measure_outcome(100.0, [_bar(28, close=102.0, high=103.0)])

    assert [item.sessions for item in measured.horizon_returns] == [1, 3, 5, 10]
    assert measured.horizon_returns[0].close_return_pct == pytest.approx(2.0)
    assert measured.horizon_returns[0].as_of == dt.date(2026, 7, 28)
    assert all(item.close_return_pct is None for item in measured.horizon_returns[1:])
    assert all(item.as_of is None for item in measured.horizon_returns[1:])


def test_market_session_outcome_does_not_relabel_a_later_bar_as_one_session():
    market_dates = [dt.date(2026, 7, day) for day in (24, 25, 26, 27, 28)]
    measured = _measure_market_session_outcome(
        100.0,
        [
            # The ticker has no bar on the first market session after selection.
            _bar(25, close=103.0, high=104.0),
            _bar(26, close=104.0, high=105.0),
            _bar(27, close=105.0, high=106.0),
            _bar(28, close=106.0, high=107.0),
        ],
        market_dates,
    )

    assert measured.sessions_since == 5
    assert measured.horizon_returns[0].close_return_pct is None
    assert measured.horizon_returns[0].as_of is None
    assert measured.horizon_returns[1].close_return_pct == pytest.approx(4.0)
    assert measured.horizon_returns[1].as_of == dt.date(2026, 7, 26)


def _snapshot(
    code: str,
    *,
    date: dt.date,
    rank: int,
    close: float,
    change_pct: float,
) -> DailyShortlistState:
    return DailyShortlistState(
        market="DSE",
        as_of_date=date,
        code=code,
        rank=rank,
        attention_score=0.9,
        close=close,
        change_pct=change_pct,
        sector=None,
        pe=None,
        facts=[],
        cautions=[],
        eligible_names=100,
        excluded_illiquid=10,
        excluded_short_history=5,
        slate_size=2,
        notes=[],
        base_rates={},
        evidence_mode="forward",
        methodology_version="daily-shortlist-v1",
    )


def test_archive_integrity_reconciles_close_move_size_and_ranks():
    first = dt.date(2026, 7, 23)
    second = dt.date(2026, 7, 24)
    snapshots = [
        _snapshot("GP", date=second, rank=1, close=110.0, change_pct=10.0),
        _snapshot("SQURPHARMA", date=second, rank=2, close=220.0, change_pct=10.0),
    ]
    bars = [
        DailyBar(
            market="DSE",
            code=code,
            date=date,
            open=close,
            high=close,
            low=close,
            close=close,
            volume=10_000,
            adjusted_close=None,
            source="test",
        )
        for code, date, close in (
            ("GP", first, 100.0),
            ("GP", second, 110.0),
            ("SQURPHARMA", first, 200.0),
            ("SQURPHARMA", second, 220.0),
        )
    ]

    integrity = _archive_integrity(snapshots, bars, [first, second])

    assert integrity.matched_selection_closes == 2
    assert integrity.close_mismatches == 0
    assert integrity.matched_selection_moves == 2
    assert integrity.move_mismatches == 0
    assert integrity.incomplete_sessions == 0
    assert integrity.invalid_rank_sessions == 0


def test_archive_date_never_moves_forward_past_the_request():
    dates = [
        dt.date(2026, 7, 25),
        dt.date(2026, 7, 23),
        dt.date(2026, 7, 22),
    ]

    assert _select_archive_date(dates, None) == dt.date(2026, 7, 25)
    assert _select_archive_date(dates, dt.date(2026, 7, 24)) == dt.date(2026, 7, 23)
    assert _select_archive_date(dates, dt.date(2026, 7, 1)) is None


def test_archived_structured_facts_regenerate_the_matching_fallback():
    facts, rendered = _fact_outputs([{"kind": "move", "value": 2.5}])

    assert facts == [ShortlistFactOut(kind="move", value=2.5)]
    assert rendered == ["rose 2.50% today"]
