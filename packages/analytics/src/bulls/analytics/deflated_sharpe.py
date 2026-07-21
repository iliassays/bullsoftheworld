"""Deflated Sharpe Ratio: the overfitting guard the Atlas validation protocol requires.

The institutional study (Phase 13.3.3) makes one anti-overfitting mechanism mandatory before
any strategy is promoted: *the final report carries a deflated performance statistic computed
over the full trial count*. A Sharpe ratio selected as the best of many trials is upward-biased
— the more specifications you try, the higher the best-looking Sharpe climbs even when every
strategy is worthless. This module quantifies that.

Two statistics, both from Bailey & López de Prado:

- **Probabilistic Sharpe Ratio (PSR)** — "The Sharpe Ratio Efficient Frontier" (J. Risk, 2012):
  the probability that the true Sharpe exceeds a benchmark, correcting for track-record length
  and for non-normal returns (fat tails and skew inflate a naive Sharpe's confidence).
- **Deflated Sharpe Ratio (DSR)** — "The Deflated Sharpe Ratio" (J. Portfolio Mgmt, 2014):
  PSR evaluated against the Sharpe you would expect to see *by chance* as the maximum of N
  independent trials. A DSR of 0.95 means: after accounting for how many strategies were tried,
  there is a 95% probability the edge is real rather than a selection artifact.

Deliberately dependency-free (pure ``math``/``statistics``) to match the analytics package.
The normal CDF is exact via ``math.erfc``; its inverse uses Acklam's approximation
(|error| < 1.2e-9), which is far tighter than the statistic's own sampling error.
"""

from __future__ import annotations

import math
import statistics
from collections.abc import Sequence

from pydantic import BaseModel

# Euler-Mascheroni constant, used in the expected-maximum-order-statistic approximation.
_EULER_MASCHERONI = 0.5772156649015329


def _norm_cdf(x: float) -> float:
    """Standard normal CDF, exact to machine precision via the complementary error function."""
    return 0.5 * math.erfc(-x / math.sqrt(2.0))


# Acklam's rational approximation to the inverse standard normal CDF.
_ACKLAM_A = (
    -3.969683028665376e01,
    2.209460984245205e02,
    -2.759285104469687e02,
    1.383577518672690e02,
    -3.066479806614716e01,
    2.506628277459239e00,
)
_ACKLAM_B = (
    -5.447609879822406e01,
    1.615858368580409e02,
    -1.556989798598866e02,
    6.680131188771972e01,
    -1.328068155288572e01,
)
_ACKLAM_C = (
    -7.784894002430293e-03,
    -3.223964580411365e-01,
    -2.400758277161838e00,
    -2.549732539343734e00,
    4.374664141464968e00,
    2.938163982698783e00,
)
_ACKLAM_D = (
    7.784695709041462e-03,
    3.224671290700398e-01,
    2.445134137142996e00,
    3.754408661907416e00,
)


def _norm_ppf(p: float) -> float:
    """Inverse standard normal CDF (quantile function) via Acklam's approximation.

    ``p`` must lie strictly in (0, 1); the callers here guarantee that.
    """
    if not 0.0 < p < 1.0:
        raise ValueError(f"norm_ppf requires 0 < p < 1, got {p}")
    # Rational-approximation regions: two tails and a central body.
    low, high = 0.02425, 1 - 0.02425
    if p < low:
        q = math.sqrt(-2.0 * math.log(p))
        return (
            ((((_ACKLAM_C[0] * q + _ACKLAM_C[1]) * q + _ACKLAM_C[2]) * q + _ACKLAM_C[3]) * q
             + _ACKLAM_C[4]) * q + _ACKLAM_C[5]
        ) / ((((_ACKLAM_D[0] * q + _ACKLAM_D[1]) * q + _ACKLAM_D[2]) * q + _ACKLAM_D[3]) * q + 1.0)
    if p > high:
        q = math.sqrt(-2.0 * math.log(1.0 - p))
        return -(
            ((((_ACKLAM_C[0] * q + _ACKLAM_C[1]) * q + _ACKLAM_C[2]) * q + _ACKLAM_C[3]) * q
             + _ACKLAM_C[4]) * q + _ACKLAM_C[5]
        ) / ((((_ACKLAM_D[0] * q + _ACKLAM_D[1]) * q + _ACKLAM_D[2]) * q + _ACKLAM_D[3]) * q + 1.0)
    q = p - 0.5
    r = q * q
    return (
        (((((_ACKLAM_A[0] * r + _ACKLAM_A[1]) * r + _ACKLAM_A[2]) * r + _ACKLAM_A[3]) * r
          + _ACKLAM_A[4]) * r + _ACKLAM_A[5]) * q
    ) / (((((_ACKLAM_B[0] * r + _ACKLAM_B[1]) * r + _ACKLAM_B[2]) * r + _ACKLAM_B[3]) * r
          + _ACKLAM_B[4]) * r + 1.0)


class SharpeMoments(BaseModel):
    """Per-period Sharpe and the higher moments that bias its confidence."""

    num_returns: int
    sharpe: float
    skewness: float
    # Non-excess kurtosis: a normal distribution scores 3.0, not 0.0.
    kurtosis: float


