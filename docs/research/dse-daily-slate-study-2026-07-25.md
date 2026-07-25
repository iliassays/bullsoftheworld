# Why the daily slate is empty, and what to ship instead (2026-07-25)

Status: research report + shipped product fix. Reproducible with
`.venv/bin/python research/edge_discovery/scheme3_diagnostic.py` and
`.../run_daily_five.py` against the read-only DSE extract taken 2026-07-25.

The question that started this: *a researcher opens the app and sees nothing — what is the point
of the system?* That is a fair product criticism, and it turned out to have a precise, measurable
cause.

---

## A. The cause: Scheme-3 almost never fires

The `quality_reversal_eod` paper book has taken **zero trades** since going live 2026-07-06.
`rebound` likewise. That is not a bug. Measured over 232 usable DSE sessions:

| gate | passes, as % of eligible rows |
|---|---|
| deep washout (>40% below 52w high) | 17.59% |
| near range bottom (<15% of 52w range) | 14.37% |
| **breaks prior 5-bar high** | **8.98%** |
| quality (EPS>0, NAV>0, P/E≤25) | 39.66% |

Cumulatively, in spec order:

```
washout                rows 15,366   sessions with a signal 232
+ near bottom          rows  8,513   sessions with a signal 232
+ 5-bar break          rows    305   sessions with a signal  92    <- removes 96%
+ quality              rows     90   sessions with a signal  50
```

**Sessions with at least one signal: 50 of 232 (21.6%). The slate is empty 78.4% of sessions** —
90 signals in two years, under one per week.

The killer is the 5-bar break. Requiring a stock to sit within 15% of its 52-week low *and*
simultaneously break its prior 5-day high is close to self-contradictory. The two conditions
individually pass 14% and 9% of rows; together with washout they pass 0.35%.

## B. Then we tested whether the selection was worth waiting for. It was not.

Three independent tests, all with next-session fill, 80bps DSE round-trip cost, 63-session
horizon, block-bootstrapped confidence intervals.

| basket | sessions | positions | mean net | t | 95% CI | hit |
|---|---|---|---|---|---|---|
| Daily Five (ranked on washout+bottom+turn+value) | 169 | 845 | **+1.92%** | +1.31 | [−11.86, +14.78] | 59% |
| **NULL: random 5 from the same pool** | 169 | 845 | **+3.17%** | +3.22 | [−4.35, +9.63] | 59% |
| Scheme-3 strict (all four gates) | 39 | 78 | **−2.14%** | −0.77 | — | 49% |
| DSEX buy-and-hold, same dates | 169 | — | +1.50% | — | — | 60% |

**The return-seeking ranking was 1.24pp worse than picking at random from the same pool.** And
Scheme-3's strict rule — the thing the empty slate was waiting for — was *negative*. The paper
book taking zero trades has been a mercy, not a malfunction.

## C. The quality gate does not discriminate either, and the whole window is one rally

Stress tests on the load-bearing claim:

```
1) Does the quality gate discriminate? (random 5 from each pool)
   quality pool      +3.17%   t=+3.22
   NON-quality pool  +6.62%   t=+3.46     <- filtering FOR quality removed the better performers
   all liquid        +5.89%   t=+3.39

2) Is it stable? (quality pool, split at 2026-01-31)
   2025-07..2026-01   -0.51%   hit 47%
   2026-02..2026-07  +12.70%   hit 91%    <- 91% of windows positive = everything rose

3) Is it an illiquidity premium? (quality pool by ADV tercile)
   least liquid +4.19%  |  mid +5.79%  |  most liquid +0.27%
```

Every positive number in section B is the February-2026 DSE rally. A 91% hit rate is not a
signal; it is a market where nearly everything went up. The most liquid tercile — the only one an
ordinary user can actually trade at size — returned **+0.27%**.

Note also that the bootstrap CI spans zero for every basket while the t-statistics look
significant. When those two disagree, the sample is too thin and too overlapping to resolve
anything: 169 signal dates with 63-session horizons is a handful of independent observations.

## D. What shipped

`bulls.analytics.daily_shortlist` — an **always-full** daily slate. Verified on the real panel:
**232 of 232 sessions produce 5 names** (Scheme-3: 50 of 232).

The design follows the evidence rather than the hope:

- **Liquidity and seasoning are the only hard gates.** Quality is *not* a gate — the non-quality
  pool outperformed, so excluding those names would be an unevidenced editorial choice dressed as
  risk control. Quality facts ride along on every row so a reader can filter for themselves, and
  loss-making, negative-book-value and extreme-P/E names carry an explicit caution.
- **The ranking is attention, not prediction.** `is_return_claim` is `False` and not
  configurable. The measured base rates from section B are embedded in every response, so a UI
  cannot render the slate without them.
- **Each row states what we do not know**, including that a >8% drop may be a corporate action
  because DSE closes are unadjusted.

Why an attention ranking is still worth shipping: allocating a researcher's next hour across ~400
codes is a real job, and "these five moved, here is the data, here is what we cannot tell you" is
a truthful and useful answer. It is also the descriptive-only posture that is the platform's
actual differentiator. What it must never become is a pick list — ranking by "what changed"
inherits a known *negative* drift (high relative volume measured −169bps in the US program).

A defect found during verification and fixed: the first real slate ranked MLDYEING second and
printed "P/E 820.0" in its **reasons** list, where a naive reader reads it as an endorsement.
Extreme multiples now render as cautions.

## E. Verdict for the registry

`dse_quality_reversal_scheme3` → **rejected**: −2.14% on 78 positions, fires on 21.6% of
sessions, and its strict form is dominated by a random draw from the same universe.

`dse_daily_shortlist_ranked` → **rejected as a return signal**, shipped as a descriptive surface:
1.24pp worse than random.

That makes **45 preregistered hypotheses, 0 promotable** across all three programs.

## F. What would actually change the answer

1. **More DSE history.** 492 sessions spanning one regime cannot separate a signal from a rally.
   This is the binding constraint on every DSE claim, not cleverness.
2. **Corporate-action adjustment factors.** Until DSE closes are adjusted, any rule that likes
   weakness is partly buying bonus and rights ex-dates.
3. **Not more strategy variants.** Three programs have now returned the same answer by different
   routes. The mandate forbids fishing, and with confidence intervals this wide any variant that
   looked good would be indistinguishable from luck.
