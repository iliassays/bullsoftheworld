"""Train Atlas's research-only U.S. EOD cross-sectional diagnostic.

This command streams production bars by symbol and writes compact, sampled Parquet shards on the
same server.  It never copies the full database, writes to production tables, creates a target, or
changes a strategy state.

The current U.S. security master is used to restrict the panel to active common stocks and ADRs.
Because complete listing/delisting history begins only in July 2026, every result is explicitly a
survivor-only diagnostic upper bound and is blocked from promotion regardless of performance.

Usage::

    nice -n 10 uv run python scripts/train_us_eod_rank_model.py \
        --output-root var/research/us-eod-rank
"""

# ruff: noqa: E402

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

import polars as pl
from sqlalchemy import select, text

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from research.modeling.cross_sectional_rank import (
    FEATURE_COLUMNS,
    CrossSectionalSpec,
    attach_scores,
    build_benchmark_calendar,
    build_symbol_observations,
    evaluate_ranking,
    finite_dict,
    fit_ridge,
    rank_features,
    temporal_window,
)

from bulls.core.db import dispose_engine, get_sessionmaker
from bulls.core.models import DailyBar, SecurityMaster

ARTIFACT_SCHEMA_VERSION = "atlas-cross-sectional-model-artifact-v1"
DEFAULT_HORIZONS = (5, 20)
SHARD_SYMBOLS = 200
MINIMUM_CROSS_SECTION = 100


def _parse_horizons(value: str) -> tuple[int, ...]:
    horizons = tuple(sorted({int(item.strip()) for item in value.split(",") if item.strip()}))
    if not horizons or any(horizon not in {5, 20, 60} for horizon in horizons):
        raise argparse.ArgumentTypeError("horizons must be a comma-separated subset of 5,20,60")
    return horizons


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train the research-only U.S. EOD rank model")
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("var/research/us-eod-rank"),
    )
    parser.add_argument("--horizons", type=_parse_horizons, default=DEFAULT_HORIZONS)
    parser.add_argument(
        "--reuse-run",
        type=Path,
        help="reuse an existing run directory's immutable Parquet datasets",
    )
    parser.add_argument(
        "--max-symbols",
        type=int,
        help="bounded smoke run only; such an artefact can never be treated as a full diagnostic",
    )
    return parser.parse_args(argv)


async def _load_benchmark(horizons: tuple[int, ...]) -> pl.DataFrame:
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        rows = (
            await session.execute(
                select(
                    DailyBar.date,
                    DailyBar.open,
                    DailyBar.high,
                    DailyBar.low,
                    DailyBar.close,
                    DailyBar.adjusted_close,
                )
                .where(DailyBar.market == "US", DailyBar.code == "SPY")
                .order_by(DailyBar.date)
            )
        ).all()
    if not rows:
        raise RuntimeError("SPY benchmark history is missing")
    return build_benchmark_calendar(
        pl.DataFrame(
            {
                "date": [row.date for row in rows],
                "open": [float(row.open) for row in rows],
                "high": [float(row.high) for row in rows],
                "low": [float(row.low) for row in rows],
                "close": [float(row.close) for row in rows],
                "adjusted_close": [
                    float(row.adjusted_close) if row.adjusted_close is not None else None
                    for row in rows
                ],
            }
        ),
        horizons=horizons,
    )


def _frame_from_rows(rows: list[Any]) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "code": [row.code for row in rows],
            "date": [row.date for row in rows],
            "open": [float(row.open) for row in rows],
            "high": [float(row.high) for row in rows],
            "low": [float(row.low) for row in rows],
            "close": [float(row.close) for row in rows],
            "volume": [int(row.volume or 0) for row in rows],
            "adjusted_close": [
                float(row.adjusted_close) if row.adjusted_close is not None else None
                for row in rows
            ],
        }
    )


async def _stream_histories(max_symbols: int | None = None):
    """Yield one active common-stock/ADR history at a time from a read-only cursor."""

    sessionmaker = get_sessionmaker()
    statement = (
        select(
            DailyBar.code,
            DailyBar.date,
            DailyBar.open,
            DailyBar.high,
            DailyBar.low,
            DailyBar.close,
            DailyBar.volume,
            DailyBar.adjusted_close,
        )
        .join(
            SecurityMaster,
            (SecurityMaster.market == DailyBar.market)
            & (SecurityMaster.symbol == DailyBar.code),
        )
        .where(
            DailyBar.market == "US",
            SecurityMaster.market == "US",
            SecurityMaster.is_active.is_(True),
            SecurityMaster.is_product_eligible.is_(True),
            SecurityMaster.instrument_type.in_(("common_stock", "adr")),
        )
        .order_by(DailyBar.code, DailyBar.date)
        .execution_options(yield_per=10_000, stream_results=True)
    )
    async with sessionmaker() as session:
        await session.execute(text("SET TRANSACTION READ ONLY"))
        await session.execute(text("SET LOCAL statement_timeout = '45min'"))
        result = await session.stream(statement)
        current_code: str | None = None
        current_rows: list[Any] = []
        emitted = 0
        async for row in result:
            if current_code is not None and row.code != current_code:
                yield _frame_from_rows(current_rows)
                emitted += 1
                if max_symbols is not None and emitted >= max_symbols:
                    return
                current_rows = []
            current_code = row.code
            current_rows.append(row)
        if current_rows and (max_symbols is None or emitted < max_symbols):
            yield _frame_from_rows(current_rows)


