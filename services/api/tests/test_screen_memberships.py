"""Market-board membership freshness is factual, scoped and non-retroactive."""

from __future__ import annotations

import datetime as dt

from api.routers.screener import ScreenItem, ScreenOut
from api.screen_membership import (
    advance_screen_memberships,
    apply_screen_membership_badges,
    screen_membership_key,
)


def _screen(*codes: str, key: str = "institutional_buying") -> ScreenOut:
    return ScreenOut(
        key=key,
        title="Board",
        description="Board description",
        value_label="pp",
        items=[ScreenItem(code=code, last_close=100, value=1) for code in codes],
    )


def test_first_observation_is_a_baseline_not_a_false_new_claim() -> None:
    now = dt.datetime(2026, 7, 15, 10, tzinfo=dt.UTC)
    board = _screen("A", "B")

    state = advance_screen_memberships([board], None, now)

    assert [item.new_since for item in board.items] == [None, None]
    assert state["screens"] == {"institutional_buying": {"A": None, "B": None}}


def test_only_a_genuine_entry_after_the_baseline_is_marked_new() -> None:
    first = dt.datetime(2026, 7, 15, 10, tzinfo=dt.UTC)
    previous = advance_screen_memberships([_screen("A")], None, first)
    board = _screen("A", "B")

    state = advance_screen_memberships([board], previous, first + dt.timedelta(hours=1))

    assert board.items[0].new_since is None
    assert board.items[1].new_since == "2026-07-15T11:00:00+00:00"
    assert state["screens"]["institutional_buying"]["B"] == board.items[1].new_since


def test_entry_badge_expires_but_reentry_gets_a_new_timestamp() -> None:
    first = dt.datetime(2026, 7, 15, 10, tzinfo=dt.UTC)
    baseline = advance_screen_memberships([_screen("A")], None, first)
    entered = advance_screen_memberships(
        [_screen("A", "B")], baseline, first + dt.timedelta(hours=1)
    )
    old_board = _screen("A", "B")
    apply_screen_membership_badges([old_board], entered, first + dt.timedelta(hours=26))
    assert old_board.items[1].new_since is None

    left = advance_screen_memberships([_screen("A")], entered, first + dt.timedelta(hours=27))
    returned = _screen("A", "B")
    advance_screen_memberships([returned], left, first + dt.timedelta(hours=28))
    assert returned.items[1].new_since == "2026-07-16T14:00:00+00:00"


def test_membership_storage_is_tenant_market_and_universe_isolated() -> None:
    assert screen_membership_key("bullsofdhaka", "DSE", None) != screen_membership_key(
        "bullsofwallst", "US", None
    )
    assert screen_membership_key("bullsofdhaka", "DSE", "small") != screen_membership_key(
        "bullsofdhaka", "DSE", "large"
    )
