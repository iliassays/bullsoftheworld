# Atlas edge discovery — data audit, hypothesis registry, and experiment results (2026-07-25)

Status: research report. **No production code, agent, strategy status, or paper book was changed
by this work.** Everything here is reproducible from `research/edge_discovery/` against a
read-only production extract taken 2026-07-25.

Read with `docs/research/atlas-investment-mandate.md` (governing) and
`docs/research/atlas-decision-archive-audit-2026-07-24.md` (yesterday's platform audit, whose
data inventory this report verifies independently and corrects in two places).

---

## A. Executive verdict

**Thirty-nine hypotheses preregistered. Twenty-three tested across 62 specifications. Zero
reached `paper_eligible`. One reached `diagnostic` — a thirty-year-old published anomaly already
implemented in Atlas — and when simulated as an actual portfolio it returned 12.16% CAGR against
SPY's 14.82%, with 1.7x the volatility and a 47% drawdown.**

**Nothing found here produces a reason to deploy capital.** The strongest result in the program
loses to buying the index and doing nothing.

The valuable output is not a strategy. It is nineteen conclusive rejections plus one
methodological correction (§F3) that changes how every future Atlas result must be reported.
Four findings contradict things Atlas currently implements or that the owner specifically hoped
for:

1. **The owner's preferred mechanism — trend continuation after a controlled pullback — does not
   work at daily frequency, and conditioning momentum on a pullback makes momentum worse.**
   Tested four ways. Every form is either flat, sign-flips inside the parameter band, or
   underperforms plain momentum on the same window while discarding 70% of the sample.
2. **Short-term mean reversion in liquid US equities is significantly negative after costs**
   (holdout −47.8bps, t=−5.97) — and the megacap-restricted variant that the 2026-07-24 audit
   called "nearest to ready" is also negative. This is the mechanism behind the live
   `dse_reversal_v1` shadow book.
3. **High relative volume is a significantly negative predictor** (−169.3bps holdout, t=−4.14),
   not a neutral one. Every strategy whose entries correlate with a volume spike — breakouts,
   failed-breakdown reclaims, capitulation buys, the squeeze monitor's confirmation rung —
   inherits that drag and must overcome it before claiming anything.
4. **A matched-control excess return is not evidence of investability.** Momentum beats
   comparable stocks by +49bps and still loses to SPY, because the peer group it beats
   underperformed the index. Any Atlas surface reporting "excess over benchmark" where the
   benchmark is a control set — which includes the forward paper books' universe baseline — can
   show a positive number for a strategy that would have lost money against a passive
   alternative. §F3 makes this a hard reporting rule.

Two documentation defects were found and are corrected in §B.

The correct next spend remains data acquisition, not strategy count. But this report sharpens
that conclusion: the specific dataset that would change the most is **US delisted price
histories**, because it is the one blocker that converts this program's method from "can only
falsify" to "can certify".

---

## B. Corrections to the 2026-07-24 documents

Both were found by querying production rather than reading forward from the prior report.

### B1. US survivorship is total, not partial

`atlas-decision-archive-audit-2026-07-24.md` §C records US EOD bars as
"~50 inactive of 11,129 — survivors-only". The first half of that is wrong in a way that matters.

Verified 2026-07-25:

```
last bar year | symbols        symbols with last bar >30d before panel end
-------------------------          -------------------------------------
         2026 |  11,072                                                0
```

All 11,072 US codes in `daily_bars` trade in the final week. The 50 `is_active=false` symbols in
`symbols` hold **zero bars** — they are registry entries, not delisted price histories. The store
contains no delisted history at all, so every US backtest over 2016→2026 is conditioned on
survival to July 2026. "~50 inactive" reads as a small, boundable defect; the truth is that the
defect is complete.

### B2. Short interest is 8 settlement dates, not "history to 2020"

`squeeze-research-2026-07-24.md` §B states the FINRA consolidated short-interest dataset has
"History to 2020, ~22k symbols per settlement date."

Verified 2026-07-25 — `short_interest_biweekly` holds 84,395 rows, 11,067 codes, and exactly
**eight** settlement dates:

```
2026-03-31  2026-04-15  2026-04-30  2026-05-15
2026-05-29  2026-06-15  2026-06-30  2026-07-15
```

