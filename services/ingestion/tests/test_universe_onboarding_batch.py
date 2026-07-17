from __future__ import annotations

import json

import pytest

from ingestion import universe_onboarding_batch
from ingestion.universe_onboarding_batch import run_batch, selected_cohort_files


def test_batch_selection_preserves_mid_cap_first_and_applies_bound(tmp_path) -> None:
    for filename in ("mid.json", "small.json"):
        (tmp_path / filename).write_text("{}")
    index = tmp_path / "manifest-index.json"
    index.write_text(
        json.dumps(
            {
                "market": "US",
                "cohorts": [
                    {"band": "mid_cap", "file": "mid.json", "manifest_sha256": "a" * 64},
                    {"band": "small_cap", "file": "small.json", "manifest_sha256": "b" * 64},
                ],
            }
        )
    )

    assert [path.name for path, _ in selected_cohort_files(index, band=None, max_cohorts=1)] == [
        "mid.json"
    ]
    assert [
        path.name for path, _ in selected_cohort_files(index, band="small_cap", max_cohorts=1)
    ] == ["small.json"]


def test_batch_selection_rejects_path_traversal(tmp_path) -> None:
    index = tmp_path / "manifest-index.json"
    index.write_text(
        json.dumps(
            {
                "market": "US",
                "cohorts": [{"band": "mid_cap", "file": "../escape.json"}],
            }
        )
    )

    with pytest.raises(ValueError, match="escapes"):
        selected_cohort_files(index, band=None, max_cohorts=1)


@pytest.mark.asyncio
async def test_batch_bound_applies_to_first_unfinished_cohort(monkeypatch, tmp_path) -> None:
    files = [
        (tmp_path / name, "") for name in ("small-001.json", "small-002.json", "small-003.json")
    ]
    manifests = {
        path: type(
            "Manifest",
            (),
            {
                "market": "US",
                "name": path.stem,
                "manifest_sha256": path.stem,
            },
        )()
        for path, _ in files
    }
    completed = {manifests[files[0][0]].manifest_sha256}
    attempted: list[str] = []

    monkeypatch.setattr(
        universe_onboarding_batch,
        "selected_cohort_files",
        lambda *args, **kwargs: files,
    )
    monkeypatch.setattr(
        universe_onboarding_batch,
        "load_cohort",
        lambda path, market: manifests[path],
    )

    async def already_completed(manifest):
        return manifest.manifest_sha256 in completed

    async def latest_failed(_manifest):
        return None

    async def onboard(manifest, *, resume_id, fetch, promote, refresh_security_master):
        assert resume_id is None
        assert refresh_security_master
        attempted.append(manifest.name)
        return {"run_id": manifest.name}

    monkeypatch.setattr(universe_onboarding_batch, "_already_completed", already_completed)
    monkeypatch.setattr(universe_onboarding_batch, "_latest_failed_run", latest_failed)
    monkeypatch.setattr(universe_onboarding_batch, "run_onboarding", onboard)

    result = await run_batch(tmp_path / "manifest-index.json", band="small_cap", max_cohorts=1)

    assert attempted == ["small-002"]
    assert result["requested_cohorts"] == 1
    assert [row["file"] for row in result["skipped"]] == ["small-001.json"]
    assert [row["file"] for row in result["completed"]] == ["small-002.json"]


@pytest.mark.asyncio
async def test_batch_resumes_latest_failed_run(monkeypatch, tmp_path) -> None:
    path = tmp_path / "small-001.json"
    manifest = type(
        "Manifest",
        (),
        {"market": "US", "name": "small-001", "manifest_sha256": "a" * 64},
    )()
    resumed = object()

    monkeypatch.setattr(
        universe_onboarding_batch,
        "selected_cohort_files",
        lambda *args, **kwargs: [(path, "")],
    )
    monkeypatch.setattr(universe_onboarding_batch, "load_cohort", lambda *_args: manifest)

    async def not_completed(_manifest):
        return False

    async def latest_failed(_manifest):
        return resumed

    async def onboard(_manifest, *, resume_id, fetch, promote, refresh_security_master):
        assert resume_id is resumed
        assert refresh_security_master
        return {"run_id": "resumed"}

    monkeypatch.setattr(universe_onboarding_batch, "_already_completed", not_completed)
    monkeypatch.setattr(universe_onboarding_batch, "_latest_failed_run", latest_failed)
    monkeypatch.setattr(universe_onboarding_batch, "run_onboarding", onboard)

    result = await run_batch(tmp_path / "manifest-index.json", band="small_cap")

    assert result["completed"][0]["run_id"] == "resumed"
