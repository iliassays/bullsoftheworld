"""Run the preregistered battery and write the experiment ledger.

    .venv/bin/python research/edge_discovery/run_battery.py

Research-only. Writes JSON/CSV artefacts to the scratchpad and prints a summary. Nothing here
touches production, and no result flips any strategy status — promotion remains a human
decision made against the mandate.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from edge_discovery import dataset, harness, signals
from edge_discovery.hypotheses import ALL, PRICE_BASED

OUT_DIR = Path(
    "/private/tmp/claude-501/-Users-iliashossain-project-millionare-bulls-of-the-world"
    "/f8d6f3a8-9d5b-4636-ac60-804fe70fad22/scratchpad/results"
)
HORIZONS = (5, 10, 21)


def build_panel(market: str) -> pl.DataFrame:
    """Featured, bucketed panel with forward returns attached."""
    if market == "US":
        bars = dataset.us_bars()
        price_col = "adjusted_close"
    else:
        bars = dataset.dse_bars()
        price_col = "close"

    frame = dataset.with_features(bars, price_col=price_col)
    frame = dataset.add_atr(frame)
    frame = dataset.forward_returns(frame, HORIZONS, price_col=price_col)
    frame = harness.attach_buckets(frame)
    return frame


def run_spec(panel: pl.DataFrame, registered, windows: harness.Windows) -> list[harness.Result]:
    spec = registered.spec
    signal_fn = signals.SIGNALS.get(spec.key)
    if signal_fn is None:
        return []

    min_liq = (
        5 if "reversal" in spec.key or "pullback" in spec.key or "capitulation" in spec.key else 4
    )
    min_bars = 252
    gate = signals.eligible(min_liq_decile=min_liq, min_bars=min_bars)
    if spec.market == "DSE":
        # DSE has 492 sessions total; a 252-bar warm-up would leave almost nothing. Use 120 and
        # report the reduced history as the limitation it is.
        gate = signals.eligible(min_liq_decile=min_liq, min_price=0.0, min_bars=120)

    # The control must be computed over the ELIGIBLE universe only, otherwise the benchmark
    # includes names the strategy could never have bought.
    universe = panel.filter(gate)
    universe = harness.attach_control(universe, spec.horizon)

    events = universe.filter(signal_fn())
    if events.is_empty():
        return []

    results = []
    for window, frame in harness.split_events(events, windows).items():
        if frame.is_empty():
            continue
        result = harness.evaluate(frame, spec, window)
        if result is not None:
            results.append(result)
    return results


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ledger: list[dict] = []

    for market, windows in (("US", harness.US_WINDOWS), ("DSE", harness.DSE_WINDOWS)):
        panel = build_panel(market)
        meta = dataset.panel_meta(market)
        print(
            f"\n=== {market} panel: {meta.codes} codes, {meta.sessions} sessions, "
            f"{meta.first_session}..{meta.last_session}"
        )
        print(f"    price basis: {meta.price_basis}")
        print(f"    survivorship: {meta.survivorship}")

        for registered in PRICE_BASED:
            if registered.spec.market != market:
                continue
            results = run_spec(panel, registered, windows)
            if not results:
                print(f"  {registered.spec.key:32s} NO EVENTS")
                ledger.append(
                    {
                        "spec_key": registered.spec.key,
                        "spec_hash": registered.spec.spec_hash(),
                        "window": "n/a",
                        "outcome": "no_events",
                    }
                )
                continue
            for result in results:
                ledger.append(result.as_row())
                print(
                    f"  {result.spec_key:32s} {result.window:11s} "
                    f"n={result.events:7d} d={result.signal_dates:5d} "
                    f"excess={result.mean_excess_bps:8.1f}bps "
                    f"t={result.t_stat:6.2f} "
                    f"ci=[{result.ci_low_bps:7.1f},{result.ci_high_bps:7.1f}] "
                    f"3x={result.cost_3x_bps:8.1f}"
                )

    (OUT_DIR / "ledger.json").write_text(json.dumps(ledger, indent=2, default=str))
    pl.DataFrame([r for r in ledger if "events" in r]).write_csv(OUT_DIR / "ledger.csv")

    registry = [
        {
            "key": r.spec.key,
            "market": r.spec.market,
            "family": r.spec.family,
            "runnable": r.runnable,
            "blocked_on": list(r.blocked_on),
            "spec_hash": r.spec.spec_hash(),
            "mechanism": r.spec.mechanism,
        }
        for r in ALL
    ]
    (OUT_DIR / "registry.json").write_text(json.dumps(registry, indent=2))
    print(
        f"\nWrote {len(ledger)} ledger rows and {len(registry)} registered hypotheses to {OUT_DIR}"
    )


if __name__ == "__main__":
    main()
