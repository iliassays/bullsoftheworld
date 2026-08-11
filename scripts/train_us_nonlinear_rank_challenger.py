"""Evaluate the preregistered 20-session U.S. nonlinear rank challenger.

The command reuses immutable Parquet shards from ``train_us_eod_rank_model.py``. It performs no
database write and has no Atlas target, paper-book or order integration.

Usage::

    uv run --group research python scripts/train_us_nonlinear_rank_challenger.py \
        --source-run var/research/us-eod-rank/20260804T103717Z
"""

# ruff: noqa: E402

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

import polars as pl

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from research.modeling.cross_sectional_rank import (
    CrossSectionalSpec,
    attach_scores,
    evaluate_ranking,
    finite_dict,
    fit_ridge,
    rank_features,
    temporal_window,
)
from research.modeling.nonlinear_rank import (
    LightGBMRankSpec,
    attach_rank_scores,
    feature_importance,
    fit_lambdarank,
)
from research.modeling.segmented_challenger import (
    DEFAULT_LIQUIDITY_SLEEVES,
    filter_liquidity_sleeve,
)

ARTIFACT_SCHEMA_VERSION = "atlas-nonlinear-rank-artifact-v1"


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-run", type=Path, required=True)
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("var/research/us-nonlinear-rank"),
    )
    return parser.parse_args(argv)


def _load_panel(source_run: Path) -> pl.DataFrame:
    paths = sorted((source_run / "horizon-20").glob("part-*.parquet"))
    if not paths:
        raise RuntimeError(f"No 20-session dataset shards found under {source_run}")
    return pl.scan_parquet(paths).collect(engine="streaming")


def _metric_score(result: dict[str, Any]) -> tuple[float, float]:
    book = result.get("top_book") or {}
    return (
        float(result.get("mean_daily_rank_ic") or float("-inf")),
        float(book.get("mean_stressed_pct") or float("-inf")),
    )


def _evaluate(frame: pl.DataFrame, *, score_column: str) -> dict[str, Any]:
    return evaluate_ranking(
        frame,
        score_column=score_column,
        horizon=20,
        positions=10,
    )


def _ridge_comparator(
    discovery: pl.DataFrame,
    validation: pl.DataFrame,
    reused_diagnostic: pl.DataFrame,
    *,
    spec: CrossSectionalSpec,
) -> dict[str, Any]:
    trials: list[dict[str, Any]] = []
    for penalty in spec.ridge_penalties:
        selection_model = fit_ridge(discovery, penalty=penalty)
        evaluation = _evaluate(
            attach_scores(validation, selection_model),
            score_column="model_score",
        )
        trials.append({"penalty": penalty, "validation": evaluation})
    selected = max(trials, key=lambda trial: _metric_score(trial["validation"]))
    penalty = float(selected["penalty"])
    selection_model = fit_ridge(discovery, penalty=penalty)
    forward_model = fit_ridge(
        pl.concat((discovery, validation), how="vertical_relaxed"),
        penalty=penalty,
    )
    return {
        "selected_penalty": penalty,
        "penalty_trials": trials,
        "validation": _evaluate(
            attach_scores(validation, selection_model),
            score_column="model_score",
        ),
        "reused_historical_diagnostic": _evaluate(
            attach_scores(reused_diagnostic, forward_model),
            score_column="model_score",
        ),
    }


def _comparison_stressed(result: dict[str, Any]) -> float:
    value = (result.get("top_book") or {}).get("mean_stressed_pct")
    return float(value) if value is not None else float("-inf")


