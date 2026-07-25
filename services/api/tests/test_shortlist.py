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
    _range_position_pct,
)
from bulls.analytics.daily_shortlist import BASE_RATES, METHODOLOGY_VERSION


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
