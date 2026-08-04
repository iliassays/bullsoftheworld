# DSE Atlas capital-readiness audit - 2026-08-03

Status: **research system operational; no DSE strategy approved for real capital**.

This audit answers a narrow question: has Atlas found a reproducible DSE edge that survives
point-in-time controls, next-observable execution, DSE costs, liquidity constraints and a market
benchmark? The answer as of this date is **no**. One separate product surface, the DSE Daily
Shortlist, has produced a promising continuation hypothesis, but its forward history is far too
short for admission as an Atlas strategy.

This is a system audit, not investment advice or a recommendation to buy a security.

## 1. Production operating state

Read-only production checks on 2026-08-03 established:

| Area | Observed state | Assessment |
|---|---:|---|
| Active DSE symbols | 396; all marked research-ready | Healthy operational universe |
| Latest EOD coverage | 395/396 for 2026-08-03 (99.75%) | Healthy |
| Daily bars | 197,525 rows; 2024-06-27 through 2026-08-03 | Operational, not deep enough for a full regime cycle |
| Analytics | 396 rows for 2026-08-03 | Fresh |
| Point-in-time-complete analytics | 0 | Historical research blocker |
| Intraday capture | 11 sessions; 10 complete; sampled delayed quotes | Useful for monitoring only; not an intraday backtest foundation |
| Adjusted DSE closes | 0 | Critical research blocker |
| Research lifecycle worker | Active | Healthy automation |
| DSE ingestion worker | Active | Healthy automation |

The foundation audit reported zero critical operational issues and one warning for an unclassified
capitalisation tier. That does **not** mean the foundation is promotion-grade for research. The
operational audit measures freshness and serving coverage; it does not cure absent corporate-action
adjustments, shallow history or incomplete historical known-at timestamps.

Additional point-in-time constraints:

- Shareholding and financial histories exist, but historical publication/first-known timing is not
  sufficiently deep to claim that every value was available on the historical signal date.
- Current active/security classifications are available; a complete historical inactive/delisted
  DSE universe is not.
- Raw closes can convert bonus, rights and split ex-dates into false returns, false stops and false
  reversal signals.
- Intraday observations use an ingestion upper-bound timestamp, not an exchange trade timestamp.

## 2. DSE market regime on 2026-08-03

Atlas data described a broad risk-on market that was consolidating rather than accelerating:

- DSEX: 5,885.69; -0.17% on the day, +0.79% over five sessions and +1.49% over 20 sessions.
- DSEX was approximately 3.8% above its 50-session average and 11.6% above its 200-session average.
- 303/395 stocks (76.7%) were above SMA-50 and 344/395 (87.1%) were above SMA-200.
- Turnover was BDT 12,105 million versus a 20-session mean near BDT 12,215 million: normal, not a
  fresh market-wide volume expansion.
- 57 names had RSI at or above 70; only two were at or below 30.

This is a favourable beta regime. It explains why many historical lists look profitable. It does
not prove that Atlas selected the winners before the market moved.

## 3. Strategy evidence scoreboard

| Strategy | Current decision | Evidence |
|---|---|---|
| `dse_reversal_v1` | Active diagnostic book only | Raw-close corporate actions and short history cap it below promotion. Current private NAV/fills were not inspected in this audit because the authenticated DSE workspace was unavailable. |
| `dse_compression_breakout_20d_v1` | Paused | +4.24% at measured costs versus DSEX +8.01%; -3.77 percentage points excess. |
| `dse_selective_compression_v1` | Not admitted | 186 confirmations; zero passed the fixed admission gate. Gates must not be weakened after seeing this result. |
| `dse_demand_signature_v1` | Rejected as entry strategy | Next-open execution lost 1.30% per candidate after costs; holdout slot book -17.95% versus DSEX +11.62%. |
| `dse_keltner_momentum_v1` | Rejected | Holdout mean -0.37%, median -4.11%, excess -1.71pp, profit factor 0.92. |
| `dse_bullish_ma20_50_v1` | Rejected | 24 holdout trades; median -3.24%; -3.30pp versus DSEX; winner-tail dependent. |
| Oyster daily pattern | Rejected | 83 DSE episodes; median 20-session return -1.96%, excess -2.20pp. |
| `dse_trend_pullback` | Diagnostic hypothesis | No admitted/promotion-grade result. |
| `dse_scalp` | Data-blocked | Eleven captured sessions cannot establish an intraday edge or execution model. |
| `dse_quality_value_v1` | Candidate, blocked | Requires point-in-time publication dates and costed portfolio evidence. |
| `dse_pead_v1` | Data-blocked | Requires deep timestamped earnings releases and surprise history. |