class DeflatedSharpeResult(BaseModel):
    """Overfitting-adjusted read on a backtest's Sharpe ratio."""

    moments: SharpeMoments
    num_trials: int
    # Expected Sharpe of the best of ``num_trials`` worthless strategies — the bar chance clears.
    benchmark_sharpe: float
    # P(true Sharpe > 0), track-record- and non-normality-adjusted but NOT trial-adjusted.
    probabilistic_sharpe: float
    # P(true Sharpe > benchmark_sharpe): the trial-count-adjusted confidence. This is the guard.
    deflated_sharpe: float
    threshold: float
    passes: bool


def sharpe_moments(returns: Sequence[float]) -> SharpeMoments | None:
    """Per-period Sharpe plus skewness and (non-excess) kurtosis. ``None`` if undefined.

    The Sharpe uses the sample standard deviation (matching the backtest engine's
    ``statistics.stdev``); the higher moments use population-normalized central moments,
    as the PSR/DSR derivations assume.
    """
    n = len(returns)
    if n < 8:
        # Skew/kurtosis are meaningless on a handful of points; refuse rather than mislead.
        return None
    mean = statistics.fmean(returns)
    sample_sd = statistics.stdev(returns)
    if sample_sd <= 0:
        return None
    m2 = statistics.fmean((r - mean) ** 2 for r in returns)
    m3 = statistics.fmean((r - mean) ** 3 for r in returns)
    m4 = statistics.fmean((r - mean) ** 4 for r in returns)
    if m2 <= 0:
        return None
    return SharpeMoments(
        num_returns=n,
        sharpe=mean / sample_sd,
        skewness=m3 / m2**1.5,
        kurtosis=m4 / m2**2,
    )


def probabilistic_sharpe_ratio(moments: SharpeMoments, benchmark_sharpe: float = 0.0) -> float:
    """P(true per-period Sharpe > ``benchmark_sharpe``), per Bailey & López de Prado (2012).

    Corrects the observed Sharpe for track-record length and for the return distribution's
    skew and kurtosis. Positive skew and thin tails raise confidence; negative skew and fat
    tails (the dangerous kind) lower it.
    """
    sr = moments.sharpe
    n = moments.num_returns
    denominator = 1.0 - moments.skewness * sr + ((moments.kurtosis - 1.0) / 4.0) * sr * sr
    if denominator <= 0:
        # Extreme moments make the standard error undefined; treat as no usable confidence.
        return 0.0
    z = (sr - benchmark_sharpe) * math.sqrt(n - 1) / math.sqrt(denominator)
    return _norm_cdf(z)


def expected_maximum_sharpe(num_trials: int, trials_sharpe_std: float) -> float:
    """Expected maximum per-period Sharpe of ``num_trials`` independent worthless strategies.

    This is the false-discovery benchmark: the Sharpe you should expect to see purely from
    running many trials against a true Sharpe of zero. Approximated by the expected value of
    the maximum of ``num_trials`` standard normals, scaled by the cross-trial Sharpe dispersion
    (Bailey & López de Prado 2014, eq. for E[max]).
    """
    if num_trials < 1:
        raise ValueError("num_trials must be at least 1")
    if trials_sharpe_std < 0:
        raise ValueError("trials_sharpe_std cannot be negative")
    if num_trials == 1:
        # A single trial is no selection at all — there is nothing to deflate against.
        return 0.0
    e = math.e
    return trials_sharpe_std * (
        (1.0 - _EULER_MASCHERONI) * _norm_ppf(1.0 - 1.0 / num_trials)
        + _EULER_MASCHERONI * _norm_ppf(1.0 - 1.0 / (num_trials * e))
    )


def sharpe_estimation_std(moments: SharpeMoments) -> float:
    """Standard error of a single Sharpe estimate from its own track record.

    Used as the cross-trial Sharpe dispersion when an empirical dispersion across the trial
    family is not supplied — a standard, conservative fallback (the estimator's own sampling
    noise stands in for how much Sharpe wanders between trials).
    """
    sr = moments.sharpe
    variance = (
        1.0 - moments.skewness * sr + ((moments.kurtosis - 1.0) / 4.0) * sr * sr
    ) / (moments.num_returns - 1)
    return math.sqrt(variance) if variance > 0 else 0.0


def deflated_sharpe_ratio(
    returns: Sequence[float],
    *,
    num_trials: int,
    trials_sharpe_std: float | None = None,
    threshold: float = 0.95,
) -> DeflatedSharpeResult | None:
    """Trial-count-adjusted confidence that a backtest's edge is real, not selection noise.

    ``num_trials`` is how many specifications were tried before this one was reported (the Atlas
    trial-family count). ``trials_sharpe_std`` is the observed spread of per-period Sharpe ratios
    across those trials; when omitted, the estimator's own standard error is used as a
    conservative stand-in. Returns ``None`` when there are too few returns to say anything honest.
    """
    if num_trials < 1:
        raise ValueError("num_trials must be at least 1")
    moments = sharpe_moments(returns)
    if moments is None:
        return None
    dispersion = (
        trials_sharpe_std if trials_sharpe_std is not None else sharpe_estimation_std(moments)
    )
    benchmark = expected_maximum_sharpe(num_trials, dispersion)
    psr = probabilistic_sharpe_ratio(moments, benchmark_sharpe=0.0)
    dsr = probabilistic_sharpe_ratio(moments, benchmark_sharpe=benchmark)
    return DeflatedSharpeResult(
        moments=moments,
        num_trials=num_trials,
        benchmark_sharpe=benchmark,
        probabilistic_sharpe=psr,
        deflated_sharpe=dsr,
        threshold=threshold,
        passes=dsr >= threshold,
    )
