import datetime as dt

from ingestion.squeeze_backfill import _forward_protected


def test_forward_protected_starts_at_first_live_observation() -> None:
    cutoffs = {("DBH", "compression_breakout"): dt.date(2026, 7, 24)}

    assert not _forward_protected(
        cutoffs,
        code="DBH",
        family="compression_breakout",
        as_of=dt.date(2026, 7, 23),
    )
    assert _forward_protected(
        cutoffs,
        code="DBH",
        family="compression_breakout",
        as_of=dt.date(2026, 7, 24),
    )
    assert _forward_protected(
        cutoffs,
        code="DBH",
        family="compression_breakout",
        as_of=dt.date(2026, 7, 25),
    )


def test_forward_protection_is_scoped_to_ticker_and_family() -> None:
    cutoffs = {("DBH", "compression_breakout"): dt.date(2026, 7, 24)}

    assert not _forward_protected(
        cutoffs,
        code="DBH",
        family="failed_breakdown_reversal",
        as_of=dt.date(2026, 7, 25),
    )
    assert not _forward_protected(
        cutoffs,
        code="BRACBANK",
        family="compression_breakout",
        as_of=dt.date(2026, 7, 25),
    )
