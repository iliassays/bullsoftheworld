"""Run sensitivity and walk-forward on the candidates the battery did not already kill.

.venv/bin/python research/edge_discovery/run_robustness.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from edge_discovery import harness, robustness
from edge_discovery.hypotheses import PRICE_BASED
from edge_discovery.run_battery import OUT_DIR, build_panel

# Candidates that were not already rejected outright by the battery: anything whose holdout or
# validation excess was non-negative, plus the owner's preferred trend-pullback family, which is
# carried forward even though it read flat because a null result there is a decision the owner
# specifically asked to be able to make.
CARRY_FORWARD = {
    "us_trend_pullback_20d",
    "us_trend_pullback_h21",
    "us_momentum_12_1",
    "us_momentum_with_pullback",
    "dse_compression_breakout",
    "dse_momentum_12_1",
    "dse_trend_pullback_20d",
}


def main() -> None:
    sensitivity_rows: list[dict] = []
    walk_rows: list[dict] = []

    for market, windows in (("US", harness.US_WINDOWS), ("DSE", harness.DSE_WINDOWS)):
        panel = build_panel(market)
        for registered in PRICE_BASED:
            if registered.spec.market != market or registered.spec.key not in CARRY_FORWARD:
                continue
            print(f"\n--- {registered.spec.key}")
            sens = robustness.sensitivity(panel, registered, windows)
            for row in sens:
                print("  sens ", row)
            sensitivity_rows.extend(sens)

            folds = robustness.walk_forward(panel, registered)
            for row in folds:
                print("  fold ", row)
            walk_rows.extend(folds)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "sensitivity.json").write_text(json.dumps(sensitivity_rows, indent=2))
    (OUT_DIR / "walk_forward.json").write_text(json.dumps(walk_rows, indent=2))
    print(f"\nWrote {len(sensitivity_rows)} sensitivity rows, {len(walk_rows)} fold rows")


if __name__ == "__main__":
    main()
