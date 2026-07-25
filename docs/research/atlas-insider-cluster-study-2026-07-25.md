# Atlas Family I — the insider purchase-cluster study (2026-07-25)

Status: research report. **No production strategy, paper book, agent, or strategy status was
changed by this work.** Reproducible with
`.venv/bin/python research/edge_discovery/run_insider.py` against the read-only production
extract taken 2026-07-25.

Read with `docs/research/atlas-investment-mandate.md` (governing) and
`docs/research/atlas-edge-discovery-2026-07-25.md` (the parent program, whose harness and panel
this reuses unchanged).

---

## A. Verdict

**`us_insider_cluster_buy` is rejected. It failed the kill criterion that was frozen before the
data was pulled.**

The hypothesis was that several insiders buying inside one window is more informative than one —
the Cohen–Malloy–Pomorski (2012) opportunistic/cluster effect, and the mechanism behind Fintel's
insider product. Breadth was the whole claim. Breadth is not there:

| | holdout excess | filter-operative excess | hit rate |
|---|---|---|---|
| I1 cluster (≥2 buyers) | **−39.7bps** (t=−0.40) | +157.5bps (t=2.39) | 42% |
| I2 single buyer | **+75.0bps** (t=0.78) | +167.3bps (t=3.22) | 48% |
| I3 **NULL** 10b5-1 scheduled | −211.1bps | **+471.7bps** (t=3.94) | 54% |
| I4 **NULL** calendar-routine | +344.0bps | +119.9bps (t=1.24) | 49% |

I2's preregistered criterion read: *"Expected positive but materially smaller than I1. If ≥ I1,
reject I1."* It is larger, in both readings. That alone closes the question.

Two independent disqualifications arrived with it, and they matter more than the headline:

1. **The nulls are not null.** I3 and I4 were registered as controls that *must* return ~zero —
   a purchase scheduled months in advance cannot encode current information. I3 came back at
   +471.7bps, larger than the opportunistic set it was meant to bound. Its confidence interval is
   [−704, +1516] on 659 events. The honest conclusion is not "scheduled buys predict"; it is
   **five years of US Form 4 cannot distinguish any of these four groups from each other.**

2. **The central filter did not exist for half the sample.** The Rule 10b5-1 checkbox is
   **0.0% populated before 2023** — 0 of 39,483 filings in 2021–22, against 4.7–9.8% from 2023.
   I1's positive discovery (+162.4bps) and early validation windows were computed with the
   spec's defining filter inoperative, silently mixing scheduled trades into the "opportunistic"
   set. Those windows never measured what the specification described.

## B. Harness calibration — read the numbers against −37, not against 0

The null (deterministic ~2% random selection, horizon 63) returns **−37.0bps**. That is not a
harness fault; it is the correct answer. Decomposed:

```
gross excess (signal − matched control)   −7.7bps   ≈ 0, as a mechanism-free rule must be
average charged cost                      29.3bps   deciles 2-9, round trip
net                                      −37.0bps
```

Costs are charged to the strategy leg only (the control is a measurement baseline, not a traded
portfolio), so a rule with no information scores −(cost). Therefore: **> −37bps means some
information; > 0 means it survives costs.** Every Family I number above should be read against
that, and the gross ≈ 0 result is what certifies the harness at this horizon before any Family I
result is believed.

## C. What was frozen, and when

Spec hashes were computed and written to the scratchpad *before* the Form 4 extract query was
run, so the specifications provably predate the data:

| spec | hash | role |
|---|---|---|
| `us_insider_cluster_buy` | `a08385df87d90213` | primary |
| `us_insider_single_buy` | `59bc997b52d78584` | breadth test |
| `us_insider_plan_buy_null` | `9ec33e7ab6d01fb9` | null |
| `us_insider_routine_buy_null` | `3feefc1268f87ae2` | null |

Registering the two nulls at the same moment as the primary is what made this run decisive. Had
only I1 been tested, its +162/+167bps discovery and validation windows would have looked like a
find, and the holdout would have looked like bad luck.

## D. Data

The blocker recorded on 2026-07-24 was cache logistics, not missing data, and it is now cleared.

| fact | value |
|---|---|
| open-market purchase rows, officer/director, PIT-stamped | 107,705 |
| issuers / panel-matched codes | 5,053 / 5,347 |
| `known_at` range | 2021-07-01 → 2026-07-23 |
| median filing lag (`known_at` − `transaction_date`) | **2 days** — the Section 16 deadline |
| events surviving the liquidity/price/history gate | 10,068 of 21,694 |

The 2-day median lag is the important one: it confirms `known_at` is a genuine point-in-time
acceptance timestamp rather than a backfill stamp, which is what makes a historical run possible
at all. Selection is on `known_at` throughout; filing dates are snapped *forward* to the next
trading session and filled at the session after that, so a Friday-evening filing is never
tradeable at Friday's open.

**Two limits that bound every number here.** The panel is survivors-only (11,072 of 11,072 US
codes trade in the final week; no delisted histories), and insider buying concentrates in
beaten-down small caps whose failures are exactly what is missing — so the favourable bias is
**larger for this family than for any price-based one**. Under the program's asymmetry rule a
negative result is conclusive and a positive result is an upper bound; here the upper bound is
especially loose. Separately, the usable history is five years, not the 2003-onward span the raw
`transaction_date` column suggests.

## E. What survives

`us_insider_single_buy` is recorded as **`diagnostic`**, not promoted and not paper-eligible: a
generic "an officer or director bought on the open market" read is positive (+167.3bps,
t=3.22) and clears the null, but it cannot be attributed to insider information while the
scheduled and routine nulls are equally positive. It may be a small-cap or value tilt the matched
control does not fully absorb. Hit rate is 47–48%, so the mean rests on the right tail.

`bulls.analytics.fintel_insider_algo` stays shipped and stays descriptive. Its exclusions are
mechanistically justified, cheap, and make the output readable and honest — a reader learns that
three officers bought outside a plan, which is a fact. What changed today is that the module's
docstring now records that those exclusions **did not discriminate on our data**, so the score
can never be ranked or charted as if it were measured alpha.

## F. Correction to the parent report

`atlas-edge-discovery-2026-07-25.md` lists Form 4 as "2003 → , 1.72M rows / 7,854 issuers".
The row count is right and the date range is misleading: point-in-time `known_at` coverage begins
**2021-07-01**. Rows with earlier transaction dates are late or amended filings captured after
that date, not history we could have acted on. Any study reading `transaction_date` as its
availability date inherits ~19 years of look-ahead on the oldest rows.

## G. What would change the answer

In priority order:

1. **US delisted price histories.** The one acquisition that converts this family from "can only
   falsify" to "can certify". It is the same blocker the parent report named, and this family is
   where it bites hardest.
2. **More post-2023 history.** The plan filter has existed for ~3.5 years. The nulls need enough
   events for their confidence intervals to close before any filter claim is testable; at the
   current rate that is several more years, not several more months.
3. **Nothing else.** In particular, do not add cluster-window or threshold variants hunting for a
   configuration that works — the mandate forbids it, and with nulls this wide any variant that
   looked good would be indistinguishable from noise.

## H. Reproduction

```bash
.venv/bin/python research/edge_discovery/run_insider.py
```

The runner aborts if the research routine classifier disagrees with the shipped production
`fintel_insider_algo.routine_owner_ciks` (checked on 400 owners; agreed exactly on this run), so
the study cannot drift away from the code it is meant to be testing.
