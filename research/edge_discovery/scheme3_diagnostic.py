"""Why is the daily slate empty? Scheme-3 firing-frequency diagnostic.

    .venv/bin/python research/edge_discovery/scheme3_diagnostic.py

Research-only. The live ``quality_reversal_eod`` paper book has taken ZERO trades since
2026-07-06, and ``rebound`` likewise. This measures whether that is a bug or the rule's designed
behaviour, by counting how often each of Scheme-3's four gates passes historically and how often
all four align on the same session.

Point-in-time discipline: ``company_financials`` carries a ``fiscal_year`` but no publication
date, so there is no honest way to know exactly when EPS became public. The spec's own rule is
used instead — at a signal date in calendar year Y, only fiscal years <= Y-1 are eligible. That is
a 6-18 month lag, conservative enough that it cannot leak a future report.
"""

from __future__ import annotations

import sys
from pathlib import Path

import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from edge_discovery import dataset
from edge_discovery.dataset import DATA_DIR

# Scheme-3 thresholds, verbatim from docs/research/scheme3-strategy-spec.md.
WASHOUT_PCT = -40.0
RANGE_POS_PCT = 15.0
MIN_AVG_VOLUME = 5_000
MIN_BARS = 260
MAX_PE = 25.0


def financials() -> pl.DataFrame:
    """Latest eligible annual report per (code, calendar year), spec lag applied."""
    frame = pl.read_csv(DATA_DIR / "dse_financials.csv")
    years = pl.DataFrame({"cal_year": list(range(2013, 2028))}, schema={"cal_year": pl.Int32})
    return (
        frame.join(years, how="cross")
        .filter(pl.col("fiscal_year") <= pl.col("cal_year") - 1)
        .sort(["code", "cal_year", "fiscal_year"])
        .group_by(["code", "cal_year"])
        .last()
        .select("code", "cal_year", "eps", "nav_per_share")
    )


def build() -> pl.DataFrame:
    bars = dataset.dse_bars()
    frame = bars.with_columns(
        high_252=pl.col("high").rolling_max(252).over("code"),
        low_252=pl.col("low").rolling_min(252).over("code"),
        # The prior 5 bars, EXCLUDING today — today's close must break above them.
        high_5_prior=pl.col("high").shift(1).rolling_max(5).over("code"),
        avg_vol_20=pl.col("volume").rolling_mean(20).over("code"),
        bars_seen=pl.int_range(pl.len()).over("code"),
        cal_year=pl.col("date").dt.year().cast(pl.Int32),
    ).join(financials(), on=["code", "cal_year"], how="left")

    return frame.with_columns(
        drawdown_pct=(pl.col("close") / pl.col("high_252") - 1) * 100,
        range_pos_pct=(pl.col("close") - pl.col("low_252"))
        / (pl.col("high_252") - pl.col("low_252"))
        * 100,
        pe=pl.when(pl.col("eps") > 0).then(pl.col("close") / pl.col("eps")).otherwise(None),
    ).with_columns(
        g_liquid=(pl.col("avg_vol_20") >= MIN_AVG_VOLUME) & (pl.col("bars_seen") >= MIN_BARS),
        g_washout=pl.col("drawdown_pct") < WASHOUT_PCT,
        g_bottom=pl.col("range_pos_pct") < RANGE_POS_PCT,
        g_trigger=pl.col("close") > pl.col("high_5_prior"),
        g_quality=(pl.col("eps") > 0) & (pl.col("nav_per_share") > 0) & (pl.col("pe") <= MAX_PE),
    )


def main() -> None:
    frame = build()
    eligible = frame.filter(pl.col("g_liquid"))
    meta = dataset.panel_meta("DSE")
    print(
        f"DSE panel: {meta.codes} codes, {meta.sessions} sessions, "
        f"{meta.first_session}..{meta.last_session}"
    )
    print(f"rows passing the liquidity/history gate: {eligible.height:,}\n")

    print("Each gate independently, as % of eligible rows:")
    for gate, label in (
        ("g_washout", f"deep washout (>{-WASHOUT_PCT:.0f}% below 52w high)"),
        ("g_bottom", f"near range bottom (<{RANGE_POS_PCT:.0f}% of 52w range)"),
        ("g_trigger", "breaks prior 5-bar high"),
        ("g_quality", f"quality: EPS>0, NAV>0, P/E<={MAX_PE:.0f}"),
    ):
        pct = eligible.select(pl.col(gate).mean()).item()
        print(f"  {label:48s} {pct * 100:6.2f}%")

    # Cumulative funnel, in spec order.
    print("\nCumulative funnel (all gates so far):")
    stack = pl.lit(True)
    for gate, label in (
        ("g_washout", "washout"),
        ("g_bottom", "+ near bottom"),
        ("g_trigger", "+ 5-bar break"),
        ("g_quality", "+ quality"),
    ):
        stack = stack & pl.col(gate)
        hits = eligible.filter(stack)
        dates = hits["date"].n_unique() if hits.height else 0
        print(f"  {label:16s} rows={hits.height:6,}  sessions_with_a_signal={dates:4d}")

    signals = eligible.filter(
        pl.col("g_washout") & pl.col("g_bottom") & pl.col("g_trigger") & pl.col("g_quality")
    )
    sessions = eligible["date"].n_unique()
    with_signal = signals["date"].n_unique()
    print(
        f"\nSessions with >=1 Scheme-3 signal: {with_signal} of {sessions} "
        f"({with_signal / sessions * 100:.1f}%)"
    )
    print(f"=> the slate is EMPTY on {(1 - with_signal / sessions) * 100:.1f}% of sessions.")

    if signals.height:
        per_year = (
            signals.group_by(pl.col("date").dt.year().alias("yr"))
            .agg(signals=pl.len(), names=pl.col("code").n_unique())
            .sort("yr")
        )
        print(f"\nSignals by year:\n{per_year}")
        print(f"\nMost recent signal: {signals['date'].max()}")


if __name__ == "__main__":
    main()