def run_experiment(source_run: Path, output_root: Path) -> Path:
    source_run = source_run.resolve()
    manifest_path = source_run / "dataset-manifest.json"
    manifest_bytes = manifest_path.read_bytes()
    source_manifest = json.loads(manifest_bytes)
    raw_panel = _load_panel(source_run)

    sleeve = next(item for item in DEFAULT_LIQUIDITY_SLEEVES if item.key == "deep_liquidity")
    eligible = filter_liquidity_sleeve(raw_panel, sleeve)
    panel = rank_features(eligible)
    linear_spec = CrossSectionalSpec(horizon=20)
    windows = {
        name: temporal_window(panel, linear_spec, name)
        for name in ("discovery", "validation", "holdout")
    }
    dates = {name: frame["date"].n_unique() for name, frame in windows.items()}
    if min(dates.values()) < 10:
        raise RuntimeError(f"Insufficient dates for frozen temporal windows: {dates}")

    nonlinear_spec = LightGBMRankSpec()
    fit = fit_lambdarank(
        windows["discovery"],
        windows["validation"],
        spec=nonlinear_spec,
    )
    nonlinear_results = {
        "discovery_in_sample": _evaluate(
            attach_rank_scores(
                windows["discovery"],
                fit.selection_model,
                num_iteration=fit.best_iteration,
            ),
            score_column="nonlinear_rank_score",
        ),
        "validation": _evaluate(
            attach_rank_scores(
                windows["validation"],
                fit.selection_model,
                num_iteration=fit.best_iteration,
            ),
            score_column="nonlinear_rank_score",
        ),
        "reused_historical_diagnostic": _evaluate(
            attach_rank_scores(
                windows["holdout"],
                fit.forward_model,
                num_iteration=fit.best_iteration,
            ),
            score_column="nonlinear_rank_score",
        ),
    }
    ridge = _ridge_comparator(
        windows["discovery"],
        windows["validation"],
        windows["holdout"],
        spec=linear_spec,
    )
    momentum = {
        name: _evaluate(frame, score_column="x_residual_return_60")
        for name, frame in (
            ("validation", windows["validation"]),
            ("reused_historical_diagnostic", windows["holdout"]),
        )
    }
    validation = nonlinear_results["validation"]
    validation_book = validation.get("top_book") or {}
    criteria = {
        "positive_median_rank_ic": (validation.get("median_daily_rank_ic") or 0) > 0,
        "positive_doubled_cost_top_ten":
            (validation_book.get("mean_stressed_pct") or 0) > 0,
        "at_least_20_independent_dates": (validation_book.get("dates") or 0) >= 20,
        "beats_ridge_after_doubled_costs": (
            _comparison_stressed(validation) > _comparison_stressed(ridge["validation"])
        ),
        "beats_momentum_after_doubled_costs": (
            _comparison_stressed(validation) > _comparison_stressed(momentum["validation"])
        ),
    }
    candidate_for_forward = all(criteria.values())

    stamp = dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")
    output_dir = (output_root / stamp).resolve()
    output_dir.mkdir(parents=True, exist_ok=False)
    fit.selection_model.save_model(str(output_dir / "selection-model.txt"))
    fit.forward_model.save_model(str(output_dir / "forward-model.txt"))
    registration_cutoff = panel["date"].max()
    result = finite_dict(
        {
            "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
            "generated_at": dt.datetime.now(dt.UTC).isoformat(),
            "source_run": str(source_run),
            "source_manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
            "source_manifest": source_manifest,
            "data_scope": "current_survivors_diagnostic_upper_bound",
            "registration_cutoff": registration_cutoff.isoformat(),
            "specification": asdict(nonlinear_spec),
            "specification_hash": nonlinear_spec.spec_hash(),
            "trial_count": nonlinear_spec.trial_count,
            "sleeve": sleeve.as_dict(),
            "rows": {name: frame.height for name, frame in windows.items()},
            "dates": dates,
            "best_iteration": fit.best_iteration,
            "feature_importance": feature_importance(fit.forward_model),
            "nonlinear_results": nonlinear_results,
            "ridge_comparator": ridge,
            "momentum_comparator": momentum,
            "historical_forward_admission_criteria": criteria,
            "research_verdict": (
                "candidate_for_fresh_forward_collection"
                if candidate_for_forward
                else "rejected_on_genuine_validation"
            ),
            "promotion_status": "blocked",
            "promotion_blockers": [
                "historical security membership is current-survivor-only",
                "the post-2024 window is reused research evidence, not a pristine holdout",
                "no unchanged fresh-forward collection has matured",
            ],
            "forward_contract": {
                "starts_after": registration_cutoff.isoformat(),
                "minimum_market_sessions": 120,
                "minimum_matured_signal_dates": 60,
                "orders_enabled": False,
            },
        }
    )
    artifact = output_dir / "evaluation.json"
    artifact.write_text(json.dumps(result, indent=2, sort_keys=True, default=str))
    return artifact


def main(argv: list[str]) -> None:
    args = _parse_args(argv)
    artifact = run_experiment(args.source_run, args.output_root)
    print(json.dumps({"artifact": str(artifact)}, indent=2))


if __name__ == "__main__":
    main(sys.argv[1:])
