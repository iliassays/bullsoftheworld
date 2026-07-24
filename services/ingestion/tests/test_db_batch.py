from __future__ import annotations

from ingestion.db_batch import (
    PARAMETER_CEILING,
    parameter_safe_batches,
    rows_per_statement,
)


def test_rows_per_statement_stays_under_the_ceiling() -> None:
    # The US quote publish binds 13 columns per symbol; this is the case that broke prod.
    assert rows_per_statement(13) == 2520
    assert PARAMETER_CEILING >= 2520 * 13
    assert PARAMETER_CEILING < 2521 * 13


def test_rows_per_statement_never_returns_zero() -> None:
    # A pathologically wide row still has to move one at a time rather than stalling.
    assert rows_per_statement(PARAMETER_CEILING * 2) == 1
    assert rows_per_statement(0) == 1


def test_every_batch_respects_the_ceiling_at_us_universe_scale() -> None:
    rows = [dict.fromkeys(range(13), 1) for _ in range(11_079)]

    batches = list(parameter_safe_batches(rows))

    assert sum(len(batch) for batch in batches) == 11_079
    assert all(len(batch) * 13 <= PARAMETER_CEILING for batch in batches)
    # Unbatched this was 144k parameters in one statement.
    assert len(batches) > 1


def test_ragged_rows_are_sized_by_the_widest_member() -> None:
    rows = [{"a": 1}, dict.fromkeys("abcdefghij", 1)]

    batches = list(parameter_safe_batches(rows, ceiling=10))

    assert all(len(batch) * 10 <= 10 for batch in batches)


def test_empty_input_yields_nothing() -> None:
    assert list(parameter_safe_batches([])) == []


def test_small_input_stays_in_one_statement() -> None:
    rows = [dict.fromkeys(range(13), 1) for _ in range(396)]  # DSE universe

    assert len(list(parameter_safe_batches(rows))) == 1
