# DSE daily strategy lab — July 2026

Status: superseded diagnostic; do not use for strategy admission

> Superseded on 18 July 2026. This lab ranked a broad usable-data universe before applying an
> absolute company-quality gate, then evaluated a multi-month factor with event-trade stop/target
> mechanics. Those choices answered the wrong investment question for Atlas. The results remain
> below as a preserved failed methodology and multiple-testing record; they are not evidence that
> a quality-first strategy works or fails. The corrected audit is recorded in
> `docs/research/dse-quality-universe-lab-2026-07.md`.

This record preserves the daily-data strategy comparison requested on 18 July 2026. It does not
activate a shadow book, rewrite the existing Atlas reversal book, or authorize capital.

## Data and eligibility

The production dataset contained 192,776 DSE daily OHLCV rows for 401 symbols from 27 June 2024
through 16 July 2026. The strict labs admitted 233 active, non-hidden, non-Z equities after the
security-master and company-profile gates. A security also needed:

- at least 126 genuine observations for the daily factor lab;
- a completed bar on the signal session and a bar on the immediately following DSE session;
- trailing median traded value of at least BDT 5 million;
- no suspicious close-to-close move greater than 35% in the recent integrity window;
- enough capacity for a 2% share of trailing value.

The factor portfolio assumed BDT 10 million, 0.40% fees each side, 0.25% base slippage each side,
0.75% stressed slippage, integer shares, a maximum ten positions, and T+2 sale-proceeds settlement.
Signals formed after a completed close and filled no earlier than the next session open.

Chronological partitions were fixed before the run:

- train: before 1 July 2025;
- validation: 1 July through 31 December 2025;
- test: 1 January 2026 onward.

## Existing daily edge controls

The registered `scripts/dse_edge_lab.py` protocol produced:

| Strategy | Full portfolio | DSEX | Test portfolio | Test DSEX | Decision |
|---|---:|---:|---:|---:|---|
| Deep washout five-session reclaim | +17.14% | +8.01% | +2.39% | +18.83% | Keep diagnostic |
| Capitulation then reclaim | -3.24% | +6.12% | 0.00% | 0.00% | Reject |
| High-participation deep reclaim | +6.33% | +10.44% | -2.32% | +19.36% | Reject |
| Up-regime high-activity continuation | -12.93% | +13.64% | -8.62% | +17.18% | Reject |

The deep-reclaim control was profitable in aggregate but unstable. Its test median trade was
-10.94%, test mean excess return was -0.76%, and the test portfolio materially trailed DSEX.

## Strict daily factor run

The new strict factor lab compared three predeclared families:

1. `quality_value_daily`: low P/E and P/B plus ROE, EPS growth, and cash-dividend consistency. Since
   exact financial publication timestamps are unavailable, it used only fiscal years no later than
   signal year minus two.
2. `defensive_low_vol_daily`: the lowest 60-session volatility among securities with positive
   six-minus-one-month momentum and a close at or above the 126-session average.
3. `momentum_daily_control`: positive six-minus-one-month momentum above the 126-session average,
   included as a negative control rather than a preferred hypothesis.

| Strategy | Executable outcomes | Portfolio | DSEX | Excess | Max drawdown | Decision |
|---|---:|---:|---:|---:|---:|---|
| Conservatively lagged quality-value | 36 | +2.16% | +11.09% | -8.93% | 12.24% | Reject |
| Positive-trend defensive low volatility | 61 | -16.01% | +12.94% | -28.95% | 18.06% | Reject |
| Six-minus-one-month momentum control | 92 | -4.09% | +14.09% | -18.18% | 14.99% | Reject |

No factor passed the chronological outcome, benchmark-relative, median-return, profit-factor, and
stressed-slippage gates.

### All-category sensitivity

The same frozen protocol was rerun across all 359 active equities, including Z-category securities.
History, next-session tradability, turnover, integrity, and capacity gates remained unchanged.

| Strategy | All-category portfolio | DSEX | Excess | Decision |
|---|---:|---:|---:|---|
| Conservatively lagged quality-value | +2.11% | +12.94% | -10.83% | Reject |
| Positive-trend defensive low volatility | -12.40% | +12.94% | -25.34% | Reject |
| Six-minus-one-month momentum control | -6.12% | +14.09% | -20.21% | Reject |

Including Z-category equities did not reveal a hidden edge and did not change any admission
decision. The non-Z universe remains the institution-eligible primary report; the all-category run
is retained as a sensitivity rather than silently discarding otherwise usable history.

## Methodology boundary discovered

The older `scheme2_value.py` screen reported +28.5% for quality-value. That result used same-close
entries, a weaker liquidity endpoint screen, no explicit slippage, and a less conservative
fundamental-availability approximation. Under next-open execution, capacity, T+2 settlement, and a
two-year fiscal-information lag, the portfolio returned only +2.16% while DSEX returned +11.09%.
The older number must not be used as evidence for a new Atlas book.

## Decision at the time of the superseded run

- Add no new DSE daily shadow book from this run.
- Keep `dse_reversal_v1` unchanged as the existing active diagnostic and continue forward evidence.
- Withdraw the quality-value admission conclusion. The broad-universe/event-exit protocol is an
  invalid test of the quality-first, periodically rebalanced candidate. Preserve its numbers only
  as a failed research design; do not retune or cite them as a quality-strategy result.
- Preserve defensive low-volatility and momentum as rejected diagnostics.

## Structural limits

- Only about two years and one dominant DSE regime are present.
- Inactive and delisted history is incomplete, leaving current-symbol survivorship risk.
- Adjusted closes are unpopulated, so corporate-action safety is not authoritative.
- Financial publication timestamps are unavailable; the two-year lag is safe but deliberately
  stale.
- Failure to admit a new strategy is a valid research result, not a reason to search undocumented
  variants until one looks profitable.

## Reproduction

```bash
uv run python scripts/dse_edge_lab.py
uv run python scripts/dse_daily_factor_lab.py
uv run python scripts/dse_daily_factor_lab.py --include-z
uv run pytest -q packages/analytics/tests/test_dse_daily_factors.py \
  packages/analytics/tests/test_dse_edges.py
```
