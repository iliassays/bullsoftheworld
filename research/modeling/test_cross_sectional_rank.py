from __future__ import annotations

import datetime as dt
from itertools import pairwise

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


def _ranked_panel(
    n_dates: int = 60,
    n_names: int = 200,
    seed: int = 11,
    *,
    correlation: float = 0.0,
) -> pl.DataFrame:
    """Synthetic panel already in rank-percentile space, with a known signal.

    ``correlation`` mixes a shared factor into every feature. The real feature set
    is strongly collinear (``residual_return_5/20/60/120``, ``distance_sma_*``), and
    collinearity is what makes the ridge penalty reshape the *ranking* rather than
    merely rescale it — with independent features ridge shrinks every coefficient
    by the same factor and the ranking is invariant by construction.
    """

    rng = np.random.default_rng(seed)
    rows: dict[str, list] = {"date": [], "net_excess": []}
    for name in FEATURE_COLUMNS:
        rows[f"x_{name}"] = []
    for day in range(n_dates):
        raw = rng.normal(size=(n_names, len(FEATURE_COLUMNS)))
        if correlation:
            shared = rng.normal(size=(n_names, 1))
            raw = raw * (1.0 - correlation) + shared * correlation
        matrix = np.argsort(np.argsort(raw, axis=0), axis=0) / (n_names - 1) - 0.5
        target = 0.02 * matrix[:, 0] + rng.normal(scale=0.05, size=n_names)
        rows["date"] += [dt.date(2021, 1, 1) + dt.timedelta(days=day)] * n_names
        rows["net_excess"] += target.tolist()
        for index, name in enumerate(FEATURE_COLUMNS):
            rows[f"x_{name}"] += matrix[:, index].tolist()
    return pl.DataFrame(rows)


def test_penalty_is_scale_invariant_and_spans_light_shrinkage() -> None:
    """The penalty must mean the same amount of shrinkage regardless of feature
    scale, and the grid's low end must leave the fit essentially unregularised.

    v1 applied an absolute penalty to a weighted Gram matrix pinned near 1/12, so
    its smallest option already shrank coefficients ~55% and a known 0.02 effect
    was recovered as 0.009.
    """

    panel = _ranked_panel()
    light = fit_ridge(panel, penalty=0.001).coefficients[0]
    heavy = fit_ridge(panel, penalty=10.0).coefficients[0]

    assert abs(light - 0.02) < 0.004, "grid low end must recover the planted effect"
    assert abs(heavy) < abs(light) / 5.0, "grid high end must actually regularise"

    # Doubling every feature must not change how much a given penalty shrinks.
    scaled = panel.with_columns(
        [(pl.col(f"x_{name}") * 2.0).alias(f"x_{name}") for name in FEATURE_COLUMNS]
    )
    ratio_plain = fit_ridge(panel, penalty=1.0).coefficients[0] / light
    scaled_light = fit_ridge(scaled, penalty=0.001).coefficients[0]
    ratio_scaled = fit_ridge(scaled, penalty=1.0).coefficients[0] / scaled_light
    assert abs(ratio_plain - ratio_scaled) < 0.02


def test_penalty_grid_spans_meaningfully_different_models() -> None:
    """On collinear features the grid must reach genuinely different rankings.

    v1's grid did the opposite: its two heaviest settings scored a rank correlation
    of 0.9995 (duplicate trials) while the best validation IC sat at the smallest
    penalty, meaning the optimum was outside the search on the light side.
    """

    panel = _ranked_panel(correlation=0.7)
    scores = {}
    for penalty in CrossSectionalSpec().ridge_penalties:
        model = fit_ridge(panel, penalty=penalty)
        scores[penalty] = attach_scores(panel, model)["model_score"].to_numpy()

    ordered = sorted(scores)
    lightest = np.argsort(np.argsort(scores[ordered[0]]))
    heaviest = np.argsort(np.argsort(scores[ordered[-1]]))
    span = float(np.corrcoef(lightest, heaviest)[0, 1])
    assert span < 0.95, f"grid ends are near-duplicates (rank corr {span:.4f})"

    # No adjacent pair may be an exact duplicate of its neighbour.
    for low, high in pairwise(ordered):
        rank_low = np.argsort(np.argsort(scores[low]))
        rank_high = np.argsort(np.argsort(scores[high]))
        assert float(np.corrcoef(rank_low, rank_high)[0, 1]) < 0.99999


def test_sharpe_reports_uncertainty_that_shrinks_with_history() -> None:
    """A Sharpe without its error bar reads a short window as a strong result."""

    def _book(dates: int) -> dict:
        rng = np.random.default_rng(3)
        rows = []
        for day in range(dates):
            date = dt.date(2021, 1, 1) + dt.timedelta(days=7 * day)
            for index in range(5):
                value = float(rng.normal(loc=0.002, scale=0.02))
                rows.append(
                    {
                        "date": date,
                        "code": f"S{index}",
                        "model_score": float(rng.normal()),
                        "net_excess": value,
                        "stressed_net_excess": value - 0.001,
                        "gross_excess": value + 0.002,
                    }
                )
        return evaluate_top_book(
            pl.DataFrame(rows), score_column="model_score", horizon=5, positions=3
        )

    short, long = _book(20), _book(400)
    assert short["sharpe_standard_error"] > long["sharpe_standard_error"]
    assert short["sharpe_lower_95"] < short["sharpe"]
    # ~1/sqrt(years): 20 rebalances at horizon 5 is well under half a year.
    assert short["years"] < long["years"]
    assert short["sharpe_standard_error"] > 1.0


def test_model_rejects_wrong_matrix_shape() -> None:
    model = RidgeModel(("a", "b"), (1.0, 2.0), 0.0, 1.0)
    try:
        model.predict(np.ones((3, 1)))
    except ValueError as exc:
        assert "shape" in str(exc)
    else:
        raise AssertionError("shape mismatch must fail")
