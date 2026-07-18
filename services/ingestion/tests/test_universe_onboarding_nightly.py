"""Nightly cohort staging: uses the whole safe window, band order respected, protected windows honored."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest

from ingestion.universe_onboarding_nightly import (
    BAND_ORDER,
    in_protected_window,
    latest_manifest_index,
    run_nightly,
    runtime_budget_seconds,
    stage_available_cohorts,
)


def _utc(hour: int, minute: int) -> dt.datetime:
    return dt.datetime(2026, 7, 17, hour, minute, tzinfo=dt.UTC)


def _weekend_utc(hour: int, minute: int) -> dt.datetime:
    return dt.datetime(2026, 7, 18, hour, minute, tzinfo=dt.UTC)


def test_protected_windows_cover_session_and_eod() -> None:
    assert in_protected_window(_utc(4, 0))  # DSE intraday polling
    assert in_protected_window(_utc(8, 30))  # session tail
    assert in_protected_window(_utc(13, 20))  # EOD chain
    assert not in_protected_window(_utc(2, 10))  # nightly slot
    assert not in_protected_window(_utc(10, 0))
    assert not in_protected_window(_utc(23, 0))


def test_runtime_budget_stops_before_the_next_protected_window() -> None:
    assert runtime_budget_seconds(_utc(0, 45)) == 2 * 60 * 60
    assert runtime_budget_seconds(_utc(2, 10)) == 55 * 60
    assert runtime_budget_seconds(_utc(12, 30)) == 5 * 60


def test_weekend_uses_full_bounded_runtime_without_market_windows() -> None:
    assert not in_protected_window(_weekend_utc(4, 0))
    assert not in_protected_window(_weekend_utc(13, 20))
    assert runtime_budget_seconds(_weekend_utc(4, 0)) == 2 * 60 * 60
    assert runtime_budget_seconds(_weekend_utc(23, 0)) == 2 * 60 * 60


def test_private_staging_covers_every_research_band_in_priority_order() -> None:
    assert BAND_ORDER == (
        "mid_cap",
        "small_cap",
        "micro_cap",
        "nano_cap",
        "ultra_nano_cap",
    )


def _band_runner(responses: dict[str, list[dict]]):
    """Return a fake run_batch that pops one canned response per call, per band."""
    calls: dict[str, int] = {band: 0 for band in responses}

    async def runner(index_path, *, band, max_cohorts, fetch):
        assert max_cohorts == 1 and fetch is True
        index = calls[band]
        calls[band] += 1
        return responses[band][index]

    return runner, calls


@pytest.mark.asyncio
async def test_stages_every_cohort_in_a_band_before_advancing_to_the_next() -> None:
    """Repeated calls within one band keep completing cohorts, not just the first."""
    runner, calls = _band_runner(
        {
            "small_cap": [
                {"completed": [{"file": "small-1"}], "skipped": [], "failed": []},
                {"completed": [{"file": "small-2"}], "skipped": [], "failed": []},
                {
                    "completed": [],
                    "skipped": [{"file": "small-1"}, {"file": "small-2"}],
                    "failed": [],
                },
            ],
            "micro_cap": [
                {"completed": [{"file": "micro-1"}], "skipped": [], "failed": []},
                {"completed": [], "skipped": [{"file": "micro-1"}], "failed": []},
            ],
            "mid_cap": [
                {"completed": [], "skipped": [], "failed": []},
            ],
        }
    )

    result = await stage_available_cohorts(
        Path("index.json"),
        bands=("small_cap", "micro_cap", "mid_cap"),
        runner=runner,
    )

    assert result["outcome"] == "backlog_complete"
    assert [c["file"] for c in result["progress"]] == ["small-1", "micro-1", "small-2"]
    assert calls == {"small_cap": 3, "micro_cap": 2, "mid_cap": 1}


@pytest.mark.asyncio
async def test_reports_backlog_complete_when_every_band_is_already_done() -> None:
    async def runner(index_path, *, band, max_cohorts, fetch):
        return {"completed": [], "skipped": [{"file": f"{band}-001"}], "failed": []}

    result = await stage_available_cohorts(Path("index.json"), runner=runner)

    assert result["outcome"] == "backlog_complete"
    assert result["progress"] == []
    assert result["skipped"] == len(BAND_ORDER)


@pytest.mark.asyncio
async def test_failed_cohort_blocks_only_its_band_and_keeps_prior_progress() -> None:
    runner, _ = _band_runner(
        {
            "small_cap": [
                {"completed": [{"file": "small-1"}], "skipped": [], "failed": []},
                {"completed": [], "skipped": [], "failed": [{"file": "small-2", "error": "boom"}]},
            ],
        }
    )

    result = await stage_available_cohorts(Path("index.json"), bands=("small_cap",), runner=runner)

    assert result["outcome"] == "partial_failure"
    assert result["failures"][0]["band"] == "small_cap"
    assert [c["file"] for c in result["progress"]] == ["small-1"]


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


@pytest.mark.asyncio
async def test_run_nightly_treats_deadline_with_progress_as_a_normal_stop(
    monkeypatch, tmp_path: Path
) -> None:
    """Running out of the safe window after staging cohorts is expected, not an incident."""
    index_path = tmp_path / "manifest-index.json"
    index_path.write_text("{}")
    monkeypatch.setattr(
        "ingestion.universe_onboarding_nightly.in_protected_window", lambda now: False
    )
    monkeypatch.setattr(
        "ingestion.universe_onboarding_nightly.runtime_budget_seconds", lambda now: 3600
    )

    async def fake_stage(index_path, *, progress, **kwargs):
        progress.append({"file": "small-1"})
        raise TimeoutError

    monkeypatch.setattr("ingestion.universe_onboarding_nightly.stage_available_cohorts", fake_stage)
    alerted = []

    async def fake_alert(subject, body):
        alerted.append(subject)

    monkeypatch.setattr("ingestion.universe_onboarding_nightly._send_failure_alert", fake_alert)

    exit_code = await run_nightly(index_path)

    assert exit_code == 0
    assert alerted == []  # no alert - real progress was made before the deadline


@pytest.mark.asyncio
async def test_run_nightly_alerts_when_deadline_hits_with_zero_progress(
    monkeypatch, tmp_path: Path
) -> None:
    index_path = tmp_path / "manifest-index.json"
    index_path.write_text("{}")
    monkeypatch.setattr(
        "ingestion.universe_onboarding_nightly.in_protected_window", lambda now: False
    )
    monkeypatch.setattr(
        "ingestion.universe_onboarding_nightly.runtime_budget_seconds", lambda now: 3600
    )

    async def fake_stage(index_path, *, progress, **kwargs):
        raise TimeoutError

    monkeypatch.setattr("ingestion.universe_onboarding_nightly.stage_available_cohorts", fake_stage)
    alerted = []

    async def fake_alert(subject, body):
        alerted.append(subject)

    monkeypatch.setattr("ingestion.universe_onboarding_nightly._send_failure_alert", fake_alert)

    exit_code = await run_nightly(index_path)

    assert exit_code == 1
    assert alerted == ["US cohort staging reached its market-safety deadline"]
