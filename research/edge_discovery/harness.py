"""Deterministic experiment harness for edge discovery.

Research-only. The harness computes signals, eligibility, execution, costs and statistics; no
LLM touches a number. It is built around four decisions that determine whether a result means
anything:

**1. Execution is never same-bar.** A signal observed at the close of session ``t`` is filled at
session ``t+1``'s open. :func:`dataset.forward_returns` enforces this and the harness never
receives a price the signal date could not have seen.

**2. The control is date- and characteristic-matched, not the raw universe.** For each signal we
subtract the mean forward return of every *eligible* security in the same session, the same
liquidity decile and the same volatility tercile. This differencing is what makes the US panel
usable at all: signal and control are drawn from the same survivors-only sample, so the level
component of survivorship bias cancels. What does *not* cancel is the selection component — if
the rule preferentially picks names that were unusually likely to delist, the control cannot see
the ones that vanished. Hence the asymmetry the whole program rests on:

    On survivors-only data a negative result is conclusive and a positive result is an upper
    bound. We can kill hypotheses here. We cannot certify them here.

**3. Inference is on a date series, not on events.** Events sharing a session are driven by the
same market move, so treating them as independent observations inflates every t-statistic. The
harness collapses events to one mean-excess observation per signal date, then block-bootstraps
that series with a block length equal to the holding horizon so overlapping holdings do not
manufacture significance either.

**4. Costs are charged to the strategy leg only.** The matched control is a measurement baseline,
not a traded portfolio, so charging it costs would flatter the strategy.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from dataclasses import asdict, dataclass, field

import numpy as np
import polars as pl

# Round-trip cost in basis points by liquidity decile (0 = least liquid, 9 = most liquid).
# Retail-realistic: half-spread plus commission plus slippage, charged on entry and exit.
COST_BPS_NORMAL = {
    9: 10.0,
    8: 12.0,
    7: 15.0,
    6: 20.0,
    5: 25.0,
    4: 35.0,
    3: 50.0,
    2: 70.0,
    1: 100.0,
    0: 150.0,
}
COST_TIERS = {"normal": 1.0, "stress_2x": 2.0, "severe_3x": 3.0}

BOOTSTRAP_DRAWS = 2000
RNG_SEED = 20260725


@dataclass(frozen=True)
class Spec:
    """A preregistered hypothesis. Frozen before any holdout is inspected."""

    key: str
    name: str
    market: str
    family: str
    mechanism: str
    direction: str
    horizon: int
    universe: str
    entry_rule: str
    exit_rule: str
    invalidation: str
    expected_failure: str
    thresholds: dict[str, float] = field(default_factory=dict)

    def spec_hash(self) -> str:
        payload = json.dumps(asdict(self), sort_keys=True, default=str)
        return hashlib.sha256(payload.encode()).hexdigest()[:16]


@dataclass
class Result:
    """Everything an experiment must report, pass or fail."""

    spec_key: str
    spec_hash: str
    window: str
    events: int
    signal_dates: int
    codes: int
    mean_excess_bps: float
    median_excess_bps: float
    hit_rate: float
    t_stat: float
    ci_low_bps: float
    ci_high_bps: float
    ann_excess_pct: float
    excess_ex_top2_bps: float
    max_drawdown_pct: float
    cost_normal_bps: float
    cost_2x_bps: float
    cost_3x_bps: float
    sharpe: float
    notes: str = ""

    def as_row(self) -> dict:
        return asdict(self)


def attach_buckets(frame: pl.DataFrame) -> pl.DataFrame:
    """Assign each row a liquidity decile and volatility tercile *within its own session*.

    Cross-sectional ranking per date is inherently point-in-time: it uses only that day's
    observable dollar volume and trailing volatility.
    """
    return frame.with_columns(
        liq_decile=(pl.col("adv_20").rank("ordinal").over("date") * 10 / pl.len().over("date"))
        .floor()
        .clip(0, 9)
        .cast(pl.Int8),
        vol_tercile=(pl.col("vol_60").rank("ordinal").over("date") * 3 / pl.len().over("date"))
        .floor()
        .clip(0, 2)
        .cast(pl.Int8),
    )


def attach_control(frame: pl.DataFrame, horizon: int) -> pl.DataFrame:
    """Attach the matched-control forward return: the bucket-and-date mean.

    The signal's own forward return is excluded from its control (leave-one-out) so a rule that
    fires on many names in one bucket cannot end up being compared against itself.
    """
    fwd = f"fwd_{horizon}"
    grouped = pl.col(fwd).mean().over(["date", "liq_decile", "vol_tercile"])
    count = pl.col(fwd).count().over(["date", "liq_decile", "vol_tercile"])
    # Leave-one-out mean: (sum - self) / (n - 1)
    loo = pl.when(count > 1).then((grouped * count - pl.col(fwd)) / (count - 1)).otherwise(None)
    return frame.with_columns(control=loo.alias("control"))


def _block_bootstrap(
    series: np.ndarray, block: int, draws: int, rng: np.random.Generator
) -> np.ndarray:
    """Circular block bootstrap of the per-date mean-excess series.

    Block length equals the holding horizon so that the resampled series preserves the
    dependence induced by overlapping positions.
    """
    n = len(series)
    if n == 0:
        return np.array([])
    block = max(1, min(block, n))
    n_blocks = int(np.ceil(n / block))
    starts = rng.integers(0, n, size=(draws, n_blocks))
    offsets = np.arange(block)
    idx = (starts[:, :, None] + offsets[None, None, :]).reshape(draws, -1) % n
    return series[idx[:, :n]].mean(axis=1)


def evaluate(
    events: pl.DataFrame,
    spec: Spec,
    window: str,
    notes: str = "",
) -> Result | None:
    """Score one hypothesis on one chronological window.

    ``events`` must carry ``date``, ``code``, ``fwd_<h>``, ``control`` and ``liq_decile``.
    """
    horizon = spec.horizon
    fwd = f"fwd_{horizon}"
    events = events.drop_nulls([fwd, "control", "liq_decile"])
    if events.is_empty():
        return None

    sign = 1.0 if spec.direction == "long" else -1.0
    cost = pl.col("liq_decile").replace_strict(COST_BPS_NORMAL, default=150.0) / 10_000.0

    scored = events.with_columns(
        gross=(sign * (pl.col(fwd) - pl.col("control"))),
        cost_normal=cost,
    ).with_columns(
        net=pl.col("gross") - pl.col("cost_normal"),
        net_2x=pl.col("gross") - 2 * pl.col("cost_normal"),
        net_3x=pl.col("gross") - 3 * pl.col("cost_normal"),
    )

    per_date = (
        scored.group_by("date")
        .agg(
            mean_net=pl.col("net").mean(),
            mean_2x=pl.col("net_2x").mean(),
            mean_3x=pl.col("net_3x").mean(),
            n=pl.len(),
        )
        .sort("date")
    )
    series = per_date["mean_net"].to_numpy()
    if len(series) < 5:
        return None

    rng = np.random.default_rng(RNG_SEED)
    boot = _block_bootstrap(series, block=horizon, draws=BOOTSTRAP_DRAWS, rng=rng)
    ci_low, ci_high = np.percentile(boot, [2.5, 97.5]) if boot.size else (np.nan, np.nan)

    mean_net = float(series.mean())
    std = float(series.std(ddof=1)) if len(series) > 1 else float("nan")
    t_stat = mean_net / (std / np.sqrt(len(series))) if std and std > 0 else float("nan")

    # Outlier dependence: drop the two largest single-event contributors.
    net_events = scored["net"].to_numpy()
    if net_events.size > 2:
        trimmed = np.sort(net_events)[:-2]
        ex_top2 = float(trimmed.mean())
    else:
        ex_top2 = float("nan")

    # Equity path of the per-date series, for drawdown. Each date is one horizon-long holding,
    # so the path is a proxy for the strategy's own excess-return experience, not a NAV.
    equity = np.cumprod(1 + series)
    peak = np.maximum.accumulate(equity)
    max_dd = float((equity / peak - 1).min() * 100)

    # Annualised: each observation spans `horizon` sessions; 252 sessions per year.
    ann = mean_net * (252.0 / horizon) * 100

    sharpe = (
        float(series.mean() / series.std(ddof=1) * np.sqrt(252.0 / horizon))
        if std and std > 0
        else float("nan")
    )

    return Result(
        spec_key=spec.key,
        spec_hash=spec.spec_hash(),
        window=window,
        events=scored.height,
        signal_dates=per_date.height,
        codes=scored["code"].n_unique(),
        mean_excess_bps=mean_net * 10_000,
        median_excess_bps=float(np.median(net_events)) * 10_000,
        hit_rate=float((net_events > 0).mean()),
        t_stat=float(t_stat),
        ci_low_bps=float(ci_low) * 10_000,
        ci_high_bps=float(ci_high) * 10_000,
        ann_excess_pct=ann,
        excess_ex_top2_bps=ex_top2 * 10_000,
        max_drawdown_pct=max_dd,
        cost_normal_bps=mean_net * 10_000,
        cost_2x_bps=float(per_date["mean_2x"].mean()) * 10_000,
        cost_3x_bps=float(per_date["mean_3x"].mean()) * 10_000,
        sharpe=sharpe,
        notes=notes,
    )


@dataclass(frozen=True)
class Windows:
    """Chronological split. The holdout is inspected once, after every spec is frozen."""

    discovery_end: dt.date
    validation_end: dt.date

    def label(self, date: dt.date) -> str:
        if date <= self.discovery_end:
            return "discovery"
        if date <= self.validation_end:
            return "validation"
        return "holdout"


US_WINDOWS = Windows(discovery_end=dt.date(2022, 12, 31), validation_end=dt.date(2025, 6, 30))
DSE_WINDOWS = Windows(discovery_end=dt.date(2025, 6, 30), validation_end=dt.date(2026, 1, 31))


def split_events(events: pl.DataFrame, windows: Windows) -> dict[str, pl.DataFrame]:
    labelled = events.with_columns(
        window=pl.col("date").map_elements(windows.label, return_dtype=pl.String)
    )
    return {
        name: labelled.filter(pl.col("window") == name)
        for name in ("discovery", "validation", "holdout")
    }
