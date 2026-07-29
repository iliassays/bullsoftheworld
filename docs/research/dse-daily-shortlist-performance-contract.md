# DSE Daily Shortlist Performance Contract

Status: implemented
Surface: Bulls of Dhaka Ideas, `GET /shortlist/daily/performance`

## What Is Being Measured

The Daily Shortlist is generated after a completed DSE close. It is an attention ranking, not a
forecast and not an executable order list.

Two different return series are kept separate:

1. **Selection-close follow-through**: shortlist close to the exact later DSE session close.
   This describes what happened after the list was produced. It is not executable P&L.
2. **Next-open gross proxy**: next DSE session open to the horizon close. This is closer to an
   executable experiment, but it still excludes fees and slippage, and daily OHLC cannot prove a
   fill.

Horizons are 1, 3, 5 and 10 exact DSE sessions. If a selected company has no bar on the target
session, the observation remains missing. A later company bar is never relabelled as the missing
horizon.

## Primary Cohort

The headline cohort is **independent ticker episodes**. Repeated appearances for one ticker with
no gap longer than 10 DSE sessions form one continuous episode. This prevents a persistent name
from receiving repeated statistical weight.

The API also publishes:

- all appearances, for descriptive archive inspection;
- forward-only independent episodes, for evidence recorded in real time.

Reconstructed history is reported separately because it includes only currently listed names and
therefore has survivorship bias.

## Benchmark And Data Quality

- Benchmark: DSEX close over the same exact session horizon.
- Excess return: selected-name return minus DSEX return.
- Exchange sessions come from market-wide DSE bars. If DSEX is missing for a date, the company
  follow-through remains measurable but benchmark/excess fields stay unavailable and publish their
  smaller sample count.
- Confidence interval: bootstrap of equal-weight selection-date clusters, so five same-day names
  are not treated as five independent market regimes.
- Obvious next-open limit locks are excluded from the next-open proxy.
- Paths containing a raw close-to-close jump above 35% are excluded as possible corporate actions
  or adjustment defects.
- The archive audit reconciles stored selection closes and session moves against `daily_bars`, and
  checks slate completeness and rank continuity.

## Interpretation

Positive historical returns alone are not evidence of selection skill. A rising market can lift
most names, and the shortlist intentionally notices unusual completed-session activity. The UI
therefore leads with DSEX-relative results, sample size, coverage and archive integrity.

Statuses are deliberately conservative:

- `insufficient_history`: fewer than 30 matured 5-session independent observations;
- `no_observed_excess`: mean 5-session excess return is non-positive;
- `positive_but_unproven`: positive excess, but uncertainty or execution evidence is inadequate;
- `positive_diagnostic_requires_forward_validation`: positive excess confidence interval and
  positive next-open mean, still not promoted or described as proven alpha.

No status authorizes a trade. Strategy admission, sizing, costs and forward paper execution remain
separate Atlas responsibilities.
