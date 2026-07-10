from __future__ import annotations

import json
from pathlib import Path


def test_retrieval_eval_set_covers_both_languages_and_multiple_tickers() -> None:
    path = Path(__file__).resolve().parents[1] / "evals" / "retrieval_cases.json"
    cases = json.loads(path.read_text())

    assert len(cases) >= 6
    assert {case["code"] for case in cases} >= {"BSC", "SEAPEARL"}
    assert any(any("\u0980" <= char <= "\u09ff" for char in case["query"]) for case in cases)
    assert all(case["expected_source_types"] for case in cases)
    assert all(1 <= case["max_rank"] <= 3 for case in cases)
