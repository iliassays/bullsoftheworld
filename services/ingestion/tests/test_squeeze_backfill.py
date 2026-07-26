import datetime as dt

from sqlalchemy.dialects import postgresql

from ingestion.squeeze_backfill import _forward_protected, _replacement_delete


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


def test_replacement_delete_can_only_remove_reconstructed_rows_in_window() -> None:
    statement = _replacement_delete(
        "US",
        dt.date(2026, 5, 1),
        dt.date(2026, 7, 24),
    )
    compiled = statement.compile(dialect=postgresql.dialect())
    sql = str(compiled)

    assert "squeeze_daily_states.market =" in sql
    assert "squeeze_daily_states.as_of_date >=" in sql
    assert "squeeze_daily_states.as_of_date <=" in sql
    assert "squeeze_daily_states.evidence_mode =" in sql
    assert set(compiled.params.values()) == {
        "US",
        dt.date(2026, 5, 1),
        dt.date(2026, 7, 24),
        "reconstructed",
    }
