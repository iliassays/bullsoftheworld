from __future__ import annotations

import datetime as dt

import numpy as np
import polars as pl

from research.modeling.cross_sectional_rank import (
    FEATURE_COLUMNS,
    CrossSectionalSpec,
    RidgeModel,
    attach_scores,
    build_benchmark_calendar,
    build_symbol_observations,
    evaluate_top_book,
    fit_ridge,
    rank_features,
    temporal_window,
)


def _bars(code: str, *, periods: int = 340, drift: float = 0.001) -> pl.DataFrame:
    dates = [dt.date(2021, 1, 1) + dt.timedelta(days=index) for index in range(periods)]
    close = np.asarray([100.0 * (1.0 + drift) ** index for index in range(periods)])
    return pl.DataFrame(
        {
            "code": [code] * periods,
            "date": dates,
            "open": close * 0.999,
            "high": close * 1.01,
            "low": close * 0.99,
            "close": close,
            "adjusted_close": close,
            "volume": [200_000] * periods,
        }
    )


def test_symbol_features_use_next_open_and_non_overlapping_dates() -> None:
    benchmark = build_benchmark_calendar(_bars("SPY", drift=0.0002), horizons=(5,))
    spec = CrossSectionalSpec(horizon=5, minimum_adv=1.0)
    observations = build_symbol_observations(_bars("AAA"), benchmark, spec)

    assert observations.height > 0
    assert observations["session_ordinal"].to_list() == sorted(
        observations["session_ordinal"].to_list()
    )
    assert all(value % 5 == 0 for value in observations["session_ordinal"])
    first = observations.row(0, named=True)
    bars = _bars("AAA")
    signal_index = bars["date"].to_list().index(first["date"])
    expected = (
        bars["adjusted_close"][signal_index + 5]
        / bars["open"][signal_index + 1]
        - 1.0
    )
    assert abs(first["gross_return"] - expected) < 1e-12
    assert first["exit_date"] == bars["date"][signal_index + 5]


def test_rank_features_are_date_local_and_bounded() -> None:
    rows = []
    for date in (dt.date(2024, 1, 5), dt.date(2024, 1, 12)):
        for index, code in enumerate(("A", "B", "C")):
            row = {"date": date, "code": code}
            row.update({name: float(index) for name in FEATURE_COLUMNS})
            rows.append(row)
    ranked = rank_features(pl.DataFrame(rows))

    for name in FEATURE_COLUMNS:
        assert ranked[f"x_{name}"].min() == -0.5
        assert ranked[f"x_{name}"].max() == 0.5


def test_ridge_recovers_positive_ordering_and_top_book() -> None:
    rows = []
    for day in range(30):
        date = dt.date(2021, 1, 1) + dt.timedelta(days=day)
        for index in range(20):
            row = {
                "date": date,
                "exit_date": date + dt.timedelta(days=5),
                "code": f"S{index}",
                "net_excess": (index - 10) / 1000,
                "stressed_net_excess": (index - 10) / 1000 - 0.001,
                "gross_excess": (index - 10) / 1000 + 0.002,
            }
            row.update({f"x_{name}": (index - 10) / 20 for name in FEATURE_COLUMNS})
            rows.append(row)
    frame = pl.DataFrame(rows)
    model = fit_ridge(frame, penalty=0.1)
    scored = attach_scores(frame, model)
    result = evaluate_top_book(
        scored,
        score_column="model_score",
        horizon=5,
        positions=3,
    )

    assert model.coefficients[0] > 0
    assert result["dates"] == 30
    assert result["mean_net_pct"] > 0


def test_temporal_windows_purge_labels_crossing_boundaries() -> None:
    spec = CrossSectionalSpec(
        discovery_end=dt.date(2022, 12, 31),
        validation_end=dt.date(2024, 12, 31),
    )
    frame = pl.DataFrame(
        {
            "date": [
                dt.date(2022, 12, 30),
                dt.date(2022, 12, 30),
                dt.date(2023, 1, 3),
                dt.date(2024, 12, 30),
                dt.date(2025, 1, 2),
            ],
            "exit_date": [
                dt.date(2022, 12, 31),
                dt.date(2023, 1, 4),
                dt.date(2023, 1, 10),
                dt.date(2025, 1, 6),
                dt.date(2025, 1, 9),
            ],
        }
    )

    assert temporal_window(frame, spec, "discovery").height == 1
    assert temporal_window(frame, spec, "validation").height == 1
    assert temporal_window(frame, spec, "holdout").height == 1


def test_model_rejects_wrong_matrix_shape() -> None:
    model = RidgeModel(("a", "b"), (1.0, 2.0), 0.0, 1.0)
    try:
        model.predict(np.ones((3, 1)))
    except ValueError as exc:
        assert "shape" in str(exc)
    else:
        raise AssertionError("shape mismatch must fail")
