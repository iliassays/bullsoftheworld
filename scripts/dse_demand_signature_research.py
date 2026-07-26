"""Run the preregistered DSE demand-signature experiment against stored history.

Read-only by construction: this command selects bars and DSEX, computes an isolated research
ledger, and writes JSON. It does not persist signals, strategies, targets, or paper trades.

Usage:

    uv run python scripts/dse_demand_signature_research.py \
        --output /tmp/dse-demand-signature-v1.json
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

from research.edge_discovery.demand_signature import (
    DemandSignatureSpec,
    attach_scores,
    attach_triple_barrier,
    build_features,
    discovery_threshold,
    evaluate_window,
    fit_ridge_logit,
    purged_window,
    select_candidates,
    simulate_slot_portfolio,
)
from research.edge_discovery.harness import DSE_WINDOWS

from bulls.core.db import dispose_engine, get_sessionmaker
from bulls.core.models import DailyBar, MarketSummary


async def load_panel() -> tuple[pl.DataFrame, pl.DataFrame]:
    """Load DSE bars and benchmark only; no current-state symbol filter is applied."""
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        await session.execute(text("SET LOCAL statement_timeout = '10min'"))
        bar_rows = (
            await session.execute(
                select(
                    DailyBar.code,
                    DailyBar.date,
                    DailyBar.open,
                    DailyBar.high,
                    DailyBar.low,
                    DailyBar.close,
                    DailyBar.volume,
                )
                .where(DailyBar.market == "DSE")
                .order_by(DailyBar.code, DailyBar.date)
            )
        ).all()
        benchmark_rows = (
            await session.execute(
                select(MarketSummary.date, MarketSummary.dsex)
                .where(
                    MarketSummary.market == "DSE",
                    MarketSummary.dsex.is_not(None),
                )
                .order_by(MarketSummary.date)
            )
        ).all()

    if not bar_rows:
        raise RuntimeError("No DSE daily bars are available")
    if not benchmark_rows:
        raise RuntimeError("No DSEX benchmark history is available")

    bars = pl.DataFrame(
        [
            {
                "code": row.code,
                "date": row.date,
                "open": float(row.open),
                "high": float(row.high),
                "low": float(row.low),
                "close": float(row.close),
                "volume": int(row.volume or 0),
            }
            for row in bar_rows
            if min(row.open or 0, row.high or 0, row.low or 0, row.close or 0) > 0
        ]
    )
    benchmark = pl.DataFrame(
        [
            {"date": row.date, "benchmark_close": float(row.dsex)}
            for row in benchmark_rows
            if row.dsex and row.dsex > 0
        ]
    ).unique("date", keep="last")
    return bars.join(benchmark, on="date", how="left"), benchmark


def _window_bounds(
    panel_end: dt.date,
) -> tuple[tuple[str, dt.date | None, dt.date], ...]:
    return (
        ("discovery", None, DSE_WINDOWS.discovery_end),
        (
            "validation",
            DSE_WINDOWS.discovery_end + dt.timedelta(days=1),
            DSE_WINDOWS.validation_end,
        ),
        (
            "holdout",
            DSE_WINDOWS.validation_end + dt.timedelta(days=1),
            panel_end,
        ),
    )


def _rounded(value: Any) -> Any:
    if isinstance(value, float):
        return round(value, 6) if value == value else None
    if isinstance(value, dict):
        return {key: _rounded(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_rounded(item) for item in value]
    return value


def run_experiment(
    bars: pl.DataFrame,
    benchmark: pl.DataFrame,
    spec: DemandSignatureSpec,
) -> dict[str, Any]:
    """Execute the frozen discovery -> validation -> holdout contract."""
    panel = build_features(
        bars,
        minimum_adv_bdt=spec.minimum_adv_bdt,
        minimum_history=spec.minimum_history,
        suspicious_drop=spec.suspicious_drop,
    )
    panel = attach_triple_barrier(
        panel,
        horizon=spec.primary_horizon,
        target_return=spec.primary_target,
        stop_return=spec.primary_stop,
        suffix="primary",
        suspicious_drop=spec.suspicious_drop,
    )
    panel = attach_triple_barrier(
        panel,
        horizon=spec.secondary_horizon,
        target_return=spec.secondary_target,
        stop_return=spec.secondary_stop,
        suffix="secondary",
        suspicious_drop=spec.suspicious_drop,
    )
    panel_end = panel["date"].max()
    discovery = purged_window(
        panel,
        start=None,
        end=DSE_WINDOWS.discovery_end,
        label_end_column="exit_date_primary",
    ).filter(pl.col("label_valid_primary"))
    model = fit_ridge_logit(
        discovery,
        l2_penalty=spec.l2_penalty,
    )
    scored = attach_scores(panel, model)
    scored_discovery = purged_window(
        scored,
        start=None,
        end=DSE_WINDOWS.discovery_end,
        label_end_column="exit_date_primary",
    ).filter(pl.col("label_valid_primary"))
    threshold = discovery_threshold(
        scored_discovery,
        quantile=spec.score_quantile,
    )

    window_payload: dict[str, Any] = {}
    for name, start, end in _window_bounds(panel_end):
        primary_frame = purged_window(
            scored,
            start=start,
            end=end,
            label_end_column="exit_date_primary",
        )
        candidates = select_candidates(
            primary_frame,
            threshold=threshold,
            top_n=spec.candidates_per_session,
        )
        primary = evaluate_window(
            primary_frame,
            candidates,
            window=name,
            horizon=spec.primary_horizon,
            one_way_cost_bps=spec.one_way_cost_bps,
            stressed_one_way_cost_bps=spec.stressed_one_way_cost_bps,
            suffix="primary",
        )

        secondary_frame = purged_window(
            scored,
            start=start,
            end=end,
            label_end_column="exit_date_secondary",
        )
        secondary_candidates = candidates.join(
            secondary_frame.select(["code", "date"]),
            on=["code", "date"],
            how="semi",
        )
        secondary = evaluate_window(
            secondary_frame,
            secondary_candidates,
            window=name,
            horizon=spec.secondary_horizon,
            one_way_cost_bps=spec.one_way_cost_bps,
            stressed_one_way_cost_bps=spec.stressed_one_way_cost_bps,
            suffix="secondary",
        )
        portfolio = simulate_slot_portfolio(
            candidates.filter(pl.col("label_valid_primary")),
            benchmark,
            slots=spec.portfolio_slots,
            one_way_cost_bps=spec.one_way_cost_bps,
        )
        window_payload[name] = {
            "bounds": {"start": start, "end": end},
            "primary": asdict(primary),
            "secondary_robustness": asdict(secondary),
            "portfolio": asdict(portfolio),
        }

    validation = window_payload["validation"]["primary"]
    holdout = window_payload["holdout"]["primary"]
    quantitative_gates = {
        "validation_sample_at_least_30": validation["selected_events"] >= 30,
        "holdout_sample_at_least_30": holdout["selected_events"] >= 30,
        "positive_validation_precision_lift": (
            validation["precision_lift_pp"] is not None
            and validation["precision_lift_pp"] > 0
        ),
        "positive_holdout_precision_lift": (
            holdout["precision_lift_pp"] is not None
            and holdout["precision_lift_pp"] > 0
        ),
        "positive_validation_stressed_return": (
            validation["mean_stressed_return_pct"] is not None
            and validation["mean_stressed_return_pct"] > 0
        ),
        "positive_holdout_stressed_return": (
            holdout["mean_stressed_return_pct"] is not None
            and holdout["mean_stressed_return_pct"] > 0
        ),
        "positive_holdout_ci_floor": (
            holdout["net_ci_low_pct"] is not None and holdout["net_ci_low_pct"] > 0
        ),
    }
    data_gates = {
        "corporate_action_adjusted_prices": False,
        "enough_independent_market_regimes": False,
        "point_in_time_universe_membership": False,
    }
    quantitative_pass = all(quantitative_gates.values())
    production_pass = quantitative_pass and all(data_gates.values())
    verdict = (
        "eligible_for_separate_forward_collection"
        if quantitative_pass
        else "rejected_or_requires_new_preregistered_hypothesis"
    )

    training_rows = discovery.filter(
        pl.col("eligible")
        & pl.col("label_primary").is_not_null()
        & pl.col("label_valid_primary")
    ).drop_nulls(model.feature_names)
    payload = {
        "experiment": spec.as_dict(),
        "execution_contract": {
            "signal_time": "session close",
            "entry_time": "next session open",
            "barrier_tie": "stop first",
            "candidate_policy": (
                f"discovery p{int(spec.score_quantile * 100)} threshold; "
                f"top {spec.candidates_per_session} per session"
            ),
            "portfolio_policy": f"{spec.portfolio_slots} non-overlapping equal capital slots",
            "normal_cost": f"{spec.one_way_cost_bps:.0f} bps each side",
            "stress_cost": f"{spec.stressed_one_way_cost_bps:.0f} bps each side",
        },
        "panel": {
            "rows": panel.height,
            "codes": panel["code"].n_unique(),
            "first_date": panel["date"].min(),
            "last_date": panel_end,
            "eligible_rows": panel.filter(pl.col("eligible")).height,
            "price_basis": "raw DSE closes; corporate-action contaminated",
        },
        "model": {
            "family": "balanced ridge logistic regression",
            "fit_window_end": DSE_WINDOWS.discovery_end,
            "training_rows": training_rows.height,
            "positive_rate": float(training_rows["label_primary"].mean()),
            "score_threshold": threshold,
            "iterations": model.iterations,
            "converged": model.converged,
            "coefficients": model.coefficient_rows(),
        },
        "windows": window_payload,
        "gates": {
            "quantitative": quantitative_gates,
            "data": data_gates,
            "quantitative_pass": quantitative_pass,
            "production_pass": production_pass,
        },
        "verdict": verdict,
        "atlas_action": (
            "No production strategy, Agent Decision, paper target, or UI ranking is created. "
            "A favorable result starts a separately registered forward collection only."
        ),
    }
    return _rounded(payload)


async def async_main(output: Path) -> None:
    try:
        bars, benchmark = await load_panel()
        payload = run_experiment(bars, benchmark, DemandSignatureSpec())
        output.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(
            output.write_text,
            json.dumps(payload, indent=2, default=str) + "\n",
        )

        print(
            "=== DSE Demand Signature v1 ===\n"
            f"Panel: {payload['panel']['rows']:,} rows, {payload['panel']['codes']} codes, "
            f"{payload['panel']['first_date']} to {payload['panel']['last_date']}"
        )
        print(
            f"Discovery fit: {payload['model']['training_rows']:,} rows, "
            f"base rate {payload['model']['positive_rate']:.1%}, "
            f"threshold {payload['model']['score_threshold']:.4f}"
        )
        for name, window in payload["windows"].items():
            result = window["primary"]
            portfolio = window["portfolio"]
            print(
                f"{name:10s} n={result['selected_events']:>4} "
                f"precision={result['precision']!s:>8} "
                f"lift={result['precision_lift_pp']!s:>8}pp "
                f"net={result['mean_net_return_pct']!s:>8}% "
                f"stress={result['mean_stressed_return_pct']!s:>8}% "
                f"book={portfolio['total_return_pct']:+.2f}%"
            )
        print(f"Verdict: {payload['verdict']}")
        print(f"Production pass: {payload['gates']['production_pass']}")
        print(f"Wrote {output}")
    finally:
        await dispose_engine()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("/tmp/dse-demand-signature-v1.json"),
    )
    args = parser.parse_args()
    asyncio.run(async_main(args.output))


if __name__ == "__main__":
    main()