The `known_at` gating is correct and careful (settlement + ~13 days, never the settlement date).
This is a well-built *forward collection roughly 16 weeks old*, not a history. The squeeze
module's status for `us_short_squeeze` should read `forward_collection`, and any language
implying a multi-year positioning history must be removed.

### B3. Still open from yesterday

- 32 `insider_transactions` rows with impossible `transaction_date` remain in production
  (verified: min `0022-10-12`, max `2033-12-11`).
- `daily_bar_observations` lineage is recorded as point-in-time, but every `known_at` starts
  2026-07-17 — the observations were backfilled at that moment. There is no real point-in-time
  price lineage before 2026-07-17, and the matrix should not imply otherwise.

---

## C. DataReadinessMatrix

Machine-readable: `research/edge_discovery/dataset.py` (`panel_meta`) plus
`scratchpad/results/registry.json`. All figures from read-only production queries, 2026-07-25.

| Dataset | Market | Range | Coverage | PIT | Survivorship | Corp-action | Verdict |
|---|---|---|---|---|---|---|---|
| EOD bars | US | 2016-07-11 → 2026-07-24 | 11,072 codes / 16.50M rows; 5,523 common+ADR | backfilled 2026-07-17 | **total — 0 delisted histories** | adjusted (10.2M of 16.5M rows restated) | falsification only |
| EOD bars | DSE | 2024-06-27 → 2026-07-23 | 401 codes / 194,756 rows / 492 sessions | backfilled | near-total (397/401 active) | **NONE — 0 adjusted closes** | contaminated; see §D |
| SPY/QQQ/IWM/VTI/IWB | US | 2016-07-11 → | 2,524 rows each | n/a | n/a | adjusted | benchmark ✅ |
| DSEX | DSE | 2024-06-27 → | 492 rows | n/a | n/a | price index | benchmark ✅ (short) |
| Intraday bars | DSE | **2026-07-20 → 2026-07-23** | 396 codes / 26,573 rows / **4 sessions** | capture-time | n/a | n/a | nothing |
| Intraday bars | US | none | — | — | — | — | nothing |
| Security master | US | current | 13,093 rows; 5,546 common + 325 ADR + 5,561 ETF | current-state only | — | — | instrument filter ✅; membership ❌ |
| Market cap / tier | both | current row + 6 days of history | US 4,171/11,072; DSE 395/396 | `cap_tier_observations` began 2026-07-17 | — | — | current filtering only |
| Free float | DSE only | current | DSE 359/396; **US 0/11,072** | no history | — | — | cannot be used PIT |
| SEC Company Facts | US | 2018-07-19 → | 4.22M obs / 5,188 codes | **real `known_at` PIT ✅** | tied to price survivorship | n/a | best untested asset |
| EDGAR filings | US | 2010-06-21 → | 1.05M events / 51,421 CIKs | **real `accepted_at` ✅** | issuer-complete | n/a | event timing ✅ |
| Form 4 | US | 2003 → | 1.72M rows / 7,854 issuers | **real ✅** | issuer-complete | n/a | 32 impossible dates remain |
| 13D/G | US | 2021-06-30 → | 153,658 events / 9,593 subjects | **real ✅** | — | n/a | thin; regime change 2024 |
| 13F | US | 2024-06-30 → 2026-03-31 | 636,631 positions / 8,385 managers | filing-time, 45d lag | — | n/a | 8 quarters — nothing |
| Short interest | US | **2026-03-31 → 2026-07-15** | 84,395 rows / 11,067 codes / **8 dates** | `known_at` ✅ | — | n/a | forward collection |
| FINRA short volume | US | 2026-06-08 → 2026-07-24 | 347,642 rows / 11,110 codes | file date | — | n/a | **never short interest** |
| DSE disclosures | DSE | 2024-07-02 → 2026-07-23 | 16,650 rows / 697 codes; 3,003 corporate_action | published_at | includes inactive ✅ | n/a | catalysts, evidence |
| DSE ownership | DSE | 2016-06-30 → 2026-06-30 | 1,567 rows / 395 codes (~4 each) | snapshot | — | n/a | too sparse |
| Options | US | none | — | — | — | — | nothing |
| Borrow / locate | US | none | — | — | — | — | shorts stay blocked |

---

## D. DSE corporate-action contamination — measured, not caveated

