from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path
from types import SimpleNamespace

SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import hedge_daily  # noqa: E402
from hedge_app import _render, render_sizing  # noqa: E402
from hedge_archive import content_hash  # noqa: E402
from hedge_daily import (  # noqa: E402
    TRACK_RECORD,
    _current_setup_rows,
    classify_monitor_changes,
    scan_from_snapshot,
)


def _row(code: str) -> dict:
    return {"code": code}


def test_monitor_changes_distinguish_added_continued_and_removed() -> None:
    previous = {
        "new_signals": [_row("OLD_SIGNAL")],
        "active_signals": [_row("STILL_ACTIVE")],
        "watchlist": [_row("OLD_WATCH")],
    }

    changes = classify_monitor_changes(
        new_signals=[_row("NEW_SIGNAL")],
        active_signals=[_row("OLD_SIGNAL"), _row("STILL_ACTIVE")],
        watchlist=[_row("NEW_WATCH")],
        previous=previous,
    )

    assert changes == {
        "added": ["NEW_SIGNAL", "NEW_WATCH"],
        "continued": ["OLD_SIGNAL", "STILL_ACTIVE"],
        "removed": ["OLD_WATCH"],
        "has_prior_session": True,
    }


def test_scan_snapshot_exposes_only_this_sessions_new_signals() -> None:
    snapshot = {
        "schema_version": 1,
        "as_of": "2026-07-15",
        "track_record": TRACK_RECORD,
        "new_signals": [{"code": "NEW", "score": 91}],
        "active_signals": [{"code": "OLDER", "signal_date": "2026-07-01"}],
        "watchlist": [{"code": "WATCH", "score": 70}],
        "changes": {"added": ["NEW"], "continued": ["OLDER"], "removed": []},
    }

    result = scan_from_snapshot(snapshot)

    assert [row["code"] for row in result["fired"]] == ["NEW"]
    assert [row["code"] for row in result["active"]] == ["OLDER"]
    assert [row["code"] for row in result["watch"]] == ["WATCH"]
    assert result["ready"] is True


def test_daily_publication_hash_is_canonical_and_tamper_evident() -> None:
    first = {"as_of": "2026-07-15", "new_signals": [{"code": "BSC", "score": 80}]}
    reordered = {"new_signals": [{"score": 80, "code": "BSC"}], "as_of": "2026-07-15"}
    changed = {"as_of": "2026-07-15", "new_signals": [{"code": "BSC", "score": 81}]}

    assert content_hash(first) == content_hash(reordered)
    assert content_hash(first) != content_hash(changed)
    assert len(content_hash(first)) == 64


def test_current_setup_excludes_a_ticker_without_a_bar_for_the_publication_session(
    monkeypatch,
) -> None:
    latest = dt.date(2026, 7, 15)

    def bars(code: str, end: dt.date) -> list[SimpleNamespace]:
        return [
            SimpleNamespace(
                code=code,
                date=end - dt.timedelta(days=64 - index),
                close=40.0,
                high=41.0,
                low=39.0,
                volume=10_000,
            )
            for index in range(65)
        ]

    fresh = bars("FRESH", latest)
    stale = bars("STALE", latest - dt.timedelta(days=1))
    monkeypatch.setattr(
        hedge_daily,
        "_prep",
        lambda rows: (
            [40.0] * len(rows),
            [41.0] * len(rows),
            [],
            [],
            [],
            [],
            [100.0] * len(rows),
            [30.0] * len(rows),
        ),
    )
    monkeypatch.setattr(hedge_daily, "_qualifies", lambda *_args: (10.0, 15.0))

    as_of, setups = _current_setup_rows(
        {"FRESH": fresh, "STALE": stale},
        fin={},
        div={},
        profs={},
    )

    assert as_of == latest
    assert set(setups) == {"FRESH"}


def test_monitor_render_separates_signals_watchlist_and_paper_account() -> None:
    payload = {
        "as_of": "2026-07-15",
        "track_record": TRACK_RECORD,
        "new_signals": [],
        "active_signals": [],
        "watchlist": [],
        "changes": {"added": [], "continued": [], "removed": [], "has_prior_session": False},
    }
    publication = SimpleNamespace(
        as_of_date=dt.date(2026, 7, 15),
        content_hash="a" * 64,
        computed_at=dt.datetime(2026, 7, 15, 14, 20, tzinfo=dt.UTC),
    )

    html = _render(
        scan_from_snapshot(payload),
        archive=[publication],
        selected_date="2026-07-15",
        evidence_hash=publication.content_hash,
        computed_at=publication.computed_at,
        paper=None,
    )

    assert "Quality Reversal Monitor" in html
    assert "No new Quality Reversal signal" in html
    assert "setup waiting for breakout" in html
    assert "Forward-only account" not in html  # account has not been provisioned yet
    assert "No historical fills will be invented" in html


def test_sizing_empty_session_does_not_claim_slots_are_full() -> None:
    html = render_sizing(
        {
            "as_of": "2026-07-15",
            "fired": [],
            "watch": [],
            "active": [],
            "changes": {},
            "track_record": TRACK_RECORD,
            "ready": True,
        },
        capital=200_000,
        risk=1.0,
        held=0,
    )

    assert "No new signal was confirmed" in html
    assert "No free slots" not in html