def _write_shard(frames: list[pl.DataFrame], path: Path) -> int:
    usable = [frame for frame in frames if not frame.is_empty()]
    if not usable:
        return 0
    combined = pl.concat(usable, how="vertical_relaxed", rechunk=True)
    combined.write_parquet(path, compression="zstd", statistics=True)
    return combined.height


async def build_datasets(
    run_dir: Path,
    *,
    horizons: tuple[int, ...],
    max_symbols: int | None,
) -> dict[str, Any]:
    """Stream histories once and build one non-overlapping dataset per horizon."""

    benchmark = await _load_benchmark(horizons)
    specs = {horizon: CrossSectionalSpec(horizon=horizon) for horizon in horizons}
    buffers: dict[int, list[pl.DataFrame]] = {horizon: [] for horizon in horizons}
    shard_numbers = {horizon: 0 for horizon in horizons}
    observation_counts = {horizon: 0 for horizon in horizons}
    symbols = 0

    for horizon in horizons:
        (run_dir / f"horizon-{horizon}").mkdir(parents=True, exist_ok=False)

    async for bars in _stream_histories(max_symbols=max_symbols):
        symbols += 1
        for horizon, spec in specs.items():
            observations = build_symbol_observations(bars, benchmark, spec)
            if not observations.is_empty():
                buffers[horizon].append(observations)
        if symbols % SHARD_SYMBOLS == 0:
            for horizon in horizons:
                shard = run_dir / f"horizon-{horizon}" / f"part-{shard_numbers[horizon]:05d}.parquet"
                observation_counts[horizon] += _write_shard(buffers[horizon], shard)
                buffers[horizon].clear()
                shard_numbers[horizon] += 1
            print(f"dataset progress: {symbols} symbols", flush=True)

    for horizon in horizons:
        if buffers[horizon]:
            shard = run_dir / f"horizon-{horizon}" / f"part-{shard_numbers[horizon]:05d}.parquet"
            observation_counts[horizon] += _write_shard(buffers[horizon], shard)

    metadata = {
        "created_at": dt.datetime.now(dt.UTC).isoformat(),
        "market": "US",
        "source": "production daily_bars + current security_master",
        "scope": "current_survivors_diagnostic_upper_bound",
        "symbols_streamed": symbols,
        "max_symbols": max_symbols,
        "observation_counts": {str(key): value for key, value in observation_counts.items()},
        "benchmark_first_date": benchmark["date"].min().isoformat(),
        "benchmark_latest_date": benchmark["date"].max().isoformat(),
        "limitations": [
            "Historical listing and delisting reconstruction is unavailable before July 2026.",
            "The current active security master therefore creates survivorship selection bias.",
            "Positive results are upper-bound diagnostics; negative results remain useful rejections.",
            "No model output is connected to Atlas targets, orders, or paper positions.",
        ],
    }
    (run_dir / "dataset-manifest.json").write_text(json.dumps(metadata, indent=2))
    return metadata


def _load_ranked_panel(run_dir: Path, horizon: int) -> pl.DataFrame:
    paths = sorted((run_dir / f"horizon-{horizon}").glob("part-*.parquet"))
    if not paths:
        raise RuntimeError(f"No dataset shards found for horizon {horizon}")
    frame = pl.scan_parquet(paths).collect(engine="streaming")
    frame = frame.filter(pl.len().over("date") >= MINIMUM_CROSS_SECTION)
    return rank_features(frame)


def _trial_score(result: dict[str, Any]) -> tuple[float, float]:
    top_book = result.get("top_book") or {}
    stressed = top_book.get("mean_stressed_pct")
    rank_ic = result.get("mean_daily_rank_ic")
    return (
        float(stressed) if stressed is not None else float("-inf"),
        float(rank_ic) if rank_ic is not None else float("-inf"),
    )


