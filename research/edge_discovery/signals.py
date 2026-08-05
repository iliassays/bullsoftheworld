"""Deterministic signal definitions, one function per preregistered hypothesis.

Each function receives the featured panel and returns a boolean mask expression. Every
expression reads only columns that :func:`dataset.with_features` computed from bars at or before
the row's own session, so no function can see its own outcome.

Cross-sectional thresholds (deciles, percentiles) are ranked ``.over("date")`` — that is
point-in-time by construction, since a session's ranking uses only that session's observable
values.
"""

from __future__ import annotations

import polars as pl

# Below this raw price the tick size is a large fraction of the price itself, so a single
# minimum increment prints as an enormous "return". Verified 2026-08: PPCB quoted at $0.01 and
# ticking to $0.02 produced a 21-session return of +4,166,567% — arithmetically correct and
# completely meaningless. Any study that lets these rows in has its mean set by quoting
# granularity rather than by the market, which is exactly how the microcap "edge" in this
# programme turned out to be an artefact.
MIN_TRADEABLE_PRICE = 1.00


def tradeable() -> pl.Expr:
    """Data-quality floor applied to EVERY study, independent of the strategy's own filters.

    Two failure modes, both observed in production data:

    * **Sub-penny quoting.** See ``MIN_TRADEABLE_PRICE`` above.
    * **Zero-volume sessions.** 351,354 US bars have ``volume = 0``. The close is carried
      forward from the last trade, so the bar is a quote, not a transaction. A fill cannot be
      assumed at a price where nothing traded, and 223 of the extreme microcap "winners" in this
      programme had no volume on the session they were supposedly bought.
    """
    return (pl.col("close") >= MIN_TRADEABLE_PRICE) & (pl.col("volume") > 0)


def eligible(min_liq_decile: int = 4, min_price: float = 5.0, min_bars: int = 252) -> pl.Expr:
    """Baseline tradability gate.

    The price floor uses the *raw* close, not the adjusted close: adjusted prices are
    retroactively restated, so filtering on an adjusted level would apply a threshold the market
    never saw and would quietly encode future split knowledge.

    ``tradeable()`` is folded in unconditionally. A caller lowering ``min_price`` to reach the
    microcap universe must not be able to lower it into the sub-penny noise floor as well.
    """
    return (
        tradeable()
        & (pl.col("liq_decile") >= min_liq_decile)
        & (pl.col("close") >= min_price)
        & (pl.col("bars_seen") >= min_bars)
        & pl.col("adv_20").is_not_null()
        & pl.col("vol_60").is_not_null()
    )


def _pctile_within_date(column: str) -> pl.Expr:
    """Fractional rank of a column within its session, in [0, 1]."""
    return pl.col(column).rank("ordinal").over("date") / pl.len().over("date")


# --- Family A: trend continuation after a controlled pullback ------------------------------


def trend_pullback(
    pullback_atr: float = 1.5, near_sma20: float = 0.02, mom_pctile: float = 0.60
) -> pl.Expr:
    """Established uptrend, price pulled back to the 20-day mean on fading participation."""
    depth = (pl.col("high_20") - pl.col("close")) / pl.col("atr")
    return (
        (pl.col("close") > pl.col("sma_200"))
        & (_pctile_within_date("mom_12_1") >= mom_pctile)
        # Pulled back from a recent high, but only modestly relative to the name's own noise.
        & (depth > 0.25)
        & (depth <= pullback_atr)
        # ...and the pullback landed on the 20-day mean rather than slicing through it.
        & ((pl.col("close") - pl.col("sma_20")).abs() / pl.col("sma_20") <= near_sma20)
        & (pl.col("close") > pl.col("sma_50"))
        # Fading participation during the pullback distinguishes absorption from distribution.
        & (pl.col("volume").rolling_mean(5).over("code") < pl.col("avg_vol_20"))
    )


# --- Family B: compression and breakout ----------------------------------------------------


def compression_breakout(
    atr_contraction: float = 0.8, vol_multiple: float = 1.5, from_high: float = -0.15
) -> pl.Expr:
    """Range contraction near the highs, resolved upward on expanded volume."""
    prior_high_20 = pl.col("high").rolling_max(20).over("code").shift(1)
    atr_then = pl.col("atr").shift(20).over("code")
    pct_from_high = pl.col("close") / pl.col("high_52w") - 1
    return (
        (pct_from_high >= from_high)
        & (pl.col("atr") <= atr_contraction * atr_then)
        & (pl.col("close") > prior_high_20)
        & (pl.col("volume") >= vol_multiple * pl.col("avg_vol_20"))
    )


def new_52w_high() -> pl.Expr:
    prior_high = pl.col("high_52w").shift(1).over("code")
    return pl.col("close") > prior_high


def post_breakout_retest(retest_pct: float = 0.03) -> pl.Expr:
    """Price has returned to a breakout level cleared 3-10 sessions ago and is holding it."""
    breakout = compression_breakout()
    # The trigger level is the base high on the breakout session.
    trigger = pl.col("high").rolling_max(20).over("code").shift(1)
    recent_breakout = pl.any_horizontal([breakout.shift(k).over("code") for k in range(3, 11)])
    anchored_trigger = pl.max_horizontal(
        [
            pl.when(breakout.shift(k).over("code"))
            .then(trigger.shift(k).over("code"))
            .otherwise(None)
            for k in range(3, 11)
        ]
    )
    return (
        recent_breakout
        & anchored_trigger.is_not_null()
        & (pl.col("close") >= anchored_trigger)
        & (pl.col("close") <= anchored_trigger * (1 + retest_pct))
    )


