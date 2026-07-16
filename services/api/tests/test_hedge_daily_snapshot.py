from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from hedge_daily import TRACK_RECORD, scan_from_snapshot  # noqa: E402


def _candidate(code: str, score: int, fires: list[tuple[str, int]]) -> dict:
    return {
        "code": code,
        "price": 100.0,
        "stop": 90.0,
        "target": 125.0,
        "pe": 10.0,
        "roe": 15,
        "below_high": -50,
        "score": score,
        "sector": "Test",
        "fires": [
            {"date": fire_date, "sessions_ago": sessions_ago}
            for fire_date, sessions_ago in fires
        ],
    }


def test_scan_snapshot_applies_requested_session_window_without_recomputing() -> None:
    snapshot = {
        "as_of": "2026-07-15",
        "max_sessions": 63,
        "track_record": TRACK_RECORD,
        "candidates": [
            _candidate("OLD", 90, [("2026-07-01", 10)]),
            _candidate("RECENT", 80, [("2026-07-08", 6), ("2026-07-14", 1)]),
            _candidate("WATCH", 70, []),
        ],
    }

    short = scan_from_snapshot(snapshot, days=5)
    assert [row["code"] for row in short["fired"]] == ["RECENT"]
    assert short["fired"][0]["fired_on"] == "2026-07-14"
    assert [row["code"] for row in short["watch"]] == ["OLD", "WATCH"]

    long = scan_from_snapshot(snapshot, days=10)
    assert [row["code"] for row in long["fired"]] == ["RECENT"]
    assert long["fired"][0]["fired_on"] == "2026-07-08"


def test_scan_snapshot_clamps_window_and_preserves_conviction_order() -> None:
    snapshot = {
        "as_of": "2026-07-15",
        "max_sessions": 3,
        "candidates": [
            _candidate("LOW", 50, [("2026-07-15", 0)]),
            _candidate("HIGH", 90, [("2026-07-14", 1)]),
        ],
    }

    result = scan_from_snapshot(snapshot, days=999)

    assert result["days"] == 3
    assert result["ready"] is True
    assert [row["code"] for row in result["fired"]] == ["HIGH", "LOW"]
    assert all("fires" not in row for row in result["fired"])
