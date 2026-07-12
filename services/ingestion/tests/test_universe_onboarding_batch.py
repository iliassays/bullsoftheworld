from __future__ import annotations

import json

import pytest

from ingestion.universe_onboarding_batch import selected_cohort_files


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
    assert [path.name for path, _ in selected_cohort_files(index, band="small_cap", max_cohorts=1)] == [
        "small.json"
    ]


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