# --- Family C: failed breakdown ------------------------------------------------------------


def failed_breakdown(reclaim_pct: float = 1.02, relvol: float = 1.2) -> pl.Expr:
    """Support was undercut in the recent past and today's close reclaims it on volume.

    The support window ends 11 sessions back and the undercut window excludes the current
    session, so the level being tested can never be set by the bar that tests it.
    """
    support = pl.col("low").rolling_min(50).over("code").shift(11)
    undercut = pl.min_horizontal([pl.col("low").shift(k).over("code") for k in range(1, 8)])
    return (
        support.is_not_null()
        & (undercut < 0.99 * support)
        & (pl.col("close") >= reclaim_pct * support)
        & (pl.col("volume") >= relvol * pl.col("avg_vol_20"))
    )


# --- Family D: cross-sectional mean reversion ----------------------------------------------


def reversal(column: str = "ret_5", pctile: float = 0.10) -> pl.Expr:
    return _pctile_within_date(column) <= pctile


# --- Family E: momentum --------------------------------------------------------------------


def momentum_top(pctile: float = 0.10) -> pl.Expr:
    return _pctile_within_date("mom_12_1") >= (1 - pctile)


def momentum_with_pullback(mom_pctile: float = 0.10, st_pctile: float = 0.30) -> pl.Expr:
    """Long-horizon winners that are short-horizon losers."""
    return momentum_top(mom_pctile) & (_pctile_within_date("ret_5") <= st_pctile)


# --- Family F: volatility ------------------------------------------------------------------


def low_volatility(pctile: float = 0.10) -> pl.Expr:
    return _pctile_within_date("vol_60") <= pctile


def vol_contraction(ratio: float = 0.6) -> pl.Expr:
    return pl.col("vol_20") <= ratio * pl.col("vol_60")


# --- Family G: forced selling --------------------------------------------------------------


def capitulation(decline: float = -0.12, vol_multiple: float = 2.5) -> pl.Expr:
    return (
        (pl.col("ret_5") <= decline)
        & (pl.col("volume") >= vol_multiple * pl.col("avg_vol_20"))
        & (pl.col("close").shift(5).over("code") > pl.col("sma_200").shift(5).over("code"))
    )


# --- Family H: baselines -------------------------------------------------------------------


def high_relative_volume(multiple: float = 2.0) -> pl.Expr:
    return pl.col("volume") >= multiple * pl.col("avg_vol_20")


def pseudo_random(rate: float = 0.02) -> pl.Expr:
    """Deterministic pseudo-random selection: reproducible, independent of any market feature.

    Uses the hash of code and date so the same rows are selected on every run without needing a
    seeded RNG threaded through polars.
    """
    return (pl.col("code") + pl.col("date").cast(pl.String)).hash(seed=20260725) % 10_000 < int(
        rate * 10_000
    )


SIGNALS = {
    "us_trend_pullback_20d": lambda: trend_pullback(1.5, 0.02, 0.60),
    "us_trend_pullback_shallow": lambda: trend_pullback(0.75, 0.02, 0.60),
    "us_trend_pullback_h21": lambda: trend_pullback(1.5, 0.02, 0.60),
    "dse_trend_pullback_20d": lambda: trend_pullback(1.5, 0.02, 0.60),
    "us_compression_breakout": lambda: compression_breakout(0.8, 1.5, -0.15),
    "us_52w_high_breakout": lambda: new_52w_high(),
    "us_post_breakout_retest": lambda: post_breakout_retest(0.03),
    "dse_compression_breakout": lambda: compression_breakout(0.8, 1.5, -0.15),
    "us_failed_breakdown": lambda: failed_breakdown(1.02, 1.2),
    "us_failed_breakdown_uptrend": lambda: (
        failed_breakdown(1.02, 1.2) & (pl.col("close") > pl.col("sma_200"))
    ),
    "dse_failed_breakdown": lambda: failed_breakdown(1.02, 1.2),
    "us_reversal_5d": lambda: reversal("ret_5", 0.10),
    "us_reversal_5d_megacap": lambda: reversal("ret_5", 0.10) & (pl.col("liq_decile") == 9),
    "us_reversal_1d": lambda: reversal("ret", 0.05),
    "dse_reversal_5d": lambda: reversal("ret_5", 0.10),
    "us_momentum_12_1": lambda: momentum_top(0.10),
    "us_momentum_with_pullback": lambda: momentum_with_pullback(0.10, 0.30),
    "dse_momentum_12_1": lambda: momentum_top(0.10),
    "us_low_volatility": lambda: low_volatility(0.10),
    "us_vol_contraction": lambda: vol_contraction(0.6),
    "us_capitulation_volume": lambda: capitulation(-0.12, 2.5),
    "baseline_high_relvol": lambda: high_relative_volume(2.0),
    "baseline_random": lambda: pseudo_random(0.02),
}