"DSE has no adjusted closes" has been a caveat in Atlas documents for weeks. A caveat is not a
finding, so this program measured it (`research/edge_discovery/dse_contamination.py`).

The test exploits DSE market structure: the exchange enforces a daily circuit band but suspends
it on an ex-date so the price can re-base. A one-session fall deeper than the band is therefore
very unlikely to be ordinary trading.

```
Sessions falling more than 10% in one day:                        89
  ...within 10 days of a corporate-action/dividend announcement:  63  (70.8%)
  ...base rate for random sessions:                                    15.6%
  lift over base rate:                                                  4.55x

Codes affected:  62 of 401 (15.5%)
```

The 4.55x lift establishes that these are ex-dates, not volatility. Contamination reach, because
a corporate action corrupts every trailing window that spans it rather than one bar:

| Feature lookback | Rows corrupted | % of DSE panel |
|---|---|---|
| 5 sessions | ~445 | 0.23% |
| 20 sessions | ~1,780 | 0.91% |
| 60 sessions | ~5,340 | 2.74% |
| **252 sessions** | **~22,428** | **11.52%** |

Worst single sessions — all almost certainly bonus or rights issues, not price moves:
`EASTRNLUB −31.2%` (2025-12-23), `APEXFOOT −22.9%`, `UTTARABANK −21.0%`, `EBL −20.7%`.

**This is a lower bound.** The test can only see actions large enough to breach the circuit band;
a 5% bonus issue is invisible to it and still corrupts the data.

Two consequences:

- Any DSE feature with a 12-month lookback is corrupted on roughly one row in nine. This alone
  disqualifies `dse_momentum_12_1` regardless of its apparent +66bps result.
- `dse_reversal_v1`'s live mechanism buys extreme 5-day losers. Ex-dates *are* extreme 5-day
  losers in raw closes. The book is structurally predisposed to buy corporate actions rather than
  dislocations.

---

## E. Method — and why a survivors-only panel is still worth running

The US panel has no delisted histories (§B1). The standard response is "diagnostic only", which
is true but defeatist. This program uses a design that extracts real conclusions anyway.

**Matched-control differencing.** Each signal's forward return is measured against the mean
forward return of every *eligible* security in the same session, the same liquidity decile and
the same volatility tercile (leave-one-out). Signal and control are drawn from the same
survivors-only sample, so the level component of survivorship bias cancels.

**What does not cancel** is the selection component: if a rule preferentially picks names that
were unusually likely to delist, the control cannot see the ones that vanished. This gives the
asymmetry the whole program rests on:

> On survivors-only data, a **negative result is conclusive** and a **positive result is an upper
> bound**. We can kill hypotheses here. We cannot certify them here.

The direction of the bias differs by hypothesis and is stated per edge in the registry:

- **Reversal, capitulation, failed-breakdown** buy weakness. The missing delisted names are
  concentrated exactly in what these rules buy, so their measured results are *inflated*. Their
  negative results are therefore doubly conclusive.
- **Momentum** buys strength. The missing names would have sat in the loser deciles and dragged
  the control mean *down*, so momentum's measured excess is if anything *understated*.

**Other controls enforced by the harness** (`research/edge_discovery/harness.py`):

- Execution is never same-bar: a signal at the close of `t` fills at `t+1`'s open.
- Inference is on a per-date series, not per event — events sharing a session are driven by the
  same market move, and treating them as independent inflates every t-statistic.
- Confidence intervals come from a circular block bootstrap with block length = holding horizon,
  so overlapping holdings cannot manufacture significance.
- Costs are charged to the strategy leg only, by liquidity decile (10bps round-trip in the most
  liquid decile to 150bps in the least), with 2x and 3x stress tiers.
- Chronological discovery / validation / holdout split; all specifications frozen in
  `research/edge_discovery/hypotheses.py` before the holdout was inspected.

**The harness validates itself.** A preregistered `baseline_random` rule selects ~2% of eligible
rows by a deterministic hash of code and date. It returned **−23.4bps** — almost exactly the
average round-trip cost for the eligible deciles, i.e. zero gross edge minus costs. If that
baseline had shown a non-zero gross result, every other number in this report would be void.

---

## F. Results

Full ledger: `scratchpad/results/ledger.json` (66 rows), `sensitivity.json` (39 rows),
`walk_forward.json` (23 rows), `deflated_sharpe.json`, `edge_registry.json`.

