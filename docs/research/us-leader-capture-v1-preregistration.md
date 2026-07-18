# US Leader Capture v1 research registration

Status: candidate diagnostic; automation blocked

Registered: 18 July 2026

Methodology: `us-leader-capture-v1`

Engine: `atlas-portfolio-engine-v2`

This record freezes the next prospective form of the strategy after an architecture audit. It is
not represented as an untouched preregistration: two current-universe diagnostics were observed
while separating the generic EOD portfolio constructor from the multi-month holding contract.
Those results are retained below and create an explicit multiple-testing/adaptation gate.

## Economic mechanism

The hypothesis is gradual institutional recognition, not that a chart shape predicts the future.
Quarterly revenue and earnings acceleration can contain information that investors and analyst
forecasts incorporate slowly. He and Narayanamoorthy document future-return predictability from
quarter-over-quarter changes in earnings growth, and Jegadeesh documents post-announcement drift
associated with revenue surprises. Price persistence is required as independent confirmation that
the market is recognizing the information rather than Atlas buying a deteriorating narrative.

Research anchors:

- [Earnings Acceleration and Stock Returns](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3057632)
- [Revenue Growth and Stock Returns](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=314962)
- [Returns to Buying Winners and Selling Losers](https://onlinelibrary.wiley.com/doi/10.1111/j.1540-6261.1993.tb04702.x)
- [AQR time-series momentum data and methodology](https://www.aqr.com/Insights/Datasets/Time-Series-Momentum-Factors-Monthly)

These papers support research, not a profitability claim. Atlas does not currently possess analyst
consensus history, so v1 uses reported year-over-year acceleration and must not be described as an
earnings-surprise or estimate-revision strategy.

## Point-in-time evidence contract

The source is the existing immutable `sec_financial_fact_observations` history. No database copy or
full redownload is required. The adapter replays revisions in `known_at` order and uses only
stand-alone quarterly facts. The SEC notes that Company Facts exposes extracted XBRL filings and is
updated as submissions are disseminated; Atlas still retains its own accepted/known timestamp and
normalization version rather than treating today's API response as historical truth.

Authoritative source: [SEC EDGAR APIs](https://www.sec.gov/search-filings/edgar-application-programming-interfaces)

For each newly knowable filing state:

1. identify the latest reported revenue quarter;
2. compare it with the nearest corresponding quarter 300–430 days earlier;
3. calculate the same year-over-year growth for the preceding quarter;
4. define revenue acceleration as current year-over-year growth minus preceding-quarter
   year-over-year growth;
5. repeat for net income when positive denominators permit a meaningful rate; otherwise record a
   negative-to-positive turnaround explicitly;
6. attach filing URLs, effective period, knowledge time and normalization version;
7. abstain when the evidence is missing, stale, internally incomparable or known after the signal.

Production coverage observed read-only on 18 July 2026:

- 124,565 US quarterly revenue observations across 3,254 codes;
- 255,562 US quarterly net-income observations across 4,087 codes;
- 51,137 US quarterly operating-cash-flow observations across 4,057 codes;
- real-data adapter checks successfully reconstructed histories for NVDA, TSLA, AAPL, MSFT, AMZN
  and META.
- the US security-listing observation table contains 13,059 symbols but only a 17 July 2026
  knowledge snapshot (two recorded removals), so it cannot reconstruct 2018–2026 membership.

## Frozen signal and portfolio contract

Signal time is the completed US daily close. The earliest fill is the next observable adjusted
open. The book is long-only.

Eligibility at signal time:

- at least 252 completed adjusted daily bars;
- close above 50-day average and 50-day average above 200-day average;
- positive 63-session return and at least 10% 126-session return;
- close at least 80% of the 252-session high;
- 20-session volume at least 75% of the 60-session average;
- extension above the 50-day average no greater than 25%;
- latest reported quarter no more than 160 calendar days old;
- revenue year-over-year growth at least 8%;
- revenue acceleration greater than zero;
- positive net-income growth, positive net-income acceleration, or a negative-to-positive net
  income turnaround.

Portfolio construction:

- rank eligible companies cross-sectionally on 63/126-session persistence, proximity to the
  annual high, revenue/earnings acceleration, participation, volatility and extension;
- maximum ten positions;
- rebalance every 20 completed sessions;
- retain an incumbent while it remains eligible and ranks within the top 20, reducing rank churn;
- target 9% per selected name under the 90% gross mandate, subject to 10% name, 25% sector and 5%
  ADV-participation ceilings;
- apply US T+1 settlement, 5 bps fee and 15 bps slippage assumptions;
- apply the mandate's 10% position stop and 18% portfolio drawdown brake at the next observable
  open; never invent a same-close exit.

An economic threshold, evidence field, rebalance interval, rank buffer, sizing method, cost or exit
change requires a new methodology version and a new registered trial. AI may propose the change but
cannot mutate a live target or bypass the registry.

## Diagnostics already observed

The audit used the 100 currently active, highest-current-dollar-volume US symbols with daily data
from 2 January 2018 through 17 July 2026. Sixty-two securities had usable evidence and 692 filing
evidence snapshots were reconstructed. This universe has material current-survivor and selection
bias, so neither the strategy nor its equal-weight benchmark is promotion evidence.

| Attempt | Portfolio ownership | Return | Annualized return | Sharpe | Max drawdown | Executions |
|---|---|---:|---:|---:|---:|---:|
| Architecture diagnostic 1 | Weekly full replacement; inherited inverse-volatility sizing | 26.475% | 2.798% | 0.631 | 6.342% | 1,342 |
| Architecture diagnostic 2 | Monthly 2x rank buffer; mandate-level equal sizing | 63.026% | 5.910% | 0.786 | 11.727% | 453 |

The observable current-survivor equal-weight series returned 670.629% over the same dates. That
benchmark is itself biased and cannot be used as a credible expected-return estimate, but the large
gap is sufficient to reject any claim that v1 has already demonstrated a long-term wealth edge.
The second attempt improved horizon alignment and turnover but remains diagnostic and unvalidated.

## Admission and kill gates

Before historical promotion eligibility:

- reconstruct effective-dated eligible and inactive/delisted US membership;
- use point-in-time sector/classification and all filing revisions through each signal cutoff;
- replace the current-survivor proxy with investable broad-market and equal-weight benchmarks;
- preserve chronological train, validation and untouched test partitions;
- report gross exposure, cash drag, sector/style exposures, turnover, capacity and stressed costs;
- compare with simple broad-market, quality and price-momentum baselines;
- apply the strategy-family multiple-testing adjustment created by the observed diagnostics;
- require at least three years, 20 securities and 30 executions under existing engine gates, with a
  stricter investment-committee review after full regime coverage;
- fail closed on missing corporate-action, universe or knowledge-time coverage.

Kill or revise the candidate when the point-in-time mechanism cannot be reconstructed, stressed
costs remove the effect, performance is concentrated in a few selected survivors, an untouched
test fails the registered benchmark/risk criteria, or forward evidence fails the mandate. No
result in this document authorizes a broker connection, real capital or a profitability claim.
