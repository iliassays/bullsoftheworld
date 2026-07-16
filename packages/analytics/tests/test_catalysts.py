"""Catalyst derivation: official DSE dates stay confirmed, US cadence stays an inferred window."""

from __future__ import annotations

import datetime as dt

from bulls.analytics.catalysts import (
    CatalystDraft,
    dse_events_from_announcement,
    us_report_window_from_filings,
)

_PUBLISHED = dt.date(2026, 7, 10)


def _dse(details, category="corporate_action"):
    return dse_events_from_announcement(
        market="DSE",
        code="GP",
        published_at=_PUBLISHED,
        category=category,
        headline="Record date and AGM notice",
        details=details,
        source_ref="announcement:abc123",
    )


def test_dse_projection_emits_confirmed_events_with_official_confidence() -> None:
    events = _dse(
        {
            "record_date": "2026-07-20",
            "agm_date": "2026-08-05",
            "meeting_date": "2026-07-15",
        }
    )

    by_type = {event.event_type: event for event in events}
    assert set(by_type) == {"record_date", "agm", "board_meeting"}
    assert all(event.timing_kind == "confirmed" for event in events)
    assert all(event.confidence == "official_confirmed" for event in events)
    assert by_type["record_date"].confirmed_date == dt.date(2026, 7, 20)
    assert by_type["agm"].known_at.date() == _PUBLISHED


def test_dse_projection_skips_past_dates_and_unparseable_values() -> None:
    events = _dse({"record_date": "2026-07-01", "agm_date": "not a date", "meeting_date": None})

    assert events == []


def test_dse_spot_window_is_a_window_event() -> None:
    [event] = _dse({"spot_from": "2026-07-14", "spot_to": "2026-07-16"})

    assert event.event_type == "spot_window"
    assert event.timing_kind == "window"
    assert (event.window_start, event.window_end) == (dt.date(2026, 7, 14), dt.date(2026, 7, 16))


def test_dse_projection_handles_missing_details() -> None:
    assert _dse(None) == []


def _quarterly(dates: list[str]) -> list[tuple[str, dt.date, str]]:
    return [("10-Q", dt.date.fromisoformat(day), f"acc-{i}") for i, day in enumerate(dates)]


def test_us_cadence_infers_forward_window_never_confirmed() -> None:
    draft = us_report_window_from_filings(
        market="US",
        code="ABCD",
        periodic_filings=_quarterly(["2025-08-08", "2025-11-07", "2026-02-06", "2026-05-08"]),
        as_of=dt.date(2026, 7, 16),
    )

    assert draft is not None
    assert draft.timing_kind == "window"
    assert draft.confidence == "inferred_cadence"
    assert draft.confirmed_date is None
    # Median gap ~91 days from 2026-05-08 → centred near 2026-08-07, ±12 days.
    assert draft.window_start <= dt.date(2026, 8, 7) <= draft.window_end
    assert draft.window_end >= dt.date(2026, 7, 16)
    assert draft.details["cadence_days"] == 91


def test_us_cadence_rolls_window_forward_past_stale_history() -> None:
    draft = us_report_window_from_filings(
        market="US",
        code="ABCD",
        periodic_filings=_quarterly(["2025-02-07", "2025-05-09", "2025-08-08"]),
        as_of=dt.date(2026, 7, 16),
    )

    assert draft is not None
    assert draft.window_end >= dt.date(2026, 7, 16)


def test_us_cadence_requires_enough_history() -> None:
    draft = us_report_window_from_filings(
        market="US",
        code="ABCD",
        periodic_filings=_quarterly(["2026-02-06", "2026-05-08"]),
        as_of=dt.date(2026, 7, 16),
    )

    assert draft is None


def test_us_cadence_ignores_non_periodic_forms() -> None:
    filings = [
        ("8-K", dt.date(2026, 1, 5), "a"),
        ("8-K", dt.date(2026, 3, 5), "b"),
        *_quarterly(["2026-02-06", "2026-05-08"]),
    ]

    assert (
        us_report_window_from_filings(
            market="US", code="ABCD", periodic_filings=filings, as_of=dt.date(2026, 7, 16)
        )
        is None
    )


def test_dedupe_key_is_stable_and_tenant_scoped() -> None:
    [event] = _dse({"record_date": "2026-07-20"})

    assert event.dedupe_key("bullsofdhaka") == event.dedupe_key("bullsofdhaka")
    assert event.dedupe_key("bullsofdhaka") != event.dedupe_key("bullsofwallst")
    assert len(event.dedupe_key("bullsofdhaka")) == 64


def test_draft_rejects_inconsistent_timing() -> None:
    try:
        CatalystDraft(
            market="US",
            code="X",
            event_type="agm",
            title="x",
            timing_kind="confirmed",
            window_start=dt.date(2026, 1, 1),
            window_end=dt.date(2026, 1, 2),
            confirmed_date=dt.date(2026, 1, 1),
            confidence="official_confirmed",
            source_type="t",
            source_ref="r",
            known_at=dt.datetime(2026, 1, 1, tzinfo=dt.UTC),
        )
    except ValueError:
        return
    raise AssertionError("confirmed event with a window must be rejected")