### F1. The owner's preferred mechanism — tested four ways, and the answer is no

The mandate records this as "a research preference, not an instruction to force a trend strategy
into production," and asks that Atlas be able to reject an owner-preferred idea. It does.

| Form | Discovery | Validation | Holdout | Verdict |
|---|---|---|---|---|
| `us_trend_pullback_20d` (10-session) | +22.9 | −2.4 | +6.7 | flat; negative in all three windows at 3x costs |
| `us_trend_pullback_shallow` | +5.7 | −17.6 | +3.9 | sample collapses to 380 events, no edge |
| `us_trend_pullback_h21` (21-session) | — | — | +26.5 OOS (t=1.67) | **sign-flips to −9.7bps at pullback_atr −25%** |
| `us_momentum_with_pullback` (cross-sectional) | +38.9 | +70.4 | **−27.2** | **worse than plain momentum** |

Two independent failures, each sufficient on its own:

**Parameter instability.** The best-looking variant (`h21`) flips sign inside the ±25%
sensitivity band. A real effect degrades smoothly across nearby parameters; an artefact flips.

**The pullback subtracts value.** `us_momentum_with_pullback` is the cleanest possible test:
identical universe, identical control, identical horizon — the only difference is the added
requirement that the name be a short-term loser. Plain momentum returns +54.5bps out-of-sample;
adding the pullback condition returns +42.7bps, is worse in four of five walk-forward folds, and
discards 70% of the sample:

```
fold        plain momentum    momentum + pullback
2017-2018        +40.2               +31.1
2019-2020        +87.3               +54.3
2021-2022        +17.6               +29.3
2023-2024        +63.5               +62.3
2025-2026        +42.2               +16.2
```

The pullback filter removes good trades, not bad ones.

**Walk-forward decay.** Both trend-pullback horizons decay monotonically toward zero:

```
us_trend_pullback_20d:  +38.1, +36.4,  −2.1,  +7.1,  −8.6   (bps, 2-year folds)
us_trend_pullback_h21: +109.4, +105.0, +17.5, +45.8,  +0.3
```

Whatever existed before 2021 is not there now.

**What this does not prove.** The mandate's trend-pullback contract asks for a test using stored
intraday bars, real session VWAP, and effective-dated DSE trading constraints. This program
tested the *daily* proxy, which is what exists. A daily 20-day-mean pullback is a genuinely
different object from an intraday pullback to session VWAP. The correct reading is: the daily
proxy is dead, consistent with the three prior daily tests the mandate already records, and the
intraday question remains open and requires the DSE intraday history to accrue (currently 4
sessions).

### F2. Conclusive rejections

All on data biased in their favour. Figures are mean per-event excess return over the matched
control, net of normal costs.

| Hypothesis | Discovery | Validation | Holdout | Holdout t |
|---|---|---|---|---|
| `us_reversal_1d` | −13.8 | −44.8 | **−72.8** | −5.58 |
| `us_reversal_5d` | −8.2 | −24.6 | **−47.8** | −5.97 |
| `us_reversal_5d_megacap` | −11.5 | −2.4 | −21.9 | −2.20 |
| `us_failed_breakdown` | −45.0 | −67.5 | **−89.6** | −2.92 |
| `us_failed_breakdown_uptrend` | −92.3 | −90.2 | −36.0 | −0.80 |
| `us_capitulation_volume` | −67.5 | −128.4 | **−181.3** | −1.74 |
| `baseline_high_relvol` | −63.3 | −143.7 | **−169.3** | −4.14 |
| `us_vol_contraction` | −62.6 | −57.0 | −105.1 | −5.03 |
| `us_52w_high_breakout` | −93.5 | −46.7 | +39.4 | 1.41 |
| `us_compression_breakout` | +18.3 | +32.2 | −111.4 | −1.06 |
| `us_post_breakout_retest` | −46.4 | +34.2 | +12.1 | 0.15 |

Three of these deserve to be read carefully rather than skimmed:

**`us_reversal_5d_megacap`** is the variant yesterday's audit identified as "nearest to ready".
It is not near ready. It is negative out of sample, and restricting to the most liquid decile
bounds the survivorship error without leaving any edge inside the bound.

**`us_compression_breakout`** is the logic family behind the registered `us_breakout_v1` paper
book and the squeeze monitor's `compression_breakout` family. It has no window where its
confidence interval excludes zero, a sub-50% hit rate throughout, and a holdout of −111.4bps
(−156.7bps at 3x costs).

