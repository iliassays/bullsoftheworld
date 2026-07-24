"""Bind-parameter-safe bulk upserts.

Postgres refuses a statement carrying more than 32767 bind parameters. A single multi-row
``INSERT ... VALUES`` binds ``len(rows) * len(columns)`` of them, so the "one statement for every
row" pattern works fine in development and then fails *every* run once the table's row count
crosses the ceiling. It is a scale trap: nothing changes in the code, the universe just grows.

That is exactly how the US EOD chain broke on 2026-07-24 — the quote publish binds 13 columns per
symbol, so it died the moment the eligible US universe passed ~2,520 names
(``asyncpg.InterfaceError: the number of query arguments cannot exceed 32767``), taking the
downstream levels/volume/factor/portfolio steps down with it.

Callers keep their own conflict clause; this module only decides how many rows may travel in one
statement.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence

# Postgres wire-protocol limit on bind parameters per statement.
PARAMETER_CEILING = 32767


def rows_per_statement(columns: int, *, ceiling: int = PARAMETER_CEILING) -> int:
    """How many rows of ``columns`` fields fit under the bind-parameter ceiling."""

    if columns <= 0:
        return 1
    return max(1, ceiling // columns)


def parameter_safe_batches(
    rows: Sequence[dict], *, ceiling: int = PARAMETER_CEILING
) -> Iterator[Sequence[dict]]:
    """Split ``rows`` into batches that cannot exceed the bind-parameter ceiling.

    Sizing uses the widest row, because a ragged batch is bound at its widest member.
    """

    if not rows:
        return
    columns = max(len(row) for row in rows)
    size = rows_per_statement(columns, ceiling=ceiling)
    for start in range(0, len(rows), size):
        yield rows[start : start + size]
