"""Daily Five — backtest a RANKED shortlist that is never empty.

    .venv/bin/python research/edge_discovery/run_daily_five.py

The problem this addresses is a product problem, not an alpha problem. Scheme-3's four boolean
gates align on 21.6% of sessions (``scheme3_diagnostic.py``), so a researcher opening the app sees
nothing 78% of the time. Requiring a stock to sit at its 52-week low AND break a 5-day high at the
same moment is close to self-contradictory, and it is that gate that removes 96% of candidates.

The fix: keep **quality as a hard gate** (it protects users from loss-making pennies and is the
half of the DSE research that is least regime-dependent), then **rank** the survivors on the same
evidence axes instead of demanding all-or-nothing. Ranking always fills five slots.

What is measured here, honestly:

* Does the ranked shortlist beat a **random draw from the same quality universe**? If not, the
  ranking is decoration and only the quality gate is doing work. This null is the whole test —
  the insider study (Family I) showed that skipping it invites a false positive.
* Does it beat **DSEX buy-and-hold** over the same window?

Two limits stated up front and not negotiable: the DSE panel is 492 sessions with a 260-bar
warm-up, leaving ~232 usable signal sessions, which cannot support a promotion under the mandate;
and DSE bars are raw closes with no corporate-action adjustment, so bonus/rights ex-dates present
as price drops and will be picked up by any rule that likes weakness.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from edge_discovery import dataset, harness
from edge_discovery.scheme3_diagnostic import MAX_PE, MIN_AVG_VOLUME, MIN_BARS, build

OUT_DIR = Path(
    "/private/tmp/claude-501/-Users-iliashossain-project-millionare-bulls-of-the-world"
    "/f1af2921-60e8-4368-add0-91f36b8a6688/scratchpad/results"
)
HORIZON = 63
SHORTLIST_SIZE = 5
# DSE round-trip cost: 0.4% commission plus slippage, applied on entry and exit.
DSE_COST_BPS = 80.0


def quality_universe(frame: pl.DataFrame) -> pl.DataFrame:
    """Liquid, seasoned, profitable, reasonably-priced. The hard gate — never ranked away."""
    return frame.filter(
        (pl.col("avg_vol_20") >= MIN_AVG_VOLUME)
        & (pl.col("bars_seen") >= MIN_BARS)
        & (pl.col("eps") > 0)
        & (pl.col("nav_per_share") > 0)
        & (pl.col("pe") <= MAX_PE)
        & pl.col("drawdown_pct").is_not_null()
        & pl.col("range_pos_pct").is_not_null()
    )


def attach_score(frame: pl.DataFrame) -> pl.DataFrame:
    """Rank within each session on four descriptive axes, equally weighted.

    Every axis is a within-session percentile, so the score is a relative statement about today's
    market and cannot drift as absolute levels change. Weights are equal and disclosed — there is
    no fitted parameter here to overfit.
    """
    pct = lambda col: pl.col(col).rank("ordinal").over("date") / pl.len().over("date")  # noqa: E731
    return frame.with_columns(
        # Deeper drawdown ranks higher (more washed out).
        s_washout=1.0 - pct("drawdown_pct"),
        # Closer to the 52-week bottom ranks higher.
        s_bottom=1.0 - pct("range_pos_pct"),
        # Turn evidence: recent 5-day strength off the base.
        s_turn=pct("ret_5"),
        # Cheapness among the already-profitable.
        s_value=1.0 - pct("pe"),
    ).with_columns(
        score=(pl.col("s_washout") + pl.col("s_bottom") + pl.col("s_turn") + pl.col("s_value")) / 4
    )


def shortlist(frame: pl.DataFrame, size: int = SHORTLIST_SIZE) -> pl.DataFrame:
    return (
        frame.sort(["date", "score"], descending=[False, True])
        .group_by("date", maintain_order=True)
        .head(size)
    )


def random_draw(frame: pl.DataFrame, size: int = SHORTLIST_SIZE) -> pl.DataFrame:
    """The null: `size` names per session from the SAME quality universe, deterministically."""
    return (
        frame.with_columns(
            r=(pl.col("code") + pl.col("date").cast(pl.String)).hash(seed=harness.RNG_SEED)
        )
        .sort(["date", "r"])
        .group_by("date", maintain_order=True)
        .head(size)
    )


def score_basket(events: pl.DataFrame, label: str) -> dict | None:
    """Per-session equal-weight basket return, net of round-trip cost. Block-bootstrapped."""
    fwd = f"fwd_{HORIZON}"
    events = events.drop_nulls([fwd])
    if events.is_empty():
        return None
    per_date = (
        events.group_by("date")
        .agg(gross=pl.col(fwd).mean(), n=pl.len())
        .sort("date")
        .with_columns(net=pl.col("gross") - DSE_COST_BPS / 10_000.0)
    )
    series = per_date["net"].to_numpy()
    if len(series) < 5:
        return None
    rng = np.random.default_rng(harness.RNG_SEED)
    boot = harness._block_bootstrap(series, block=HORIZON, draws=harness.BOOTSTRAP_DRAWS, rng=rng)
    ci_low, ci_high = np.percentile(boot, [2.5, 97.5])
    mean = float(series.mean())
    std = float(series.std(ddof=1))
    return {
        "label": label,
        "sessions": int(per_date.height),
        "positions": int(events.height),
        "names": int(events["code"].n_unique()),
        "mean_net_pct": mean * 100,
        "median_net_pct": float(np.median(series)) * 100,
        "hit_rate": float((series > 0).mean()),
        "t_stat": mean / (std / np.sqrt(len(series))) if std > 0 else float("nan"),
        "ci_low_pct": float(ci_low) * 100,
        "ci_high_pct": float(ci_high) * 100,
    }


def dsex_benchmark(sessions: pl.Series) -> dict | None:
    """Buy-and-hold DSEX over the same 63-session horizons, for the same signal dates."""
    index = dataset.dsex().sort("date")
    index = index.with_columns(fwd=(pl.col("dsex").shift(-HORIZON) / pl.col("dsex") - 1))
    joined = (
        pl.DataFrame({"date": sessions.unique().sort()})
        .join(index.select("date", "fwd"), on="date", how="inner")
        .drop_nulls("fwd")
    )
    if joined.height < 5:
        return None
    series = joined["fwd"].to_numpy()
    return {
        "label": "DSEX buy-and-hold (same dates, same horizon)",
        "sessions": int(joined.height),
        "mean_net_pct": float(series.mean()) * 100,
        "hit_rate": float((series > 0).mean()),
    }


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    frame = build()
    frame = dataset.forward_returns(frame, (HORIZON,), price_col="close")
    frame = frame.with_columns(ret_5=(pl.col("close") / pl.col("close").shift(5) - 1).over("code"))
    universe = attach_score(quality_universe(frame))

    sessions = universe["date"].n_unique()
    per_session = universe.height / sessions
    print(
        f"quality universe: {universe.height:,} rows over {sessions} sessions "
        f"({per_session:.0f} names/session) — the slate is ALWAYS full\n"
    )

    picks = shortlist(universe)
    null = random_draw(universe)
    strict = frame.filter(
        pl.col("g_liquid")
        & pl.col("g_washout")
        & pl.col("g_bottom")
        & pl.col("g_trigger")
        & pl.col("g_quality")
    )

    rows = [
        score_basket(picks, "Daily Five (ranked)"),
        score_basket(null, "NULL: random 5 from same quality universe"),
        score_basket(strict, "Scheme-3 strict (all four gates)"),
    ]
    bench = dsex_benchmark(universe["date"])

    print(
        f"{'basket':46s}{'sess':>6}{'pos':>6}{'mean%':>9}{'t':>7}{'ci_low':>9}{'ci_high':>9}{'hit':>6}"
    )
    for row in rows:
        if row is None:
            continue
        print(
            f"{row['label']:46s}{row['sessions']:6d}{row['positions']:6d}"
            f"{row['mean_net_pct']:+9.2f}{row['t_stat']:+7.2f}"
            f"{row['ci_low_pct']:+9.2f}{row['ci_high_pct']:+9.2f}{row['hit_rate']:6.0%}"
        )
    if bench:
        print(
            f"{bench['label']:46s}{bench['sessions']:6d}{'—':>6}"
            f"{bench['mean_net_pct']:+9.2f}{'—':>7}{'—':>9}{'—':>9}{bench['hit_rate']:6.0%}"
        )

    # Does the ranking add anything over the quality gate alone?
    ranked = next(r for r in rows if r and r["label"].startswith("Daily Five"))
    nul = next(r for r in rows if r and r["label"].startswith("NULL"))
    edge = ranked["mean_net_pct"] - nul["mean_net_pct"]
    print(f"\nranking minus null = {edge:+.2f}pp over {HORIZON} sessions")
    print("=> if this is ~0, only the QUALITY GATE is doing work and the score is presentation.")

    payload = {
        "universe_rows": universe.height,
        "sessions": sessions,
        "names_per_session": per_session,
        "horizon": HORIZON,
        "cost_bps": DSE_COST_BPS,
        "baskets": [r for r in rows if r],
        "benchmark": bench,
        "ranking_minus_null_pp": edge,
    }
    (OUT_DIR / "daily_five.json").write_text(json.dumps(payload, indent=2, default=str))
    print(f"\nWrote {OUT_DIR / 'daily_five.json'}")


if __name__ == "__main__":
    main()
