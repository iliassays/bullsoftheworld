# US nonlinear rank challenger v2 preregistration

Recorded: 11 August 2026, after diagnosing the v1 constant-tree failure and before evaluating v2.

Status: **offline research only; cannot create an Atlas target, paper position, or order**.

## Why this is a separate trial

V1 applied row weight `1 / names on date` while LightGBM's LambdaRank objective also normalized
each query. On the real 600-1,000 name cross-sections, that made gradients too small to clear the
frozen L1/L2 penalties. A one-tree mechanical check with unit weights produced six leaves and five
used features; no return metric was inspected in that check.

V2 changes only the ranking-query mechanics:

- every row has unit weight;
- `lambdarank_norm=true` explicitly performs query normalization; and
- `bagging_by_query=true` samples complete date queries rather than arbitrary rows.

Everything else remains frozen from v1: universe, causal features, labels, dates, 20-session
horizon, costs, sleeve, shallow tree parameters, comparators, construction, admission criteria and
promotion blockers. The registered family trial count is two, including the implementation-blocked
v1 specification.

## Interpretation rule

The 2023-2024 window is **model-selection validation**, not a pristine holdout: LightGBM uses it
for early stopping, and Atlas uses its frozen metrics for the admission decision. The post-2024
window is reused historical evidence and cannot rescue a failed admission gate. A v2 historical
pass only permits fresh forward collection; it cannot create a target or trade. Failure is retained
and will not be repaired by tuning this same historical sample.

## Artifact-clock correction

The first v2 artifact incorrectly used the last labelled training date as the start of the fresh
forward contract. Artifact schema v2 records two separate clocks:

- `training_label_cutoff`: the latest outcome label available to model fitting; and
- `forward_contract.registered_at` / `starts_after`: the actual time the frozen artifact was
  registered, with collection beginning only on a later market session.

This correction changes no feature, label, model parameter, admission criterion, or historical
metric. The corrected artifact remains a failed historical candidate and cannot trade.

## Reproducibility gate

An immediate rerun with the same source-manifest hash, benchmark-regime hash, specification hash,
row counts and selected iteration changed every post-selection refit score and changed top-ten
membership on 6 of 17 reused diagnostic dates. The model already failed its positive-median-IC
gate; this instability is an independent blocker.

Artifact generation now fits the unchanged specification twice and requires identical top-ten
membership on every model-selection and reused-diagnostic date. That same-process check proved
insufficient because separate server processes still produced small floating-point score changes.
Training therefore uses one CPU thread, and artifact schema v4 persists the exact canonical
decision membership. The first artifact remains `pending_independent_rerun`; a later process with
identical source, regime and specification hashes must reproduce every top-ten set. Score deltas,
same-process overlap and cross-process overlap are recorded in `reproducibility`.

This is a runtime and governance repair, not a third alpha-model trial, and it does not permit
parameter repair after outcomes have been seen.
