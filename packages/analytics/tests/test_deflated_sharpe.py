"""Tests for the Deflated Sharpe Ratio overfitting guard (Phase 13 validation protocol)."""

from __future__ import annotations

import math
import random

from bulls.analytics.deflated_sharpe import (
    SharpeMoments,
    _norm_cdf,
    _norm_ppf,
    deflated_sharpe_ratio,
    expected_maximum_sharpe,
    probabilistic_sharpe_ratio,
    sharpe_moments,
)


def _series(*, mean: float, sd: float, n: int, seed: int) -> list[float]:
    rng = random.Random(seed)
    return [rng.gauss(mean, sd) for _ in range(n)]


# --- normal CDF / inverse CDF primitives ---------------------------------------------------


def test_norm_cdf_known_values() -> None:
    assert math.isclose(_norm_cdf(0.0), 0.5, abs_tol=1e-12)
    assert math.isclose(_norm_cdf(1.959964), 0.975, abs_tol=1e-6)
    assert math.isclose(_norm_cdf(-1.959964), 0.025, abs_tol=1e-6)


def test_norm_ppf_known_values_and_round_trip() -> None:
    assert math.isclose(_norm_ppf(0.5), 0.0, abs_tol=1e-9)
    assert math.isclose(_norm_ppf(0.975), 1.959964, abs_tol=1e-5)
    for p in (0.001, 0.05, 0.3, 0.5, 0.7, 0.95, 0.999):
        assert math.isclose(_norm_cdf(_norm_ppf(p)), p, abs_tol=1e-9)


# --- moments -------------------------------------------------------------------------------


def test_sharpe_moments_rejects_short_series() -> None:
    assert sharpe_moments([0.01] * 7) is None


def test_sharpe_moments_rejects_zero_variance() -> None:
    assert sharpe_moments([0.01] * 50) is None


def test_sharpe_moments_normal_series_has_near_normal_kurtosis() -> None:
    moments = sharpe_moments(_series(mean=0.001, sd=0.01, n=2000, seed=1))
    assert moments is not None
    assert moments.num_returns == 2000
    # A normal series scores ~3.0 kurtosis and ~0 skew (non-excess convention).
    assert abs(moments.kurtosis - 3.0) < 0.4
    assert abs(moments.skewness) < 0.2


# --- probabilistic Sharpe ------------------------------------------------------------------


def test_psr_zero_sharpe_is_one_half() -> None:
    moments = SharpeMoments(num_returns=253, sharpe=0.0, skewness=0.0, kurtosis=3.0)
    assert math.isclose(probabilistic_sharpe_ratio(moments), 0.5, abs_tol=1e-12)


def test_psr_rises_with_positive_sharpe() -> None:
    weak = SharpeMoments(num_returns=253, sharpe=0.03, skewness=0.0, kurtosis=3.0)
    strong = SharpeMoments(num_returns=253, sharpe=0.15, skewness=0.0, kurtosis=3.0)
    assert probabilistic_sharpe_ratio(strong) > probabilistic_sharpe_ratio(weak) > 0.5


def test_psr_penalizes_negative_skew_and_fat_tails() -> None:
    # Same Sharpe and length; the crash-prone distribution must earn less confidence.
    normal = SharpeMoments(num_returns=253, sharpe=0.1, skewness=0.0, kurtosis=3.0)
    dangerous = SharpeMoments(num_returns=253, sharpe=0.1, skewness=-1.0, kurtosis=6.0)
    assert probabilistic_sharpe_ratio(dangerous) < probabilistic_sharpe_ratio(normal)


def test_psr_grows_with_track_record_length() -> None:
    short = SharpeMoments(num_returns=60, sharpe=0.1, skewness=0.0, kurtosis=3.0)
    long = SharpeMoments(num_returns=1000, sharpe=0.1, skewness=0.0, kurtosis=3.0)
    assert probabilistic_sharpe_ratio(long) > probabilistic_sharpe_ratio(short)


# --- expected maximum Sharpe (the false-discovery benchmark) -------------------------------


def test_expected_maximum_sharpe_single_trial_is_zero() -> None:
    # One trial is no selection: there is nothing to deflate against.
    assert expected_maximum_sharpe(1, 0.05) == 0.0


def test_expected_maximum_sharpe_rises_with_trial_count() -> None:
    values = [expected_maximum_sharpe(n, 0.02) for n in (2, 10, 100, 1000)]
    assert values == sorted(values)
    assert all(v > 0 for v in values)


def test_expected_maximum_sharpe_scales_with_dispersion() -> None:
    assert expected_maximum_sharpe(50, 0.04) > expected_maximum_sharpe(50, 0.02)


# --- deflated Sharpe (the guard) -----------------------------------------------------------


def test_deflated_sharpe_returns_none_for_short_series() -> None:
    assert deflated_sharpe_ratio([0.01] * 5, num_trials=10) is None


def test_deflated_sharpe_single_trial_equals_undeflated() -> None:
    returns = _series(mean=0.0008, sd=0.01, n=750, seed=7)
    result = deflated_sharpe_ratio(returns, num_trials=1)
    assert result is not None
    # No selection to correct for → the benchmark is zero and DSR collapses onto PSR.
    assert result.benchmark_sharpe == 0.0
    assert math.isclose(result.deflated_sharpe, result.probabilistic_sharpe, abs_tol=1e-12)


def test_deflated_sharpe_falls_as_trials_grow() -> None:
    returns = _series(mean=0.0008, sd=0.01, n=750, seed=7)
    one = deflated_sharpe_ratio(returns, num_trials=1)
    fifty = deflated_sharpe_ratio(returns, num_trials=50)
    thousand = deflated_sharpe_ratio(returns, num_trials=1000)
    assert one is not None and fifty is not None and thousand is not None
    # The same backtest is less convincing the more strategies were tried to find it.
    assert one.deflated_sharpe > fifty.deflated_sharpe > thousand.deflated_sharpe


def test_deflated_sharpe_never_exceeds_probabilistic() -> None:
    returns = _series(mean=0.0008, sd=0.01, n=750, seed=7)
    result = deflated_sharpe_ratio(returns, num_trials=200)
    assert result is not None
    assert result.deflated_sharpe <= result.probabilistic_sharpe


def test_deflated_sharpe_pass_flag_tracks_threshold() -> None:
    # A strong, long, single-trial track record should clear a 0.95 bar; heavy selection sinks it.
    returns = _series(mean=0.0012, sd=0.008, n=1000, seed=3)
    convincing = deflated_sharpe_ratio(returns, num_trials=1, threshold=0.95)
    overfit = deflated_sharpe_ratio(returns, num_trials=5000, threshold=0.95)
    assert convincing is not None and overfit is not None
    assert convincing.passes is True
    assert overfit.passes is False


def test_deflated_sharpe_explicit_dispersion_overrides_fallback() -> None:
    returns = _series(mean=0.0008, sd=0.01, n=750, seed=7)
    wide = deflated_sharpe_ratio(returns, num_trials=50, trials_sharpe_std=0.10)
    narrow = deflated_sharpe_ratio(returns, num_trials=50, trials_sharpe_std=0.01)
    assert wide is not None and narrow is not None
    # Wider cross-trial Sharpe dispersion raises the chance bar, lowering the deflated confidence.
    assert wide.deflated_sharpe < narrow.deflated_sharpe
