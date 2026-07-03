"""Alert fan-out unit tests — pure logic, no database."""

from __future__ import annotations

from ingestion.alerts import (
    NOTE_ALERT_TITLES,
    note_alert_kind,
    note_alert_title,
    should_trigger,
)
from ingestion.signals.levels import _TEMPLATES as LEVELS_TEMPLATES
from ingestion.signals.ownership import _TEMPLATES as OWNERSHIP_TEMPLATES


def test_every_levels_event_has_a_title() -> None:
    """Each event the levels agent can fire must render a real headline, not the fallback."""
    for event_type in LEVELS_TEMPLATES:
        assert event_type in NOTE_ALERT_TITLES, f"missing alert title for {event_type}"


def test_every_ownership_event_has_a_title_and_kind() -> None:
    for event_type in OWNERSHIP_TEMPLATES:
        assert event_type in NOTE_ALERT_TITLES, f"missing alert title for {event_type}"
        assert note_alert_kind(event_type) == "ownership"


# Every event type any desk can publish with a cashtag. A new agent event MUST be added here
# and to NOTE_ALERT_TITLES — otherwise watchers get the generic "New data note" headline.
ALL_AGENT_EVENTS = {
    # volume desk
    "unusual_volume": "signal",
    # factor desks
    "momentum_strong": "signal",
    "quality_value": "signal",
    "smart_money_both": "signal",
    "quiet_accumulation": "signal",
    "rel_strength": "signal",
    "circuit_up": "signal",
    "circuit_down": "signal",
    "new_52w_high": "signal",  # shared by levels + the factor breakout
    # news desks
    "news_earnings": "earnings",
    "news_dividend": "earnings",
    "news_rating": "signal",
}


def test_every_agent_event_has_a_specific_title_and_kind() -> None:
    for event_type, kind in ALL_AGENT_EVENTS.items():
        assert event_type in NOTE_ALERT_TITLES, f"missing alert title for {event_type}"
        assert note_alert_kind(event_type) == kind, event_type
        t = note_alert_title(event_type, "GP")
        assert "GP" in t["en"] and "GP" in t["bn"]


def test_title_renders_code_in_both_languages() -> None:
    t = note_alert_title("new_52w_high", "GP")
    assert t["en"] == "$GP hit a new 52-week high"
    assert "GP" in t["bn"]
    assert "{code}" not in t["en"] and "{code}" not in t["bn"]


def test_unknown_event_falls_back_gracefully() -> None:
    t = note_alert_title("some_future_event", "ROBI")
    assert "ROBI" in t["en"] and "ROBI" in t["bn"]


def test_ownership_events_get_ownership_kind() -> None:
    assert note_alert_kind("sponsor_change") == "ownership"
    assert note_alert_kind("sponsor_falling_streak") == "ownership"
    assert note_alert_kind("new_52w_high") == "signal"


def test_should_trigger_above_and_below() -> None:
    assert should_trigger("above", 100.0, 100.0)  # touching counts
    assert should_trigger("above", 100.0, 101.5)
    assert not should_trigger("above", 100.0, 99.9)
    assert should_trigger("below", 50.0, 49.0)
    assert should_trigger("below", 50.0, 50.0)
    assert not should_trigger("below", 50.0, 51.0)