**Promoted DSE strategies: 0.** Atlas has found useful negative evidence, not a deployable alpha
engine. Rejecting attractive-looking but losing rules is valuable research work; it is not a
reason to fund the surviving diagnostic by default.

## 4. Daily Shortlist: promising hypothesis, not an edge yet

The Daily Shortlist is separate from Atlas. It ranks five liquid, seasoned names after each close
using absolute daily movement (35%), relative volume (25%), structural-level proximity (25%) and
52-week range extremity (15%). It is intentionally an attention list, not a forecast.

Archive integrity on 2026-08-03:

- 335 rows across 67 sessions; 35 forward rows and 300 reconstructed rows.
- 188 independent ticker episodes.
- Zero missing selection bars, close mismatches, move mismatches, incomplete slates or rank errors.
- Only seven selection dates are genuine forward observations (2026-07-26 through 2026-08-03).

Independent-episode next-open gross follow-through:

| Hold | Mean | Median | Positive | Approx. mean after 1.30% round trip |
|---:|---:|---:|---:|---:|
| 1 session | +0.74% | +0.04% | 50.0% | -0.56% |
| 3 sessions | +2.04% | +0.32% | 50.9% | +0.74% |
| 5 sessions | +2.16% | +0.71% | 53.8% | +0.86% |
| 10 sessions | +3.94% | +1.56% | 56.7% | +2.64% |

The cost deduction uses the preregistered DSE normal assumption: 65 bps one way, 130 bps round
trip. It still omits inability to fill at the recorded open, price-limit queues, market impact,
cash settlement and overlapping daily portfolios.

Matched to the same date's eligible non-selected universe, next-open differences were +0.94pp at
one session, +1.58pp at three, +1.35pp at five and +0.94pp at ten. The five- and ten-session
confidence intervals crossed zero. Rank evidence was not monotonic: reconstructed independent
rank 1 earned +6.59% gross next-open over ten sessions, while rank 5 earned +7.01%. The attention
score therefore has not demonstrated that rank 1 is a better investment than rank 5.

Forward-only evidence is especially immature:

- 27 independent episodes from seven selection dates.
- 24 matured one-session observations: +0.98% mean from next open, below estimated 1.30% round-trip
  cost; median 0.00%.
- 17 matured three-session observations: +1.94% mean, +1.02% median before costs.
- Only ten matured five-session observations from two selection dates; the large positive result
  is not an independent sample.
- No forward episode has matured for ten sessions.

Verdict: **positive diagnostic requiring forward validation**. It is the best current DSE lead,
but it is not authorized for paper or real orders in its present product form.

## 5. Required next experiment

Register a new immutable candidate, `dse_daily_shortlist_continuation_v1`, without changing the
public Daily Shortlist:

1. Freeze the current input ranking and archive methodology before looking at more outcomes.
2. Entry: next observable DSE open only; record limit-locked and unfilled orders explicitly.
3. Test rank 1, equal-weight top five and a matched random/liquidity control as separate sleeves.
4. Pre-register five- and ten-session exits; do not choose the better horizon after the fact.
5. Charge 65 bps one way normally and 100 bps one way under stress.
6. Enforce active non-Z securities, minimum liquidity, no more than 2% of 20-session ADV, settled
   cash, maximum five concurrent positions and a portfolio exposure cap.
7. Benchmark against DSEX and the same-date eligible equal-weight universe.
8. Report net return, excess return, drawdown, turnover, capacity, hit rate, median trade, profit
   factor, rejected orders and block-bootstrap uncertainty.
9. Keep it diagnostic for at least 60 forward market sessions, at least 30 independent matured
   episodes and enough completed fills to evaluate each sleeve. More evidence may be required;
   these are minimums, not automatic approval.
10. Do not promote unless normal and stressed net excess are positive, drawdown is within the
    registered budget, results are not winner-tail dependent and the fixed rule beats both controls.

## 6. Capital decision

Atlas is ready to support **research discipline**, data inspection, watchlists, evidence logs and
paper experiments. It is **not ready to decide real DSE entries or position sizes**. The correct
capital state is zero strategy-directed exposure until a fixed candidate passes the forward gate.

If the owner independently invests in DSE before that point, those decisions must remain outside
the Atlas strategy track record. Mixing discretionary trades into the paper evidence would make
the validation uninterpretable.

This position is consistent with BSEC's own investor-education framing: investors should understand
investment analysis, portfolio management, risks and rewards, and should invest with informed risk
awareness rather than treating a screen as a recommendation:

- <https://sec.gov.bd/home/ieprogram>
- <https://sec.gov.bd/home/investor_alert_warning>

## 7. Audit tooling change

`scripts/audit_dse_daily_shortlist.py` now publishes performance by shortlist rank and disposes the
async database engine on the same event loop. The change is read-only and does not alter archived
slates, strategy state or portfolio records.
