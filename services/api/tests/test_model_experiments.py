from __future__ import annotations

import json
from pathlib import Path

import pytest

from api.institutional_research.model_experiments import _latest_experiment, _parse_artifact


def _artifact(market: str = "US") -> dict:
    window = {
        "rows": 1000,
        "dates": 20,
        "mean_daily_rank_ic": 0.04,
        "median_daily_rank_ic": 0.03,
        "positive_ic_dates_pct": 60,
        "top_book": {
            "trades": 200,
            "mean_net_pct": -0.1,
            "mean_stressed_pct": -0.2,
            "annualized_net_pct": -5,
            "hit_rate_pct": 45,
            "sharpe": -0.4,
            "maximum_drawdown_pct": -12,
        },
    }
    return {
        "artifact_schema_version": "atlas-cross-sectional-model-artifact-v1",
        "generated_at": "2026-08-04T10:00:00+00:00",
        "dataset_manifest": {
            "market": market,
            "benchmark_latest_date": "2026-08-03",
            "scope": "current_survivors_diagnostic_upper_bound",
            "symbols_streamed": 5470,
            "max_symbols": None,
            "limitations": ["Survivorship selection bias."],
        },
        "models": {
            "5": {
                "spec": {"market": market, "horizon": 5},
                "spec_hash": "a" * 64,
                "selected_penalty": 0.1,
                "research_verdict": "rejected_or_requires_new_preregistered_hypothesis",
                "promotion_status": "blocked",
                "promotion_blockers": ["forward evidence missing"],
                "model_results": {
                    "discovery": window,
                    "validation_refit_diagnostic": window,
                    "holdout": window,
                },
                "momentum_baseline": {"holdout": window},
                "coefficients_by_absolute_weight": [
                    {"feature": "log_adv_20", "coefficient": 0.02}
                ],
                "segmented_challenger": {
                    "key": "us_eod_segmented_rank_challenger",
                    "version": "v1",
                    "trial_count": 15,
                    "cap_segmentation_status": "blocked_missing_point_in_time_market_cap",
                    "methodology": "Frozen liquidity sleeves and constrained construction.",
                    "sleeves": [
                        {
                            "key": "deep_liquidity",
                            "label": "Deep liquidity",
                            "status": "evaluated",
                            "contract": {
                                "minimum_price": 5,
                                "minimum_adv": 50_000_000,
                                "maximum_adv": None,
                                "minimum_cross_section": 50,
                                "allowed_trend_regimes": ["risk_on", "transition"],
                                "allowed_volatility_regimes": ["normal"],
                                "construction": {
                                    "book_notional": 5_000_000,
                                    "max_positions": 10,
                                    "minimum_positions": 8,
                                    "max_position_weight": 0.15,
                                    "max_adv_participation": 0.01,
                                    "minimum_predicted_net_excess": 0,
                                },
                            },
                            "selected_penalty": 0.01,
                            "research_verdict": "rejected_or_requires_new_preregistered_hypothesis",
                            "promotion_status": "blocked",
                            "promotion_blockers": ["forward evidence missing"],
                            "model_results": {"validation": window, "holdout": window},
                            "momentum_baseline": {"holdout": window},
                        }
                    ],
                },
            }
        },
    }


def test_parse_artifact_returns_compact_audited_projection(tmp_path: Path) -> None:
    path = tmp_path / "model-evaluation.json"
    path.write_text(json.dumps(_artifact()))

    result = _parse_artifact(path, market="US")

    assert result.status == "rejected"
    assert result.symbols_streamed == 5470
    assert result.data_cutoff.isoformat() == "2026-08-03"
    assert result.horizons[0].holdout is not None
    assert result.horizons[0].holdout.mean_stressed_pct == -0.2
    assert result.horizons[0].top_coefficients[0].feature == "log_adv_20"
    challenger = result.horizons[0].segmented_challenger
    assert challenger is not None
    assert challenger.trial_count == 15
    assert challenger.sleeves[0].contract.book_notional == 5_000_000
    assert challenger.sleeves[0].holdout is not None
    assert challenger.sleeves[0].holdout.mean_stressed_pct == -0.2
    assert len(result.artifact_sha256) == 64


def test_parse_artifact_rejects_cross_market_payload(tmp_path: Path) -> None:
    path = tmp_path / "model-evaluation.json"
    path.write_text(json.dumps(_artifact("DSE")))

    with pytest.raises(ValueError, match="tenant market"):
        _parse_artifact(path, market="US")


def test_latest_experiment_skips_malformed_newest_artifact(tmp_path: Path) -> None:
    root = tmp_path / "us-eod-rank"
    valid = root / "20260803T000000Z"
    invalid = root / "20260804T000000Z"
    valid.mkdir(parents=True)
    invalid.mkdir(parents=True)
    (valid / "model-evaluation.json").write_text(json.dumps(_artifact()))
    (invalid / "model-evaluation.json").write_text("not-json")

    result = _latest_experiment(tmp_path, market="US")

    assert result is not None
    assert result.generated_at.isoformat() == "2026-08-04T10:00:00+00:00"
