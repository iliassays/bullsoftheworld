"""Tests for the EDGAR historical backfill runner."""

from __future__ import annotations

import datetime as dt

import pytest

from ingestion.edgar_backfill import _dates, run_backfill


def test_dates_is_inclusive_and_chronological() -> None:
    days = list(_dates(dt.date(2026, 7, 1), dt.date(2026, 7, 4)))
    assert days == [dt.date(2026, 7, d) for d in (1, 2, 3, 4)]


def test_dates_rejects_end_before_start() -> None:
    with pytest.raises(ValueError):
        list(_dates(dt.date(2026, 7, 4), dt.date(2026, 7, 1)))


async def test_run_backfill_sums_counts_and_survives_a_bad_day(monkeypatch) -> None:
    calls: list[dt.date] = []

    async def fake_collect_day(day, *, store):
        calls.append(day)
        if day == dt.date(2026, 7, 2):
            raise RuntimeError("simulated SEC outage")
        return {"index_entries": 1, "captured": 1, "parsed": 1, "failed": 0, "skipped": 0}

    monkeypatch.setattr("ingestion.edgar_backfill.collect_day", fake_collect_day)
    monkeypatch.setattr("ingestion.edgar_backfill.object_store", lambda: object())

    totals = await run_backfill(dt.date(2026, 7, 1), dt.date(2026, 7, 3))

    # All three days are attempted even though day 2 raises...
    assert calls == [dt.date(2026, 7, 1), dt.date(2026, 7, 2), dt.date(2026, 7, 3)]
    # ...but only the two successful days count toward the totals.
    assert totals == {"days": 2, "index_entries": 2, "captured": 2, "parsed": 2, "failed": 0, "skipped": 0}
