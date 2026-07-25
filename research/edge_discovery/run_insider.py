"""Run Family I — the preregistered insider-purchase battery.

    .venv/bin/python research/edge_discovery/run_insider.py

Research-only. Writes artefacts to the scratchpad, changes no production code, and flips no
strategy status. The four specs were frozen (hashes recorded) before the Form 4 extract was
pulled; this script prints each hash alongside its result so that is checkable.

Before scoring anything it runs two guards:

* **Harness null** — the same random-selection baseline the main battery uses, at horizon 63, so
  a Family I number is only believed if the harness returns ~0 for a rule with no mechanism at
  this horizon.
* **Drift check** — the polars routine classifier is compared against production
  ``bulls.analytics.fintel_insider_algo.routine_owner_ciks`` on a sample of issuers. A mismatch
  aborts the run rather than quietly measuring something the shipped code does not do.
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from edge_discovery import dataset, harness, insider_signals, signals
from edge_discovery.hypotheses import INSIDER

OUT_DIR = Path(
    "/private/tmp/claude-501/-Users-iliashossain-project-millionare-bulls-of-the-world"
    "/f1af2921-60e8-4368-add0-91f36b8a6688/scratchpad/results"
)
HORIZON = 63
# Deciles 0-1 cost 100-150bps round trip; preregistered as excluded.
MIN_LIQ_DECILE = 2
MIN_PRICE = 1.0


def build_panel() -> pl.DataFrame:
    bars = dataset.with_features(dataset.us_bars(), price_col="adjusted_close")
    bars = dataset.add_atr(bars)
    bars = dataset.forward_returns(bars, (HORIZON,), price_col="adjusted_close")
    return harness.attach_buckets(bars)


def eligible_universe(panel: pl.DataFrame) -> pl.DataFrame:
    gate = signals.eligible(min_liq_decile=MIN_LIQ_DECILE, min_price=MIN_PRICE, min_bars=252)
    universe = panel.filter(gate)
    return harness.attach_control(universe, HORIZON)


def drift_check(sample: int = 400) -> dict:
    """Assert the research routine classifier agrees with the shipped production one."""
    from bulls.analytics.fintel_insider_algo import InsiderTrade, routine_owner_ciks

    frame = insider_signals.purchases()
    owners = frame["owner_cik"].unique().sort().head(sample).to_list()
    subset = frame.filter(pl.col("owner_cik").is_in(owners))

    as_of = dt.date(2026, 7, 25)
    year = as_of.year
    research_routine = {
        row["owner_cik"]
        for row in insider_signals.routine_owner_years(subset)
        .filter(pl.col("year") == year)
        .to_dicts()
    }

    trades = [
        InsiderTrade(
            owner_cik=row["owner_cik"],
            known_at=dt.datetime.combine(row["known_date"], dt.time(21), tzinfo=dt.UTC),
            transaction_date=row["transaction_date"],
            code="P",
            acquired_disposed="A",
            shares=row["shares"],
            is_officer=row["is_officer"],
            is_director=row["is_director"],
        )
        for row in subset.to_dicts()
    ]
    production_routine = set(routine_owner_ciks(trades, as_of=as_of))

    # Production classifies on all history <= as_of; research requires the run to complete before
    # the signal YEAR. So production is a superset: it may additionally flag owners whose run
    # completed during 2026 itself. Any owner research flags that production does not is a bug.
    unexpected = research_routine - production_routine
    return {
        "owners_sampled": len(owners),
        "research_routine": len(research_routine),
        "production_routine": len(production_routine),
        "research_only": sorted(unexpected),
        "agrees": not unexpected,
    }


def null_calibration(universe: pl.DataFrame) -> harness.Result | None:
    """Deterministic ~2% random selection at horizon 63 — must come back ~0."""
    spec = harness.Spec(
        key="baseline_random_h63",
        name="Baseline: random eligible, horizon 63",
        market="US",
        family="baseline",
        mechanism="No mechanism. Harness calibration at this horizon.",
        direction="long",
        horizon=HORIZON,
        universe="as Family I",
        entry_rule="Deterministic hash of (code, date) selects ~2%.",
        exit_rule=f"Time exit at {HORIZON} sessions.",
        invalidation="None.",
        expected_failure="None — this is the null.",
    )
    events = universe.filter(
        (pl.col("code") + pl.col("date").cast(pl.String)).hash(seed=harness.RNG_SEED) % 50 == 0
    )
    return harness.evaluate(events, spec, "all")


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    drift = drift_check()
    print(f"drift check: {drift}")
    if not drift["agrees"]:
        raise SystemExit("ABORT: research routine classifier disagrees with production module")

    coverage = insider_signals.coverage_report()
    print("\ncoverage:", json.dumps(coverage, indent=2))

    panel = build_panel()
    universe = eligible_universe(panel)
    meta = dataset.panel_meta("US")
    print(
        f"\npanel: {meta.codes} codes, {meta.sessions} sessions, "
        f"{meta.first_session}..{meta.last_session}"
    )
    print(f"survivorship: {meta.survivorship}")
    print(f"eligible rows: {universe.height:,}")

    null = null_calibration(universe)
    if null is not None:
        print(
            f"\nNULL baseline_random_h63: excess={null.mean_excess_bps:+.1f}bps "
            f"t={null.t_stat:.2f} ci=[{null.ci_low_bps:.1f},{null.ci_high_bps:.1f}] "
            f"n={null.events:,}"
        )

    events_by_key = insider_signals.build_events()
    ledger: list[dict] = []

    for registered in INSIDER:
        spec = registered.spec
        raw = events_by_key[spec.key]
        attached = insider_signals.attach_to_panel(universe, raw)
        print(f"\n{spec.key}  hash={spec.spec_hash()}")
        print(f"  filing-date events: {raw.height:,}  on-panel events: {attached.height:,}")
        if attached.is_empty():
            ledger.append(
                {
                    "spec_key": spec.key,
                    "spec_hash": spec.spec_hash(),
                    "window": "n/a",
                    "outcome": "no_events",
                }
            )
            continue
        for window, frame in harness.split_events(attached, harness.US_WINDOWS).items():
            if frame.is_empty():
                continue
            result = harness.evaluate(frame, spec, window)
            if result is None:
                continue
            ledger.append(result.as_row())
            print(
                f"  {window:11s} n={result.events:6d} d={result.signal_dates:4d} "
                f"excess={result.mean_excess_bps:+8.1f}bps t={result.t_stat:+6.2f} "
                f"ci=[{result.ci_low_bps:+8.1f},{result.ci_high_bps:+8.1f}] "
                f"3x={result.cost_3x_bps:+8.1f} hit={result.hit_rate:.0%}"
            )

    payload = {
        "coverage": coverage,
        "drift_check": drift,
        "null_baseline": null.as_row() if null else None,
        "ledger": ledger,
        "spec_hashes": {r.spec.key: r.spec.spec_hash() for r in INSIDER},
    }
    (OUT_DIR / "insider_ledger.json").write_text(json.dumps(payload, indent=2, default=str))
    print(f"\nWrote {OUT_DIR / 'insider_ledger.json'}")


if __name__ == "__main__":
    main()