def train_horizon(run_dir: Path, spec: CrossSectionalSpec) -> dict[str, Any]:
    """Tune on validation only, then inspect the model-specific holdout once."""

    panel = _load_ranked_panel(run_dir, spec.horizon)
    discovery = temporal_window(panel, spec, "discovery")
    validation = temporal_window(panel, spec, "validation")
    holdout = temporal_window(panel, spec, "holdout")
    if min(discovery.height, validation.height, holdout.height) == 0:
        raise RuntimeError("At least one chronological model window is empty")

    trials: list[dict[str, Any]] = []
    for penalty in spec.ridge_penalties:
        model = fit_ridge(discovery, penalty=penalty)
        result = evaluate_ranking(
            attach_scores(validation, model),
            score_column="model_score",
            horizon=spec.horizon,
            positions=spec.positions_per_rebalance,
        )
        trials.append({"penalty": penalty, "validation": result})
    selected_trial = max(trials, key=lambda trial: _trial_score(trial["validation"]))
    selected_penalty = float(selected_trial["penalty"])

    pre_holdout = pl.concat((discovery, validation), how="vertical_relaxed")
    model = fit_ridge(pre_holdout, penalty=selected_penalty)
    scored_discovery = attach_scores(discovery, model)
    scored_validation = attach_scores(validation, model)
    scored_holdout = attach_scores(holdout, model)
    baseline_column = "x_residual_return_60"

    windows = {
        "discovery": evaluate_ranking(
            scored_discovery,
            score_column="model_score",
            horizon=spec.horizon,
            positions=spec.positions_per_rebalance,
        ),
        "validation_refit_diagnostic": evaluate_ranking(
            scored_validation,
            score_column="model_score",
            horizon=spec.horizon,
            positions=spec.positions_per_rebalance,
        ),
        "holdout": evaluate_ranking(
            scored_holdout,
            score_column="model_score",
            horizon=spec.horizon,
            positions=spec.positions_per_rebalance,
        ),
    }
    baselines = {
        name: evaluate_ranking(
            frame,
            score_column=baseline_column,
            horizon=spec.horizon,
            positions=spec.positions_per_rebalance,
        )
        for name, frame in (
            ("discovery", discovery),
            ("validation", validation),
            ("holdout", holdout),
        )
    }
    holdout_book = windows["holdout"].get("top_book") or {}
    diagnostic_promising = all(
        (
            (windows["holdout"].get("median_daily_rank_ic") or 0) > 0,
            (holdout_book.get("mean_stressed_pct") or 0) > 0,
            (holdout_book.get("sharpe") or 0) > 0.5,
        )
    )
    coefficients = sorted(
        (
            {"feature": feature.removeprefix("x_"), "coefficient": coefficient}
            for feature, coefficient in zip(
                model.feature_names,
                model.coefficients,
                strict=True,
            )
        ),
        key=lambda row: abs(float(row["coefficient"])),
        reverse=True,
    )
    return finite_dict(
        {
            "spec": asdict(spec),
            "spec_hash": spec.spec_hash(),
            "features": list(FEATURE_COLUMNS),
            "rows": {
                "discovery": discovery.height,
                "validation": validation.height,
                "holdout": holdout.height,
            },
            "penalty_trials": trials,
            "selected_penalty": selected_penalty,
            "model": model.as_dict(),
            "coefficients_by_absolute_weight": coefficients,
            "model_results": windows,
            "momentum_baseline": baselines,
            "research_verdict": (
                "promising_diagnostic_but_data_blocked"
                if diagnostic_promising
                else "rejected_or_requires_new_preregistered_hypothesis"
            ),
            "promotion_status": "blocked",
            "promotion_blockers": [
                "historical security universe is not point-in-time complete",
                "survivor-only sample cannot certify positive alpha",
                "no independent forward shadow period has completed",
            ],
        }
    )


async def main(argv: list[str]) -> None:
    args = _parse_args(argv)
    if args.reuse_run:
        run_dir = args.reuse_run.resolve()
        manifest = json.loads((run_dir / "dataset-manifest.json").read_text())
    else:
        stamp = dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")
        run_dir = (args.output_root / stamp).resolve()
        run_dir.mkdir(parents=True, exist_ok=False)
        manifest = await build_datasets(
            run_dir,
            horizons=args.horizons,
            max_symbols=args.max_symbols,
        )

    results = {
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "generated_at": dt.datetime.now(dt.UTC).isoformat(),
        "run_dir": str(run_dir),
        "dataset_manifest": manifest,
        "models": {},
    }
    for horizon in args.horizons:
        print(f"training horizon {horizon}", flush=True)
        results["models"][str(horizon)] = train_horizon(
            run_dir,
            CrossSectionalSpec(horizon=horizon),
        )
    artifact = run_dir / "model-evaluation.json"
    artifact.write_text(json.dumps(finite_dict(results), indent=2, sort_keys=True, default=str))
    print(json.dumps({"artifact": str(artifact), "models": results["models"]}, indent=2, default=str))


async def _entrypoint(argv: list[str]) -> None:
    try:
        await main(argv)
    finally:
        await dispose_engine()


if __name__ == "__main__":
    asyncio.run(_entrypoint(sys.argv[1:]))