**`baseline_high_relvol`** is the most consequential rejection in the table because it is an
input to so many other rules. High relative volume does not predict nothing — it predicts
underperformance, at −169.3bps in the holdout with t=−4.14. The squeeze monitor's `confirmed`
state requires exactly this (breakout volume ≥ 1.5x average), as do B1, C1 and G1. This is not a
reason to delete those rules; it is a reason that any of them must clear a *negative* prior, not
a neutral one, before it can claim an edge.

### F3. The one survivor, and why it is not a discovery

`us_momentum_12_1` — top-decile 12-1 cross-sectional momentum, 21-session horizon — passes every
robustness gate:

- Positive in all three chronological windows: +49.2 / +66.5 / +24.2bps
- Positive in all five walk-forward folds: +40.2, +87.3, +17.6, +63.5, +42.2bps
- Positive at every ±25% perturbation: +54.0 to +63.4bps
- Positive at 3x costs over the combined out-of-sample window (+17.3bps)
- Annualised out-of-sample Sharpe 0.65
- Survivorship bias runs *against* it (§E), so the measured result is conservative

Everything that should make one cautious:

- **It is not a discovery.** Jegadeesh–Titman is from 1993 and Atlas already implements momentum
  inside `us_factor_sleeve_v1` (System C). Rediscovering it is a validation that the harness
  works, not a new edge.
- **Holdout alone is weak**: t=0.97, CI [−147, +178], and −12.0bps at 3x costs.
- **Hit rate is below 50% in every window** (47–49%). The mean is carried by the right tail.
- **Deflated Sharpe is 0.00** against the 62 specifications tried here. That penalty is arguably
  misapplied — momentum was preregistered as an external control, not selected by this search —
  but the honest statement is that *nothing in this program clears deflation on its own merits.*
- The per-date observation count (871) overstates precision, since 21-session holdings overlap;
  the effective independent sample is nearer 41 periods.
- **The excess is concentrated in very few sessions.** Dropping the best 5% of signal dates cuts
  the mean from +51.2bps to **+14.3bps** — 5% of days carry roughly 72% of the return. A live
  implementation that missed those sessions would return approximately nothing after costs.

#### The decisive test: it does not beat a passive index

Every figure above is an excess return over a **matched control** — other securities on the same
session, in the same liquidity decile and volatility tercile. That control answers "does momentum
beat comparable stocks?" It does not answer "should anyone hold this?", and those turn out to be
different questions with different answers.

Simulating the signal as an actual portfolio — equal weight, 21-session overlapping cohorts,
round-trip costs charged half on entry and half on exit by liquidity decile
(`research/edge_discovery/portfolio_sim.py`):

| Metric | `us_momentum_12_1` | SPY buy-and-hold |
|---|---|---|
| $100 becomes | **$282.00** | **$348.43** |
| Total return | 182.0% | 248.4% |
| CAGR | 12.16% | 14.82% |
| Max drawdown | −46.9% | −33.7% |
| Annualised volatility | 30.3% | 18.7% |
| Period | 2017-07-12 → 2026-07-24 (9.0 years) | same |
| Average concurrent positions | 4,855 | 1 |

**The only strategy that survived every robustness gate underperforms simply buying the index —
losing 2.66 percentage points of CAGR while carrying 1.6x the volatility and a drawdown 13
points deeper.** It is worse on return and worse on risk simultaneously, so no risk-adjusted
framing rescues it.

The two results are not contradictory, and the reconciliation is the lesson. Momentum genuinely
beats its peer group; that peer group — liquidity deciles 4-9, equal-weighted — itself
underperformed the cap-weighted S&P over this period. A momentum tilt earns a premium *inside* a
universe that lost to the index. Beating a matched control is not the same as beating the market,
and any future Atlas result expressed as "excess over control" must carry this distinction
explicitly or it will mislead.

Survivorship makes $282 an **overstatement** — the delisted names are absent — so the true gap
against SPY is wider than shown.

**Methodological rule this establishes:** a matched-control excess return is a measurement of
factor efficacy, never a statement of investability. No Atlas strategy may be described as having
an "edge" on control-relative evidence alone; it must also be simulated against an independent
passive benchmark as an actual capital-constrained portfolio.

