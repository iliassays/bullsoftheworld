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

Genuine 2023-2024 validation is authoritative. The post-2024 window is reused historical evidence
and cannot rescue failed validation. A v2 historical pass only permits fresh forward collection;
it cannot create a target or trade. Failure is retained and will not be repaired by tuning this
same historical sample.
