# DSE demand-signature experiment

Recorded: 26 July 2026

Code:

- `research/edge_discovery/demand_signature.py`
- `scripts/dse_demand_signature_research.py`
- `research/edge_discovery/test_demand_signature.py`

Experiment key: `dse_demand_signature_v1`

## Decision

**Reject this version as a trading strategy. Do not create an Atlas paper target or Agent
Decision from it.**

The experiment found a repeatable *identification* effect: price structure and demand/volume
trajectories together identify stocks that later touch a large upside barrier at materially
higher rates than the eligible universe. That effect did not become a profitable next-open
strategy. Validation and holdout returns were negative after realistic costs, and the holdout
confidence interval crossed zero.

The correct interpretation is:

> Demand Signature v1 may be useful as an early watch-state model. It is not evidence that the
> stock should be bought at the next open.

## Frozen question

Can persistent signed volume, accumulation, supply contraction, absorption, relative strength,
and price structure identify DSE names that reach `+15%` before `-6%` during the next 10 sessions?

The secondary robustness label asks whether they reach `+20%` before `-8%` during the next 20
sessions. "Smart money" is deliberately absent from the model name: daily OHLCV cannot identify
the owner of a trade.

## Causal contract

- Signal after session close; entry at the next session open.
- Daily target/stop ties resolve to the stop because intraday ordering is unknown.
- Features use the signal session or older observations only.
- Training means, scales, coefficients, and the 95th-percentile score threshold use discovery
  data only.
- Validation and holdout labels are purged when their exit crosses a split boundary.
- At most three candidates are selected per session.
- The portfolio has three non-overlapping equal-capital slots.
- Costs are 100bps each side; the stress test uses 150bps each side.
- Raw DSE falls beyond the circuit band invalidate labels and contaminate trailing features.

Six focused tests prove prefix invariance, next-open execution, conservative barrier ordering,
split purging, deterministic fitting, candidate limits, and portfolio slot limits.

## Data

| Field | Value |
|---|---:|
| DSE bars | 195,152 |
| Symbols | 401 |
| Range | 2024-06-27 to 2026-07-26 |
| Discovery training rows | 14,083 |
| Discovery target base rate | 6.35% |
| Frozen score threshold | 0.7725 |

The panel still uses raw DSE closes, lacks point-in-time universe membership, and spans too few
independent regimes. Those defects prevent production admission even if the return gates pass.

## Primary result

| Window | Selected | Target rate | Lift vs base | Mean net | Stress net | Matched net excess |
|---|---:|---:|---:|---:|---:|---:|
| Discovery | 439 | 25.06% | +18.69pp | -1.59% | -2.58% | +0.05% |
| Validation | 226 | 19.91% | +10.16pp | -2.82% | -3.80% | -1.45% |
| Holdout | 221 | 27.15% | +14.57pp | -1.30% | -2.30% | -1.86% |

Holdout selected candidates hit:

- target: 27.15%;
- stop: 61.09%;
- timeout: 11.76%, averaging +2.50% gross.

The holdout net-return bootstrap interval was `-3.41%` to `+0.60%`. The three-slot holdout book
lost `17.95%` while DSEX gained `11.62%`, an excess return of `-29.57pp`. Maximum drawdown was
`32.11%`.

The 20-session robustness label also failed economically: holdout target lift was `+10.96pp`,
but mean net return remained `-0.79%` and stress return `-1.79%`.

## Does volume add information?

The frozen ablation separates price structure, flow trajectories, and their combination:

| Model | Validation lift / net | Holdout lift / net |
|---|---:|---:|
| Price only | +10.17pp / -3.08% | +8.10pp / -2.71% |
| Flow only | +2.53pp / -2.08% | +2.05pp / -1.61% |
| Combined | +10.16pp / -2.82% | **+14.57pp / -1.30%** |

Daily flow evidence is weak by itself. Its interaction with price structure adds genuine
identification power in holdout, but not enough entry quality to survive losses and costs.
Relative strength, proximity to the 20-session high, OBV pressure, market regime, and interaction
terms contributed; no coefficient proves institutional ownership.

## Why identification did not become profit

The classifier optimized the probability of a large upside touch. A tradable strategy instead
needs positive expected utility after:

- entry timing;
- stop frequency and path ordering;
- timeouts;
- transaction costs;
- capital contention;
- benchmark opportunity cost.

V1 entered every selected watch candidate at the next open. That is the failed assumption.
Approximately three out of five selected names stopped before reaching the target. Improving the
score threshold after seeing holdout would be p-hacking, so this trial is closed unchanged.

## Admissible next work

Any successor receives a new key and a new trial count. It must be specified before another
holdout is inspected.

1. Treat the demand score as a **watch-state**, then require a separately defined confirmation
   event before entry. The watch and entry timestamps must both be archived.
2. Train the successor on costed expected utility or ranking quality, not target-touch probability
   alone.
3. Keep the same next-observable fills, slot constraints, matched controls, DSEX benchmark, and
   stress costs.
4. Add block-trade and intraday microstructure only as forward-known overlays; their short
   histories cannot be backfilled into this test.
5. Do not promote until adjusted DSE history, point-in-time universe state, another market regime,
   and at least 60 forward sessions satisfy the mandate.

This is a useful research lead and a failed strategy. Both statements are true.
