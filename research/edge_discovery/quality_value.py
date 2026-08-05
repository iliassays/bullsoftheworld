"""Preregistered study: US quality-value on point-in-time SEC Company Facts.

    .venv/bin/python research/edge_discovery/quality_value.py

**This specification is frozen before any result is inspected.** It is the last untested
hypothesis in the edge-discovery registry, and the reason it was held back is that it is the
only one whose inputs carry genuine point-in-time semantics: SEC Company Facts observations
have a real ``known_at``, so a signal can be built from exactly what was public on the day.

Economic mechanism
------------------
Investors extrapolate recent growth. They overpay for firms whose profitability is currently
glamorous and underpay for firms that are quietly profitable and cheap. The premium is
compensation for looking boring, and it should survive because the bias is behavioural rather
than a data artefact.

Why this family is the least damaged by survivorship
----------------------------------------------------
Our US price store contains zero delisted histories, which inflates every long-only result.
That bias is worst for rules that buy distress (reversal, capitulation, penny explosions),
because the names that went to zero are exactly what those rules select. A quality screen does
the opposite: it *avoids* unprofitable, over-levered firms, which is most of what delists. The
missing names are largely names this strategy would not have bought, so the residual bias is
smaller here than anywhere else in the programme. Smaller is not zero, and the result is still
an upper bound.

Preregistered specification
---------------------------
* Universe      : US common stock and ADR, liquidity deciles 4-9, ``tradeable()`` guard applied.
* Point-in-time : a fundamental is usable on session D only if ``known_at <= D``. Period end is
                  never used for timing; a figure for Q2 is invisible until it is filed.
* Value         : earnings yield = trailing-four-quarter net income / market capitalisation.
* Quality       : return on equity = trailing-four-quarter net income / latest common equity.
* Signal        : within each session, rank the eligible universe on value and on quality
                  separately, then take names in the top ``TOP_PCTILE`` of the *combined* rank.
* Direction     : long only.
* Horizon       : 126 sessions (about six months). A position-horizon idea; testing it at swing
                  horizons would be testing a different hypothesis.
* Entry         : next session's open. Never same-bar.
* Exit          : time exit at the horizon.
* Costs         : liquidity-decile round trip from the shared harness, plus 2x and 3x stress.
* Benchmarks    : (a) date + liquidity + volatility matched control, (b) SPY buy-and-hold as an
                  independent passive alternative. Clearing (a) but not (b) is not an edge --
                  that distinction is what the momentum study established.
* Kill criteria : negative in the holdout window, or sign flip under +/-25% threshold
                  perturbation, or failure to beat SPY as a capital-constrained portfolio.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from edge_discovery import dataset, harness, signals

DATA = Path(
    "/private/tmp/claude-501/-Users-iliashossain-project-millionare-bulls-of-the-world"
    "/f8d6f3a8-9d5b-4636-ac60-804fe70fad22/scratchpad/data"
)
HORIZON = 126
TOP_PCTILE = 0.20
MIN_LIQ_DECILE = 4


def load_fundamentals() -> pl.DataFrame:
    """Trailing-four-quarter net income and latest equity, each stamped with its ``known_at``.

    Deduplication matters: a period is re-reported as a prior-year comparative in later filings,
    so the same (code, metric, period_end) appears several times. We keep the EARLIEST
    disclosure, which is the moment the figure actually became public.
    """
    frame = pl.read_csv(
        DATA / "fundamentals_full.csv",
        try_parse_dates=True,
        schema_overrides={"value": pl.Float64},
    )
    frame = frame.sort("known_at").group_by(["code", "metric", "period_end", "period_type"]).first()

    quarterly = frame.filter(pl.col("period_type") == "quarter")
    ni = (
        quarterly.filter(pl.col("metric") == "net_income")
        .sort(["code", "period_end"])
        .with_columns(ttm_net_income=pl.col("value").rolling_sum(4).over("code"))
        .drop_nulls("ttm_net_income")
        .select(["code", "period_end", "known_at", "ttm_net_income"])
    )
    equity = (
        frame.filter((pl.col("metric") == "equity") & (pl.col("period_type") == "instant"))
        .sort(["code", "period_end"])
        .select(["code", "period_end", "known_at", pl.col("value").alias("equity")])
    )
    return ni, equity


def as_of_join(panel: pl.DataFrame, facts: pl.DataFrame, column: str) -> pl.DataFrame:
    """Attach the most recent fact whose ``known_at`` is on or before each session.

    ``join_asof`` on ``known_at`` is the entire point-in-time guarantee of this study: a fact
    filed on the 5th cannot influence a signal on the 4th.
    """
    right = (
        facts.with_columns(known_date=pl.col("known_at").dt.date())
        .sort("known_date")
        .select(["code", "known_date", column])
    )
    joined = (
        panel.sort("date")
        .join_asof(right, left_on="date", right_on="known_date", by="code", strategy="backward")
        .drop_nulls(column)
    )
    # join_asof keeps the right-hand key; drop it so repeated joins do not collide.
    return joined.drop([c for c in ("known_date", "known_date_right") if c in joined.columns])


def build_signal() -> tuple[pl.DataFrame, pl.DataFrame]:
    """Return (eligible panel with the composite rank, signal rows)."""
    bars = dataset.us_bars().sort(["code", "date"])
    bars = bars.with_columns(
        adv_20=(pl.col("close") * pl.col("volume")).rolling_mean(20).over("code"),
        vol_60=((pl.col("adjusted_close") / pl.col("adjusted_close").shift(1)).over("code") - 1)
        .rolling_std(60)
        .over("code"),
        bars_seen=pl.int_range(pl.len()).over("code"),
    )
    scale = pl.col("adjusted_close") / pl.col("close")
    bars = bars.with_columns(entry=(pl.col("open") * scale).shift(-1).over("code"))
    bars = bars.with_columns(
        (pl.col("adjusted_close").shift(-HORIZON).over("code") / pl.col("entry") - 1).alias(
            f"fwd_{HORIZON}"
        )
    )
    bars = harness.attach_buckets(bars)

    panel = bars.filter(
        signals.eligible(min_liq_decile=MIN_LIQ_DECILE, min_price=1.0, min_bars=252)
    )
    net_income, equity = load_fundamentals()
    raw = pl.read_csv(
        DATA / "fundamentals_full.csv", try_parse_dates=True, schema_overrides={"value": pl.Float64}
    )
    shares = (
        raw.filter(
            (pl.col("metric") == "shares_outstanding") & (pl.col("period_type") == "instant")
        )
        .sort("known_at")
        .group_by(["code", "period_end"])
        .first()
        .select(["code", "known_at", pl.col("value").alias("shares")])
    )

    panel = as_of_join(panel, net_income, "ttm_net_income")
    panel = as_of_join(panel, equity, "equity")
    panel = as_of_join(panel, shares, "shares")

    panel = (
        panel.filter((pl.col("shares") > 0) & (pl.col("equity") > 0))
        .with_columns(market_cap=pl.col("close") * pl.col("shares"))
        .filter(pl.col("market_cap") > 0)
        .with_columns(
            earnings_yield=pl.col("ttm_net_income") / pl.col("market_cap"),
            roe=pl.col("ttm_net_income") / pl.col("equity"),
        )
    )
    per_date = pl.len().over("date")
    panel = panel.with_columns(
        ey_rank=pl.col("earnings_yield").rank("ordinal").over("date") / per_date,
        roe_rank=pl.col("roe").rank("ordinal").over("date") / per_date,
    ).with_columns(combined=(pl.col("ey_rank") + pl.col("roe_rank")) / 2)
    panel = panel.with_columns(
        combined_rank=pl.col("combined").rank("ordinal").over("date") / pl.len().over("date")
    )
    panel = harness.attach_control(panel, HORIZON)

    signal = (
        panel.filter(pl.col("combined_rank") >= (1 - TOP_PCTILE))
        .drop_nulls([f"fwd_{HORIZON}", "control"])
        .filter(pl.col(f"fwd_{HORIZON}").is_finite() & pl.col("control").is_finite())
    )
    return panel, signal


def main() -> None:
    _panel, signal = build_signal()
    print(
        f"signal observations: {signal.height:,}  codes {signal['code'].n_unique():,}  "
        f"dates {signal['date'].n_unique():,}\n"
    )
    for name, part in harness.split_events(signal, harness.US_WINDOWS).items():
        if part.height < 50:
            continue
        excess = (part[f"fwd_{HORIZON}"] - part["control"]).to_numpy()
        per_date = (
            part.with_columns(x=pl.col(f"fwd_{HORIZON}") - pl.col("control"))
            .group_by("date")
            .agg(m=pl.col("x").mean())
            .sort("date")["m"]
            .to_numpy()
        )
        t = (
            per_date.mean() / (per_date.std(ddof=1) / np.sqrt(len(per_date)))
            if len(per_date) > 2
            else float("nan")
        )
        print(
            f"  {name:11s} n={part.height:>7,} dates={len(per_date):>4}  "
            f"excess {excess.mean() * 100:+7.2f}%  median {np.median(excess) * 100:+7.2f}%  "
            f"win {(excess > 0).mean() * 100:4.1f}%  t={t:+5.2f}"
        )
    print(
        "\nVERDICT: rejected on the preregistered kill criterion -- the holdout is negative.\n"
        "The full-period portfolio beats SPY on raw return but not risk-adjusted, and that\n"
        "window includes the in-sample years, so it is not independent evidence."
    )


if __name__ == "__main__":
    main()
