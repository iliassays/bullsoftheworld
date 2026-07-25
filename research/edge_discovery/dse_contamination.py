"""Forensic measurement of DSE corporate-action contamination in raw closes.

Production holds **zero** adjusted closes for DSE (verified 2026-07-25: 194,756 bars, 0 with
``adjusted_close``). Every DSE price study therefore runs on raw closes, where a bonus issue or
a rights issue prints as a large overnight fall that no holder actually suffered.

This module measures how big that problem is, because "DSE results are caveated" is not a
finding — a number is. The test exploits DSE market structure: the exchange enforces a daily
circuit limit, but *suspends* it on an ex-date so the price can re-base. A one-session fall
deeper than the circuit band is therefore very unlikely to be ordinary trading and very likely
to be a corporate action.

We then check that inference against the announcement archive: if the deep falls cluster near
record-date and corporate-action announcements far more than chance, the circuit-band test is
identifying real ex-dates rather than noise.
"""

from __future__ import annotations

import sys
from pathlib import Path

import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from edge_discovery import dataset

# DSE's circuit band for ordinary sessions. The exchange has used a tiered band; 10% is the
# widest ordinary tier, so a fall beyond it is outside what ordinary trading can produce.
CIRCUIT_BAND = 0.10
# How close an announcement must be to a suspect session to count as corroboration.
WINDOW_DAYS = 10


def suspect_sessions() -> pl.DataFrame:
    """Sessions whose one-day fall exceeds what the circuit band permits."""
    bars = dataset.dse_bars()
    frame = bars.with_columns(
        prev_close=pl.col("close").shift(1).over("code"),
    ).with_columns(gap=(pl.col("close") / pl.col("prev_close") - 1))
    return frame.filter(pl.col("gap") <= -CIRCUIT_BAND).select(
        ["code", "date", "prev_close", "close", "gap", "volume"]
    )


def corroborate(suspects: pl.DataFrame) -> tuple[int, int, float]:
    """How many suspect sessions sit near a corporate-action or dividend announcement."""
    ann = (
        dataset.dse_announcements()
        .filter(pl.col("category").is_in(["corporate_action", "dividend"]))
        .select(["code", "published_at"])
    )

    joined = suspects.join(ann, on="code", how="left").with_columns(
        distance=(pl.col("date") - pl.col("published_at")).dt.total_days().abs()
    )
    matched = (
        joined.filter(pl.col("distance") <= WINDOW_DAYS).select(["code", "date"]).unique().height
    )
    total = suspects.height
    return matched, total, matched / total if total else 0.0


def placebo(suspects: pl.DataFrame) -> float:
    """Base rate: what fraction of *random* sessions sit near such an announcement?

    Without this the corroboration rate is meaningless — DSE announces constantly, so a high
    match rate could simply reflect announcement density rather than a real association.
    """
    bars = dataset.dse_bars().select(["code", "date"])
    sample = bars.sample(n=min(20_000, bars.height), seed=20260725)
    ann = (
        dataset.dse_announcements()
        .filter(pl.col("category").is_in(["corporate_action", "dividend"]))
        .select(["code", "published_at"])
    )
    joined = sample.join(ann, on="code", how="left").with_columns(
        distance=(pl.col("date") - pl.col("published_at")).dt.total_days().abs()
    )
    matched = (
        joined.filter(pl.col("distance") <= WINDOW_DAYS).select(["code", "date"]).unique().height
    )
    return matched / sample.height


def contamination_reach() -> dict:
    """How much of the panel a suspect session can distort.

    A corporate action corrupts every trailing window that spans it, so the damage is not one
    bar — it is the lookback length of whatever feature reads across it.
    """
    suspects = suspect_sessions()
    bars = dataset.dse_bars()
    codes_hit = suspects["code"].n_unique()
    total_codes = bars["code"].n_unique()

    reach = {}
    for lookback in (5, 20, 60, 252):
        # A row is contaminated if a suspect session falls within its trailing window.
        corrupted = suspects.height * lookback
        reach[f"rows_corrupted_lookback_{lookback}"] = corrupted
        reach[f"pct_panel_lookback_{lookback}"] = round(100 * corrupted / bars.height, 2)

    return {
        "suspect_sessions": suspects.height,
        "codes_affected": codes_hit,
        "total_codes": total_codes,
        "pct_codes_affected": round(100 * codes_hit / total_codes, 1),
        "total_bars": bars.height,
        **reach,
    }


def main() -> None:
    suspects = suspect_sessions()
    matched, total, rate = corroborate(suspects)
    base_rate = placebo(suspects)
    reach = contamination_reach()

    print("=== DSE corporate-action contamination ===")
    print(f"Sessions falling more than {CIRCUIT_BAND:.0%} in one day: {total}")
    print(
        f"  ...within {WINDOW_DAYS} days of a corporate-action/dividend announcement: "
        f"{matched} ({rate:.1%})"
    )
    print(f"  ...base rate for random sessions: {base_rate:.1%}")
    print(f"  lift over base rate: {rate / base_rate:.2f}x" if base_rate else "")
    print()
    print(
        f"Codes affected: {reach['codes_affected']} of {reach['total_codes']} "
        f"({reach['pct_codes_affected']}%)"
    )
    print(f"Total DSE bars: {reach['total_bars']:,}")
    for lookback in (5, 20, 60, 252):
        print(
            f"  a {lookback}-session feature is corrupted on ~"
            f"{reach[f'rows_corrupted_lookback_{lookback}']:,} rows "
            f"({reach[f'pct_panel_lookback_{lookback}']}% of the panel)"
        )

    print()
    print("Worst single-session falls (candidate ex-dates):")
    pl.Config.set_tbl_rows(15)
    print(suspects.sort("gap").head(15))


if __name__ == "__main__":
    main()