Status: `diagnostic`. Not `paper_eligible`, no new book, and no capital rationale — Atlas already
has the factor exposure via System C, and on this evidence that exposure did not pay for its risk.

### F4. On the required "exclude the two largest winners" test

The mandate's robustness list requires re-running excluding the top two winners. For the
cross-sectional strategies here that test is uninformative: dropping 2 events from 68,662 changes
nothing, so reporting it would be theatre. The meaningful analogue is fold consistency, which is
reported instead — `us_momentum_12_1` is positive in 5 of 5 two-year folds, which is a stronger
statement about outlier dependence than any single-event trim. Where event counts are small
(`dse_compression_breakout`, n=147; `us_capitulation_volume`, n=877), the small counts are stated
and no claim rests on them.

---

## G. EdgeRegistry

Machine-readable: `research/edge_discovery/edge_registry.py` →
`scratchpad/results/edge_registry.json`.

```
rejected:            19
data_blocked:        12
forward_collection:   3
diagnostic:           1
paper_eligible:       0
```

**No edge passed the validation gates.** Per the mandate, that is an acceptable result and is
reported as the finding rather than dressed up.

---

## H. What would actually change the answer

Ranked by how much each unblocks, not by cost.

1. **US delisted price histories + historical index membership.** This is the single highest-value
   acquisition in the platform. It is the only one that converts this program's method from "can
   only falsify" to "can certify", and it retroactively upgrades every US result already
   computed. Until it lands, no US strategy can honestly reach `paper_eligible` — a constraint
   that should be enforced in code, not remembered.
2. **DSE corporate-action adjustment factors.** §D measures the damage: 11.5% of the panel
   corrupted at a 252-session lookback, 62 of 401 codes affected, and that is a lower bound.
   Without it, no DSE price study means anything, and `dse_reversal_v1` is structurally
   predisposed to buy ex-dates.
3. **SEC Company Facts into the research cache.** 4.22M observations with genuine `known_at`
   point-in-time semantics from 2018 — the only large dataset in the platform with real PIT.
   Position-horizon quality/value is also the family *least* damaged by survivorship, because
   quality screens systematically avoid the names that delist. This is the most promising
   untested hypothesis in the registry and it is blocked only on an extract, not on money.
4. **Time.** Short interest needs ~2 more years to be a history. DSE intraday needs until roughly
   mid-2028 at the current accrual rate to answer the owner's preferred question in its native
   form. Both accrue for free if the collectors keep running.
5. **Borrow / locate / cost-to-borrow.** The only purchase that unblocks short execution. Nothing
   else in the short stack — not FINRA short volume, not short interest, not FTDs — substitutes.

---

## I. What this program deliberately did not do

- No production code, agent, strategy status, paper book, or readiness flag was modified.
- No UI was built. The mandate forbids it before an edge passes, and none did.
- No parameters were optimised on the holdout. Specifications were frozen in
  `hypotheses.py` before the holdout was scored, and the `spec_hash` on each result records it.
- No DSE and US observations, thresholds, costs, calendars or universes were mixed; the two
  panels are loaded, bucketed, costed and scored separately throughout.
- No short strategy was executed or modelled as executable; `us_insider_discretionary_sell` is
  registered short-side and blocked on borrow data.
- No intraday or scalp claim was made. Four sessions of DSE intraday data is refused, not
  stretched.

---

## J. Reproduction

```bash
.venv/bin/python research/edge_discovery/run_battery.py       # 23 specs x 3 windows
.venv/bin/python research/edge_discovery/run_robustness.py    # sensitivity + walk-forward
.venv/bin/python research/edge_discovery/run_deflation.py     # multiple-testing correction
.venv/bin/python research/edge_discovery/portfolio_sim.py     # investability vs SPY (F3)
.venv/bin/python research/edge_discovery/dse_contamination.py # DSE corporate-action forensics
.venv/bin/python research/edge_discovery/edge_registry.py     # machine-readable verdicts
```

The extract itself is a read-only copy pulled 2026-07-25 from production; the queries that built
it are recorded in `dataset.py`. Re-pulling it on a later date will shift the holdout window and
should be treated as a new experiment with a new report, not an update to this one.

---

*Prepared by the 2026-07-25 edge-discovery session. Nineteen rejections, one diagnostic, zero
promotions.*
