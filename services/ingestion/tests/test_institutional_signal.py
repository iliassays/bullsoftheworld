from __future__ import annotations

import datetime as dt

from ingestion.signals.institutional import detect, render


def test_13f_signal_requires_share_change_and_manager_breadth_confirmation() -> None:
    signal = detect(
        report_date=dt.date(2026, 3, 31),
        public_by=dt.date(2026, 5, 15),
        managers_count=20,
        net_change_pct=24.0,
        new_positions=4,
        increased_positions=8,
        reduced_positions=2,
        exited_positions=1,
        unchanged_positions=5,
        watched_managers=("Citadel Advisors LLC",),
    )

    assert signal is not None
    assert signal.direction == "increased"
    assert signal.evidence == "confirmed"
    text = render(signal, "ABCD")
    assert "quarter ended 2026-03-31" in text
    assert "delayed quarter-end long holdings" in text
    assert "not conviction" in text


def test_13f_signal_rejects_large_share_change_when_manager_breadth_disagrees() -> None:
    assert (
        detect(
            report_date=dt.date(2026, 3, 31),
            public_by=dt.date(2026, 5, 15),
            managers_count=20,
            net_change_pct=20.0,
            new_positions=1,
            increased_positions=1,
            reduced_positions=8,
            exited_positions=2,
            unchanged_positions=3,
        )
        is None
    )
