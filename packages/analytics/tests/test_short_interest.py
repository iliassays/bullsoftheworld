from __future__ import annotations

import datetime as dt

import pytest

from bulls.analytics.short_interest import (
    ShortInterestObservation,
    latest_known,
    short_interest_change_pct,
    short_interest_pct_of_shares_outstanding,
)


def observation(settlement: str, known: str, shares: float, **kwargs) -> ShortInterestObservation:
    return ShortInterestObservation(
        settlement_date=dt.date.fromisoformat(settlement),
        known_at=dt.datetime.fromisoformat(known).replace(tzinfo=dt.UTC),
        shares_short=shares,
        **kwargs,
    )


def test_latest_known_selects_on_dissemination_not_settlement() -> None:
    rows = [
        observation("2026-06-15", "2026-06-25T23:59:59", 1_000),
        observation("2026-06-30", "2026-07-13T23:59:59", 2_000),
    ]

    # 2026-07-05 is after the June-30 settlement but before it was disseminated: using the
    # settlement date here would leak a week of hindsight.
    assert latest_known(rows, as_of=dt.date(2026, 7, 5)).shares_short == 1_000
    assert latest_known(rows, as_of=dt.date(2026, 7, 13)).shares_short == 2_000


def test_latest_known_returns_none_before_any_dissemination() -> None:
    rows = [observation("2026-06-30", "2026-07-13T23:59:59", 2_000)]

    assert latest_known(rows, as_of=dt.date(2026, 7, 1)) is None
    assert latest_known([], as_of=dt.date(2026, 7, 20)) is None


def test_short_interest_pct_uses_shares_outstanding() -> None:
    assert short_interest_pct_of_shares_outstanding(5_000, 100_000) == pytest.approx(5.0)


def test_short_interest_pct_fails_closed_on_missing_or_invalid_inputs() -> None:
    assert short_interest_pct_of_shares_outstanding(None, 100_000) is None
    assert short_interest_pct_of_shares_outstanding(5_000, None) is None
    assert short_interest_pct_of_shares_outstanding(5_000, 0) is None
    assert short_interest_pct_of_shares_outstanding(-1, 100_000) is None


def test_short_interest_change_reports_direction() -> None:
    rising = observation("2026-06-30", "2026-07-13T23:59:59", 1_200, previous_shares_short=1_000)
    flatline = observation("2026-06-30", "2026-07-13T23:59:59", 1_000)

    assert short_interest_change_pct(rising) == pytest.approx(20.0)
    assert short_interest_change_pct(flatline) is None
