"""Read-only registry projection for offline Atlas statistical experiments."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.institutional_research.schemas import (
    ModelCoefficientOut,
    ModelExperimentBoardOut,
    ModelExperimentOut,
    ModelHorizonOut,
    ModelSegmentedChallengerOut,
    ModelSleeveContractOut,
    ModelSleeveOut,
    ModelWindowMetricsOut,
    ResearchUniverseFoundationOut,
)
from bulls.core.models import ResearchUniverseSnapshot

_ARTIFACT_DIRECTORIES = {
    "DSE": "dse-eod-rank",
    "US": "us-eod-rank",
}
_MAX_ARTIFACT_BYTES = 8 * 1024 * 1024
_REPOSITORY_ROOT = Path(__file__).resolve().parents[5]


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def _window_metrics(value: Any) -> ModelWindowMetricsOut | None:
    if not isinstance(value, dict) or not value:
        return None
    book = value.get("top_book")
    book = book if isinstance(book, dict) else {}
    return ModelWindowMetricsOut(
        rows=int(value.get("rows") or 0),
        dates=int(value.get("dates") or 0),
        mean_daily_rank_ic=_optional_float(value.get("mean_daily_rank_ic")),
        median_daily_rank_ic=_optional_float(value.get("median_daily_rank_ic")),
        positive_ic_dates_pct=_optional_float(value.get("positive_ic_dates_pct")),
        trades=int(book.get("trades") or 0),
        invested_dates=(
            int(book["invested_dates"]) if book.get("invested_dates") is not None else None
        ),
        abstentions={
            str(key): int(count) for key, count in (book.get("abstentions") or {}).items()
        },
        mean_net_pct=_optional_float(book.get("mean_net_pct")),
        mean_stressed_pct=_optional_float(book.get("mean_stressed_pct")),
        annualized_net_pct=_optional_float(book.get("annualized_net_pct")),
        hit_rate_pct=_optional_float(book.get("hit_rate_pct")),
        sharpe=_optional_float(book.get("sharpe")),
        sharpe_standard_error=_optional_float(book.get("sharpe_standard_error")),
        sharpe_lower_95=_optional_float(book.get("sharpe_lower_95")),
        years=_optional_float(book.get("years")),
        mean_effective_positions=_optional_float(book.get("mean_effective_positions")),
        maximum_drawdown_pct=_optional_float(book.get("maximum_drawdown_pct")),
    )


def _sleeve_contract(value: Any) -> ModelSleeveContractOut:
    if not isinstance(value, dict):
        raise ValueError("model sleeve contract is malformed")
    construction = value.get("construction")
    if not isinstance(construction, dict):
        raise ValueError("model sleeve construction is malformed")
    return ModelSleeveContractOut(
        minimum_price=float(value["minimum_price"]),
        minimum_adv=float(value["minimum_adv"]),
        maximum_adv=_optional_float(value.get("maximum_adv")),
        allowed_trend_regimes=[str(item) for item in value.get("allowed_trend_regimes") or []],
        allowed_volatility_regimes=[
            str(item) for item in value.get("allowed_volatility_regimes") or []
        ],
        book_notional=float(construction["book_notional"]),
        max_positions=int(construction["max_positions"]),
        minimum_positions=int(construction["minimum_positions"]),
        max_position_weight=float(construction["max_position_weight"]),
        max_adv_participation=float(construction["max_adv_participation"]),
    )


def _segmented_challenger(value: Any) -> ModelSegmentedChallengerOut | None:
    if not isinstance(value, dict):
        return None
    sleeve_rows = value.get("sleeves")
    if not isinstance(sleeve_rows, list):
        raise ValueError("segmented challenger sleeve list is malformed")
    sleeves: list[ModelSleeveOut] = []
    for row in sleeve_rows:
        if not isinstance(row, dict):
            raise ValueError("segmented challenger sleeve is malformed")
        status = str(row.get("status") or "data_blocked")
        if status not in {"evaluated", "data_blocked"}:
            raise ValueError("segmented challenger sleeve status is invalid")
        model_results = row.get("model_results")
        baseline_results = row.get("momentum_baseline")
        model_results = model_results if isinstance(model_results, dict) else {}
        baseline_results = baseline_results if isinstance(baseline_results, dict) else {}
        sleeves.append(
            ModelSleeveOut(
                key=str(row.get("key") or "unknown"),
                label=str(row.get("label") or row.get("key") or "Unknown sleeve"),
                status=status,
                contract=_sleeve_contract(row.get("contract")),
                selected_penalty=(
                    float(row["selected_penalty"])
                    if row.get("selected_penalty") is not None
                    else None
                ),
                research_verdict=str(row.get("research_verdict") or "data_blocked"),
                blockers=[
                    str(item)
                    for item in (row.get("promotion_blockers") or row.get("blockers") or [])
                ],
                validation=_window_metrics(model_results.get("validation")),
                holdout=_window_metrics(model_results.get("holdout")),
                momentum_holdout=_window_metrics(baseline_results.get("holdout")),
            )
        )
    return ModelSegmentedChallengerOut(
        key=str(value.get("key") or "unknown"),
        version=str(value.get("version") or "unknown"),
        trial_count=int(value.get("trial_count") or 0),
        cap_segmentation_status=str(value.get("cap_segmentation_status") or "unknown"),
        methodology=str(value.get("methodology") or ""),
        sleeves=sleeves,
    )


def _parse_artifact(path: Path, *, market: str) -> ModelExperimentOut:
    """Validate and condense one immutable model artefact for browser-safe delivery."""

    if path.stat().st_size > _MAX_ARTIFACT_BYTES:
        raise ValueError("model artefact exceeds the audited size limit")
    raw = path.read_bytes()
    payload = json.loads(raw)
    manifest = payload.get("dataset_manifest")
    models = payload.get("models")
    if not isinstance(manifest, dict) or manifest.get("market") != market:
        raise ValueError("model artefact market does not match the tenant market")
    if not isinstance(models, dict) or not models:
        raise ValueError("model artefact contains no evaluated horizons")

    horizons: list[ModelHorizonOut] = []
    for key, model in sorted(models.items(), key=lambda item: int(item[0])):
        if not isinstance(model, dict):
            raise ValueError(f"model horizon {key} is malformed")
        spec = model.get("spec")
        if not isinstance(spec, dict) or spec.get("market") != market:
            raise ValueError(f"model horizon {key} crosses the tenant market boundary")
        model_results = model.get("model_results")
        baseline_results = model.get("momentum_baseline")
        model_results = model_results if isinstance(model_results, dict) else {}
        baseline_results = baseline_results if isinstance(baseline_results, dict) else {}
        coefficients = model.get("coefficients_by_absolute_weight")
        coefficient_rows = coefficients if isinstance(coefficients, list) else []
        horizons.append(
            ModelHorizonOut(
                horizon_sessions=int(spec.get("horizon") or key),
                specification_hash=str(model.get("spec_hash") or ""),
                selected_penalty=float(model.get("selected_penalty") or 0),
                research_verdict=str(model.get("research_verdict") or "unknown"),
                promotion_status=str(model.get("promotion_status") or "blocked"),
                promotion_blockers=[str(item) for item in model.get("promotion_blockers") or []],
                discovery=_window_metrics(model_results.get("discovery")),
                validation=_window_metrics(model_results.get("validation_refit_diagnostic")),
                holdout=_window_metrics(model_results.get("holdout")),
                momentum_holdout=_window_metrics(baseline_results.get("holdout")),
                top_coefficients=[
                    ModelCoefficientOut(
                        feature=str(row.get("feature") or "unknown"),
                        coefficient=float(row.get("coefficient") or 0),
                    )
                    for row in coefficient_rows[:6]
                    if isinstance(row, dict)
                ],
                segmented_challenger=_segmented_challenger(
                    model.get("segmented_challenger")
                ),
            )
        )

    generated_at = dt.datetime.fromisoformat(str(payload["generated_at"]).replace("Z", "+00:00"))
    verdicts = {horizon.research_verdict for horizon in horizons}
    status = (
        "diagnostic"
        if "promising_diagnostic_but_data_blocked" in verdicts
        else "rejected"
    )
    return ModelExperimentOut(
        artifact_schema_version=str(payload.get("artifact_schema_version") or "unknown"),
        artifact_sha256=hashlib.sha256(raw).hexdigest(),
        generated_at=generated_at,
        data_cutoff=dt.date.fromisoformat(str(manifest["benchmark_latest_date"])),
        data_scope=str(manifest.get("scope") or "unknown"),
        symbols_streamed=int(manifest.get("symbols_streamed") or 0),
        bounded_sample=manifest.get("max_symbols") is not None,
        status=status,
        limitations=[str(item) for item in manifest.get("limitations") or []],
        horizons=horizons,
    )


def _latest_experiment(root: Path, *, market: str) -> ModelExperimentOut | None:
    directory = root / _ARTIFACT_DIRECTORIES[market]
    if not directory.is_dir():
        return None
    candidates = sorted(directory.glob("*/model-evaluation.json"), reverse=True)
    for candidate in candidates:
        resolved = candidate.resolve()
        if directory.resolve() not in resolved.parents:
            continue
        try:
            return _parse_artifact(resolved, market=market)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError):
            continue
    return None


async def load_model_experiment_board(
    session: AsyncSession,
    *,
    tenant_id: str,
    market: str,
    artifact_root: Path | None = None,
) -> ModelExperimentBoardOut:
    snapshot = await session.scalar(
        select(ResearchUniverseSnapshot)
        .where(ResearchUniverseSnapshot.market == market)
        .order_by(
            ResearchUniverseSnapshot.as_of_date.desc(),
            ResearchUniverseSnapshot.generated_at.desc(),
        )
        .limit(1)
    )
    foundation = None
    if snapshot is not None:
        blockers = snapshot.quality_report.get("model_blockers", {})
        foundation = ResearchUniverseFoundationOut(
            snapshot_id=snapshot.id,
            as_of_date=snapshot.as_of_date,
            policy_key=snapshot.policy_key,
            policy_version=snapshot.policy_version,
            source_mode=snapshot.source_mode,
            model_ready=snapshot.model_ready,
            candidate_count=snapshot.candidate_count,
            eligible_count=snapshot.eligible_count,
            ineligible_count=snapshot.ineligible_count,
            data_blocked_count=snapshot.data_blocked_count,
            model_eligible_count=snapshot.model_eligible_count,
            model_blockers={str(key): int(value) for key, value in blockers.items()},
        )

    configured_root = os.getenv("BULLS_RESEARCH_ARTIFACT_ROOT")
    root = artifact_root or (
        Path(configured_root) if configured_root else _REPOSITORY_ROOT / "var/research"
    )
    experiment = _latest_experiment(root, market=market)
    return ModelExperimentBoardOut(
        tenant_id=tenant_id,
        market=market,
        generated_at=dt.datetime.now(dt.UTC),
        foundation=foundation,
        experiment=experiment,
        methodology=(
            "Offline experiments use completed bars only, next-session execution, chronological "
            "discovery/validation/holdout windows, explicit costs, and an untouched holdout. "
            "They remain separate from Agent decisions until universe history and forward evidence "
            "satisfy every promotion gate."
        ),
    )


__all__ = ["load_model_experiment_board"]
