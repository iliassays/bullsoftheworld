from __future__ import annotations

import datetime as dt

from api.institutional_research.squeeze import (
    LIMITATIONS,
    _blocked_families,
    _build_entry,
    _is_listable_archive_row,
    _state_markers,
)
from bulls.core.models import DailyBar, SqueezeDailyState


def test_us_blocked_families_are_explicit_with_missing_datasets() -> None:
    blocked = {family.family: family for family in _blocked_families("US")}

    assert set(blocked) == {
        "us_short_squeeze",
        "us_gamma_squeeze",
        "us_float_liquidity_squeeze",
    }
    for family in blocked.values():
        assert family.blocked_reason
        assert family.missing_datasets
        assert family.entries == []

    # Gamma and float squeezes are still missing their core datasets outright.
    assert blocked["us_gamma_squeeze"].status == "data_blocked"
    assert blocked["us_float_liquidity_squeeze"].status == "data_blocked"
    # Short squeeze now HAS authoritative positioning (FINRA consolidated short interest), so
    # reporting it as data-blocked would misstate the reason: what it lacks is an evaluator,
    # plus float/borrow/FTD for full confidence. Execution stays blocked either way.
    assert blocked["us_short_squeeze"].status == "not_implemented"
    assert not any(
        "short interest" in item.lower() and "days-to-cover" in item.lower()
        for item in blocked["us_short_squeeze"].missing_datasets
    )


def test_dse_has_no_short_squeeze_family_at_all() -> None:
    assert _blocked_families("DSE") == []


def test_limitations_enforce_the_language_rules() -> None:
    blob = " ".join(LIMITATIONS).lower()
    assert "not short interest" in blob
    assert "days-to-cover" in blob
    assert "never live flow" in blob
    assert "nothing here is a prediction" in blob
    assert "not a price forecast" in blob


def test_archived_entry_preserves_its_evidence_mode() -> None:
    archive_date = dt.date(2026, 7, 24)
    row = SqueezeDailyState(
        market="US",
        code="TEST",
        family="compression_breakout",
        as_of_date=archive_date,
        state="forming",
        evidence_mode="reconstructed",
        previous_state="watch",
        reason="The base remains compressed.",
        first_discovered_on=archive_date,
        evidence={},
        methodology_version="squeeze-monitor-v2",
    )

    entry = _build_entry(
        row,
        market="US",
        company="Test Company",
        code_bars=[],
        selected_date=archive_date,
    )

    assert entry.evidence_mode == "reconstructed"


def test_discovery_session_is_not_reported_as_post_discovery_performance() -> None:
    discovery_date = dt.date(2026, 7, 20)
    row = SqueezeDailyState(
        market="DSE",
        code="TEST",
        family="compression_breakout",
        as_of_date=discovery_date,
        state="watch",
        evidence_mode="reconstructed",
        previous_state="none",
        reason="The setup entered watch.",
        first_discovered_on=discovery_date,
        evidence={},
        methodology_version="squeeze-monitor-v3",
    )
    # This candle moved materially before the close. None of that path was observable after the
    # close-based discovery, so it must not become follow-through or MFE/MAE.
    bar = DailyBar(
        market="DSE",
        code="TEST",
        date=discovery_date,
        open=90,
        high=120,
        low=80,
        close=100,
        volume=1_000,
        source="test",
    )

    entry = _build_entry(
        row,
        market="DSE",
        company="Test Company",
        code_bars=[bar],
        selected_date=discovery_date,
    )

    assert entry.sessions_since_discovery == 0
    assert entry.return_since_discovery_pct is None
    assert entry.max_favorable_pct is None
    assert entry.max_adverse_pct is None
    assert entry.peak_traded_pct is None
    assert entry.trough_traded_pct is None


def test_entry_separates_discovery_from_next_observable_confirmation_return() -> None:
    discovery_date = dt.date(2026, 7, 20)
    confirmation_date = dt.date(2026, 7, 21)
    observable_date = dt.date(2026, 7, 22)
    selected_date = dt.date(2026, 7, 23)
    selected = SqueezeDailyState(
        market="DSE",
        code="TEST",
        family="compression_breakout",
        as_of_date=selected_date,
        state="confirmed",
        evidence_mode="forward",
        previous_state="confirmed",
        reason="The setup remains confirmed.",
        first_discovered_on=discovery_date,
        evidence={},
        methodology_version="squeeze-monitor-v3",
    )
    history = [
        SqueezeDailyState(
            market="DSE",
            code="TEST",
            family="compression_breakout",
            as_of_date=discovery_date,
            state="forming",
            evidence_mode="forward",
            previous_state="none",
            reason="The base is forming.",
            first_discovered_on=discovery_date,
            evidence={},
            methodology_version="squeeze-monitor-v3",
        ),
        SqueezeDailyState(
            market="DSE",
            code="TEST",
            family="compression_breakout",
            as_of_date=confirmation_date,
            state="confirmed",
            evidence_mode="forward",
            previous_state="forming",
            reason="The breakout confirmed.",
            first_discovered_on=discovery_date,
            evidence={},
            methodology_version="squeeze-monitor-v3",
        ),
        selected,
    ]
    bars = [
        DailyBar(
            market="DSE",
            code="TEST",
            date=discovery_date,
            open=99,
            high=101,
            low=98,
            close=100,
            volume=1_000,
            source="test",
        ),
        DailyBar(
            market="DSE",
            code="TEST",
            date=confirmation_date,
            open=100,
            high=106,
            low=99,
            close=105,
            volume=2_000,
            source="test",
        ),
        DailyBar(
            market="DSE",
            code="TEST",
            date=observable_date,
            open=106,
            high=109,
            low=104,
            close=108,
            volume=1_500,
            source="test",
        ),
        DailyBar(
            market="DSE",
            code="TEST",
            date=selected_date,
            open=108,
            high=111,
            low=107,
            close=110,
            volume=1_200,
            source="test",
        ),
    ]

    entry = _build_entry(
        selected,
        market="DSE",
        company="Test Company",
        code_bars=bars,
        selected_date=selected_date,
        episode_rows=history,
    )

    assert entry.return_since_discovery_pct == 10.0
    assert entry.sessions_since_discovery == 3
    # The discovery candle's 101/98 range is excluded. These are excursions observable only after
    # the setup was known at the discovery close.
    assert entry.peak_traded_pct == 11.0
    assert entry.trough_traded_pct == -1.0
    assert entry.first_confirmed_on == confirmation_date
    assert entry.confirmation_price == 105.0
    assert entry.move_to_confirmation_pct == 5.0
    assert not entry.is_new_confirmation
    assert entry.next_observable_on == observable_date
    assert entry.next_observable_price == 106.0
    assert entry.return_since_next_observable_pct == 3.774
    assert "research inventory only" in entry.paper_book_status.lower()
    assert "agent decisions" in entry.paper_book_status.lower()
    assert "reconstructed rows cannot create targets" in entry.paper_book_status.lower()

    confirmation_entry = _build_entry(
        history[1],
        market="DSE",
        company="Test Company",
        code_bars=bars[:2],
        selected_date=confirmation_date,
        episode_rows=history[:2],
    )
    assert confirmation_entry.is_new_confirmation
    assert not confirmation_entry.is_new


