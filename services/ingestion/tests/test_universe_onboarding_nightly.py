"""Nightly cohort staging: one cohort per run, band order respected, protected windows honored."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest

from ingestion.universe_onboarding_nightly import (
    BAND_ORDER,
    in_protected_window,
    latest_manifest_index,
    stage_next_cohort,
)


def _utc(hour: int, minute: int) -> dt.datetime:
    return dt.datetime(2026, 7, 17, hour, minute, tzinfo=dt.UTC)


def test_protected_windows_cover_session_and_eod() -> None:
    assert in_protected_window(_utc(4, 0))  # DSE intraday polling
    assert in_protected_window(_utc(8, 30))  # session tail
    assert in_protected_window(_utc(13, 20))  # EOD chain
    assert not in_protected_window(_utc(2, 10))  # nightly slot
    assert not in_protected_window(_utc(10, 0))
    assert not in_protected_window(_utc(23, 0))


def test_risky_bands_are_not_scheduled() -> None:
    assert "nano_cap" not in BAND_ORDER
    assert "ultra_nano_cap" not in BAND_ORDER
    assert BAND_ORDER[0] == "small_cap"


@pytest.mark.asyncio
async def test_stages_first_incomplete_band_and_stops() -> None:
    calls: list[str] = []

    async def runner(index_path, *, band, max_cohorts, fetch):
        calls.append(band)
        assert max_cohorts == 1 and fetch is True
        if band == "small_cap":
            return {"completed": [], "skipped": [{"file": "s1"}], "failed": []}
        return {"completed": [{"file": f"{band}-001"}], "skipped": [], "failed": []}

    result = await stage_next_cohort(Path("index.json"), runner=runner)

    assert result["outcome"] == "staged"
    assert result["band"] == "micro_cap"
    assert calls == ["small_cap", "micro_cap"]  # never reaches mid_cap


@pytest.mark.asyncio
async def test_reports_backlog_complete_when_every_band_is_done() -> None:
    async def runner(index_path, *, band, max_cohorts, fetch):
        return {"completed": [], "skipped": [{"file": f"{band}-001"}], "failed": []}

    result = await stage_next_cohort(Path("index.json"), runner=runner)

    assert result["outcome"] == "backlog_complete"
    assert result["skipped"] == len(BAND_ORDER)


@pytest.mark.asyncio
async def test_failed_cohort_surfaces_instead_of_continuing() -> None:
    async def runner(index_path, *, band, max_cohorts, fetch):
        return {"completed": [], "skipped": [], "failed": [{"file": "s1", "error": "boom"}]}

    result = await stage_next_cohort(Path("index.json"), runner=runner)

    assert result["outcome"] == "failed"
    assert result["band"] == "small_cap"


def test_latest_manifest_index_picks_newest_snapshot(tmp_path: Path) -> None:
    for day in ("2026-07-10", "2026-07-16"):
        directory = tmp_path / day
        directory.mkdir()
        (directory / "manifest-index.json").write_text(json.dumps({"market": "US"}))
    (tmp_path / "2026-07-20").mkdir()  # snapshot directory without an index is ignored

    chosen = latest_manifest_index(tmp_path)

    assert chosen is not None
    assert chosen.parent.name == "2026-07-16"


def test_latest_manifest_index_handles_empty_directory(tmp_path: Path) -> None:
    assert latest_manifest_index(tmp_path) is None
