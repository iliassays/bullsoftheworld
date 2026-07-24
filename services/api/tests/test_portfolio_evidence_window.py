from __future__ import annotations

import datetime as dt
from types import SimpleNamespace

import pytest

from api.institutional_research.portfolio import promotion_evidence_window


def snapshot(day: int, nav: float, trades: int = 0):
    return SimpleNamespace(
        as_of_date=dt.date(2026, 7, day),
        nav=nav,
        trades=[{}] * trades,
    )


def test_retroactive_replay_is_excluded_from_forward_evidence() -> None:
    rows = [
        snapshot(1, 100),
        snapshot(2, 104, 1),
        snapshot(3, 98, 1),
        snapshot(6, 102),
        snapshot(7, 99, 1),
    ]

    baseline, latest, observations, drawdown = promotion_evidence_window(
        rows,
        forward_started_on=dt.date(2026, 7, 6),
    )

    assert baseline.as_of_date == dt.date(2026, 7, 3)
    assert latest.as_of_date == dt.date(2026, 7, 7)
    assert [item.as_of_date.day for item in observations] == [6, 7]
    assert drawdown == pytest.approx((1 - 99 / 102) * 100)


def test_ordinary_forward_book_uses_inception_as_baseline() -> None:
    rows = [snapshot(1, 100), snapshot(2, 101), snapshot(3, 99)]

    baseline, latest, observations, drawdown = promotion_evidence_window(
        rows,
        forward_started_on=dt.date(2026, 7, 1),
    )

    assert baseline is rows[0]
    assert latest is rows[-1]
    assert observations == rows[1:]
    assert drawdown == pytest.approx((1 - 99 / 101) * 100)


def test_future_forward_boundary_has_zero_forward_observations() -> None:
    rows = [snapshot(1, 100), snapshot(2, 103)]

    baseline, latest, observations, drawdown = promotion_evidence_window(
        rows,
        forward_started_on=dt.date(2026, 7, 3),
    )

    assert baseline is rows[-1]
    assert latest is rows[-1]
    assert observations == []
    assert drawdown == 0