def test_state_markers_keep_repeated_discoveries_in_separate_numbered_episodes() -> None:
    first_discovery = dt.date(2026, 6, 1)
    second_discovery = dt.date(2026, 7, 20)
    rows = [
        SqueezeDailyState(
            market="DSE",
            code="TEST",
            family="compression_breakout",
            as_of_date=first_discovery,
            state="forming",
            evidence_mode="forward",
            previous_state="none",
            reason="First base discovered.",
            first_discovered_on=first_discovery,
            evidence={},
            methodology_version="squeeze-monitor-v3",
        ),
        SqueezeDailyState(
            market="DSE",
            code="TEST",
            family="compression_breakout",
            as_of_date=dt.date(2026, 6, 3),
            state="confirmed",
            evidence_mode="forward",
            previous_state="forming",
            reason="First breakout confirmed.",
            first_discovered_on=first_discovery,
            evidence={},
            methodology_version="squeeze-monitor-v3",
        ),
        SqueezeDailyState(
            market="DSE",
            code="TEST",
            family="compression_breakout",
            as_of_date=second_discovery,
            state="forming",
            evidence_mode="forward",
            previous_state="none",
            reason="Second base discovered.",
            first_discovered_on=second_discovery,
            evidence={},
            methodology_version="squeeze-monitor-v3",
        ),
        SqueezeDailyState(
            market="DSE",
            code="TEST",
            family="compression_breakout",
            as_of_date=dt.date(2026, 7, 22),
            state="confirmed",
            evidence_mode="forward",
            previous_state="forming",
            reason="Second breakout confirmed.",
            first_discovered_on=second_discovery,
            evidence={},
            methodology_version="squeeze-monitor-v3",
        ),
    ]

    markers = _state_markers(
        rows,
        episode_dates=[first_discovery, second_discovery],
        current_episode=second_discovery,
    )

    assert [marker.episode_number for marker in markers] == [1, 1, 2, 2]
    assert [marker.is_current_episode for marker in markers] == [
        False,
        False,
        True,
        True,
    ]


def test_state_markers_ignore_legacy_standalone_terminal_rows() -> None:
    terminal_date = dt.date(2026, 6, 1)
    active_date = dt.date(2026, 7, 20)
    rows = [
        SqueezeDailyState(
            market="DSE",
            code="TEST",
            family="compression_breakout",
            as_of_date=terminal_date,
            state="exhausted",
            evidence_mode="reconstructed",
            previous_state="none",
            reason="Extended without an active setup.",
            first_discovered_on=terminal_date,
            evidence={},
            methodology_version="squeeze-monitor-v3",
        ),
        SqueezeDailyState(
            market="DSE",
            code="TEST",
            family="compression_breakout",
            as_of_date=active_date,
            state="forming",
            evidence_mode="reconstructed",
            previous_state="none",
            reason="A real setup begins.",
            first_discovered_on=active_date,
            evidence={},
            methodology_version="squeeze-monitor-v3",
        ),
    ]

    markers = _state_markers(
        rows,
        episode_dates=[active_date],
        current_episode=active_date,
    )

    assert [(marker.date, marker.episode_number) for marker in markers] == [(active_date, 1)]


def test_monitor_hides_legacy_terminal_rows_that_never_had_an_active_episode() -> None:
    archive_date = dt.date(2026, 7, 23)

    def row(state: str, previous_state: str, discovered_on: dt.date) -> SqueezeDailyState:
        return SqueezeDailyState(
            market="US",
            code="TEST",
            family="compression_breakout",
            as_of_date=archive_date,
            state=state,
            evidence_mode="forward",
            previous_state=previous_state,
            reason="Archived state.",
            first_discovered_on=discovered_on,
            evidence={},
            methodology_version="squeeze-monitor-v1",
        )

    assert not _is_listable_archive_row(row("none", "watch", archive_date))
    assert not _is_listable_archive_row(row("exhausted", "none", archive_date))
    assert not _is_listable_archive_row(row("failed", "none", archive_date))
    assert _is_listable_archive_row(row("watch", "none", archive_date))
    assert _is_listable_archive_row(
        row("exhausted", "confirmed", archive_date - dt.timedelta(days=4))
    )
