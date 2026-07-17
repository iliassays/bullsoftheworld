from __future__ import annotations

import datetime as dt

import pytest

from ingestion import full_universe_nightly


def test_latest_catalog_index_uses_newest_snapshot(tmp_path) -> None:
    older = tmp_path / "2026-07-16" / "manifest-index.json"
    newer = tmp_path / "2026-07-17" / "manifest-index.json"
    older.parent.mkdir()
    newer.parent.mkdir()
    older.write_text("{}")
    newer.write_text("{}")

    assert full_universe_nightly.latest_catalog_index(tmp_path) == newer


@pytest.mark.asyncio
async def test_catalog_runner_stops_after_terminal_completion(monkeypatch, tmp_path) -> None:
    index = tmp_path / "manifest-index.json"
    index.write_text("{}")
    calls = 0

    async def completed(*_args, **kwargs):
        nonlocal calls
        calls += 1
        assert kwargs["refresh_security_master"] is False
        return {"failed": [], "requested_cohorts": 0}

    monkeypatch.setattr(full_universe_nightly, "runtime_budget_seconds", lambda _now: 7200)
    result = await full_universe_nightly.advance_catalog(
        index,
        now=dt.datetime(2026, 7, 17, 10, tzinfo=dt.UTC),
        run_batch_fn=completed,
    )

    assert result["status"] == "complete"
    assert calls == 1
