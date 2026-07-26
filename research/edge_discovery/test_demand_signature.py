from __future__ import annotations

import datetime as dt

import numpy as np
import polars as pl
from polars.testing import assert_frame_equal

from research.edge_discovery.demand_signature import (
    FEATURE_COLUMNS,
    attach_scores,
    attach_triple_barrier,
    build_features,
    discovery_threshold,
    fit_ridge_logit,
    purged_window,
    select_candidates,
    simulate_slot_portfolio,
)


def _bars(codes: tuple[str, ...] = ("AAA", "BBB"), sessions: int = 140) -> pl.DataFrame:
    start = dt.date(2025, 1, 1)
    rows = []
    for code_index, code in enumerate(codes):
        for index in range(sessions):
            close = 100.0 + code_index * 5 + index * 0.15 + np.sin(index / 5)
            rows.append(
                {
                    "code": code,
                    "date": start + dt.timedelta(days=index),
                    "open": close - 0.2,
                    "high": close + 1.0,
                    "low": close - 1.0,
                    "close": close,
                    "volume": 200_000 + (index % 7) * 10_000,
                    "benchmark_close": 5_000.0 + index * 2,
                }
            )
    return pl.DataFrame(rows)


def test_features_do_not_change_when_future_bars_are_appended() -> None:
    bars = _bars()
    cutoff = dt.date(2025, 4, 20)
    prefix = bars.filter(pl.col("date") <= cutoff)

    full_features = build_features(bars).filter(pl.col("date") <= cutoff)
    prefix_features = build_features(prefix)
    columns = ["code", "date", *FEATURE_COLUMNS, "eligible"]

    assert_frame_equal(
        full_features.select(columns),
        prefix_features.select(columns),
        check_exact=False,
        rel_tol=1e-12,
        abs_tol=1e-12,
    )


def test_triple_barrier_enters_next_open_and_resolves_tie_to_stop() -> None:
    start = dt.date(2026, 1, 1)
    rows = []
    for index in range(12):
        rows.append(
            {
                "code": "AAA",
                "date": start + dt.timedelta(days=index),
                "open": 100.0,
                "high": 200.0 if index == 0 else 101.0,
                "low": 99.0,
                "close": 100.0,
                "volume": 1_000,
            }
        )
    # On the first executable bar both barriers touch. Daily data cannot reveal order.
    rows[1].update(open=100.0, high=116.0, low=93.0, close=101.0)

    labelled = attach_triple_barrier(
        pl.DataFrame(rows),
        horizon=5,
        target_return=0.15,
        stop_return=0.06,
        suffix="primary",
    )
    first = labelled.row(0, named=True)

    assert first["entry_date_primary"] == start + dt.timedelta(days=1)
    assert first["entry_price_primary"] == 100.0
    assert first["state_primary"] == "stop"
    assert first["label_primary"] == 0
    assert first["gross_return_primary"] == -0.06


def test_purged_window_excludes_outcomes_crossing_boundary() -> None:
    boundary = dt.date(2026, 1, 31)
    frame = pl.DataFrame(
        {
            "date": [dt.date(2026, 1, 10), dt.date(2026, 1, 25)],
            "exit_date_primary": [dt.date(2026, 1, 20), dt.date(2026, 2, 3)],
        }
    )

    result = purged_window(
        frame,
        start=dt.date(2026, 1, 1),
        end=boundary,
        label_end_column="exit_date_primary",
    )

    assert result["date"].to_list() == [dt.date(2026, 1, 10)]


def _model_frame(rows: int = 240) -> pl.DataFrame:
    rng = np.random.default_rng(17)
    values = rng.normal(size=(rows, len(FEATURE_COLUMNS)))
    target = (values[:, 0] + 0.5 * values[:, 1] > 0.3).astype(int)
    data = {name: values[:, index] for index, name in enumerate(FEATURE_COLUMNS)}
    data.update(
        {
            "code": [f"C{index % 12:02d}" for index in range(rows)],
            "date": [
                dt.date(2025, 1, 1) + dt.timedelta(days=index // 12)
                for index in range(rows)
            ],
            "eligible": [True] * rows,
            "label_primary": target,
        }
    )
    return pl.DataFrame(data)


def test_model_is_deterministic_and_threshold_uses_discovery_only() -> None:
    discovery = _model_frame()
    model_a = fit_ridge_logit(discovery)
    model_b = fit_ridge_logit(discovery)

    assert model_a == model_b
    assert model_a.coefficients[0] > 0
    assert model_a.coefficients[1] > 0

    scored = attach_scores(discovery, model_a)
    threshold = discovery_threshold(scored, quantile=0.95)
    extreme_holdout = scored.with_columns(
        pl.when(pl.int_range(pl.len()) == 0)
        .then(1.0)
        .otherwise(pl.col("demand_score"))
        .alias("demand_score")
    )
    assert discovery_threshold(scored, quantile=0.95) == threshold
    assert discovery_threshold(extreme_holdout, quantile=0.95) != threshold


def test_candidate_selection_is_thresholded_and_capped_per_session() -> None:
    day = dt.date(2026, 2, 1)
    frame = pl.DataFrame(
        {
            "code": ["A", "B", "C", "D", "E"],
            "date": [day] * 5,
            "eligible": [True] * 5,
            "demand_score": [0.99, 0.95, 0.90, 0.85, 0.70],
        }
    )

    selected = select_candidates(frame, threshold=0.80, top_n=3)

    assert selected["code"].to_list() == ["A", "B", "C"]
    assert selected["selection_rank"].to_list() == [1, 2, 3]


def test_slot_portfolio_never_overlaps_more_positions_than_slots() -> None:
    start = dt.date(2026, 3, 1)
    candidates = pl.DataFrame(
        {
            "code": ["A", "B", "C"],
            "date": [start] * 3,
            "entry_date_primary": [start + dt.timedelta(days=1)] * 3,
            "exit_date_primary": [start + dt.timedelta(days=5)] * 3,
            "gross_return_primary": [0.15, 0.15, 0.15],
            "selection_rank": [1, 2, 3],
            "demand_score": [0.9, 0.8, 0.7],
        }
    )
    benchmark = pl.DataFrame(
        {
            "date": [start + dt.timedelta(days=1), start + dt.timedelta(days=5)],
            "benchmark_close": [100.0, 105.0],
        }
    )

    result = simulate_slot_portfolio(
        candidates,
        benchmark,
        slots=2,
        one_way_cost_bps=100.0,
    )

    assert result.trades == 2
    assert result.rejected_for_slots == 1
    assert result.total_return_pct > 0
