# Atlas alpha evidence audit - 2026-08-11

Status: **research controls improved; no strategy approved for real capital**.

This record exists to prevent the next engineering or research session from converting an
attractive historical chart into a return claim. Atlas is not authorized to create real orders,
and neither result below passes its own promotion gates.

## What changed

- Strategy-family trial counts now count distinct canonical specifications, not API retries or a
  workspace-wide ordinal.
- DSE shortlist eligibility now uses actual bar counts through each historical date rather than a
  current SMA/52-week proxy.
- U.S. model-selection validation remains separate from post-selection refit diagnostics.
- The U.S. nonlinear artifact records training-label and forward-registration clocks separately.
- Nonlinear experiments now require identical top-ten membership both within one run and across
  independent processes with identical input hashes.
- The DSE shortlist audit now includes a capital-constrained, costed, next-open portfolio rather
  than presenting event-return averages as an executable book.

## DSE Daily Shortlist

Production data through 11 August 2026 contained 360 immutable rows across 72 sessions:

- 60 forward rows and 300 reconstructed rows;
- 270 currently active, ready, non-Z names in the matched eligible universe;
- zero missing selection bars, close mismatches, move mismatches, incomplete slates, or invalid
  ranks; and
- one methodology version, `daily_shortlist_v1`.

### Event diagnostic

Against the same date's non-selected liquid and seasoned universe, equal-weight next-open baskets
showed the following shortlist-minus-control differences:

| Exit | Difference | Block-bootstrap 95% interval |
|---:|---:|---:|
| 1 session | +0.85 pp | +0.37 to +1.34 pp |
| 3 sessions | +1.45 pp | +0.39 to +2.47 pp |
| 5 sessions | +1.31 pp | -0.19 to +2.65 pp |
| 10 sessions | +1.10 pp | -1.06 to +2.99 pp |

This is hypothesis-generating evidence. Reconstructed rows use the current surviving universe and
the rank result is not monotonic. It is not a portfolio return.

### Executable portfolio diagnostic

The frozen diagnostic assumes BDT 1,000,000 capital, rank 1 only, next-session-open entry,
three-session exit, integer shares, 10% target weight, ten positions, at most 2% of trailing traded
value, T+2 sale-proceeds settlement, 40 bps fee and 25 bps slippage per side. The stress scenario
doubles both fee and slippage.

| Evidence | Return | DSEX | Max drawdown | Avg exposure | Trades | Profit factor |
|---|---:|---:|---:|---:|---:|---:|
| Mixed reconstructed + old forward, base costs | +8.03% | +11.38% | 2.65% | 16.75% | 60 | 1.58 |
| Mixed reconstructed + old forward, doubled costs | -0.06% | +11.38% | 5.04% | 16.74% | 60 | 0.99 |
| Existing forward archive, base costs | -1.60% | +1.09% | 2.12% | 16.98% | 9 | 0.64 |
| Existing forward archive, doubled costs | -2.77% | +1.09% | 2.77% | 16.90% | 9 | 0.41 |

The all-five-rank sensitivity earned +7.78% at base costs but lost 16.53% at doubled costs, with
high turnover and only a 1.13 base-cost profit factor. It is not a candidate.

Decision: **do not promote**. The apparent event effect is cost-sensitive and the small existing
forward book is negative. A rank-1, three-session observation policy is registered only for dates
after 11 August 2026. It needs at least 60 matured signal dates, normal and stressed profitability,
positive benchmark/control evidence, acceptable drawdown, and stable capacity before another
admission decision. `orders_enabled` remains false.

## U.S. nonlinear rank challenger

The frozen v2 shallow LambdaRank trial used 54 discovery dates, 24 model-selection dates and 17
reused post-selection diagnostic dates. Its top-ten model-selection basket was positive after
doubled costs, but median daily rank IC was -0.0424 and only 29.2% of dates had positive IC. The
Sharpe lower confidence bound was negative.

An identical rerun then exposed a reproducibility failure:

- source-manifest, benchmark-regime and specification hashes matched;
- rows, dates and selected iteration matched;
- every reused-diagnostic refit score changed; and
- top-ten membership changed on 6 of 17 dates.

Decision: **historical gate failed; promotion blocked**. Do not tune a third version on these same
outcomes. Artifact generation now uses single-thread deterministic training, persists canonical
decision membership, and requires a separately generated matching artifact. The model may be
revisited only with a materially deeper point-in-time panel and a newly registered experiment.

## Why another indicator is not the answer

Atlas has already rejected generic reversal, high-volume continuation, Keltner, moving-average
crossover, compression, Oyster, demand-signature and broad nonlinear-ranking implementations.
Adding indicators increases the trial count faster than it increases independent evidence.

The highest-return engineering work is now:

1. adjusted DSE prices and complete corporate-action lineage;
2. historical inactive/delisted membership and effective-dated security state;
3. point-in-time DSE earnings, ownership and disclosure publication timestamps;
4. continued immutable forward collection for the one registered shortlist policy; and
5. longer U.S. date coverage before another nonlinear model trial.

After those repairs, the next economically grounded candidates are event studies, not chart-label
clones: small/low-attention earnings drift with measurable surprise, and controlled trend pullback
with declining sell participation followed by renewed demand. Each requires a new preregistration
before validation outcomes are inspected.

## Capital boundary

Atlas has useful research infrastructure and useful negative evidence. It does not currently have
a verified strategy that justifies real capital. A discretionary investment must not be recorded
as an Atlas strategy result, and historical model output must not be described as money a user
"would have made."

Relevant research basis:

- Gu, Kelly and Xiu, nonlinear empirical asset pricing: <https://www.nber.org/papers/w25398>
- Jensen, Kelly and Pedersen, implementable efficient portfolios: <https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4187217>
- Bailey et al., probability of backtest overfitting: <https://papers.ssrn.com/sol3/Papers.cfm?abstract_id=2326253>
- Dellavigna and Pollet, investor inattention and earnings drift: <https://www.nber.org/papers/w11683>
- LightGBM paper: <https://proceedings.neurips.cc/paper_files/paper/2017/hash/6449f44a102fde848669bdd9eb6b76fa-Abstract.html>
