# US nonlinear rank challenger preregistration

Recorded: 11 August 2026, before evaluating this model against the stored panel.

Status: **offline research only; cannot create an Atlas target, paper position, or order**.

## Decision being tested

The current linear U.S. rank model contains weak cross-sectional information, but its genuine
2023-2024 validation portfolio is statistically inconclusive and its 2025-2026 window has already
influenced subsequent research. This experiment asks one bounded question:

> Can a shallow nonlinear ranker capture stable interactions among the same causal momentum,
> liquidity, volatility and trend features in the 20-session deep-liquidity sleeve, after costs,
> without changing the universe, labels or portfolio breadth?

This is not a search for another indicator and it is not a profit claim. Five-session models and
the thinner liquidity sleeves are excluded because the existing evidence rejected them.

## Frozen data contract

- U.S. current active, product-eligible common stocks and ADRs only.
- Completed EOD observations; signal at close `t`, hypothetical entry at adjusted open `t+1`.
- Twenty non-overlapping sessions to the exit; target is net SPY-relative return after the frozen
  trailing-dollar-volume cost schedule.
- Deep-liquidity sleeve only: price at least USD 5, trailing 20-session ADV at least USD 50m,
  normal SPY volatility, and SPY trend state `risk_on` or `transition`.
- The same 16 same-date percentile features as the linear model. No new feature is admitted.
- Discovery labels exit no later than 31 December 2022.
- Validation signals start after discovery and labels exit no later than 31 December 2024.
- Signals after 31 December 2024 are a **reused historical diagnostic**, not a pristine holdout,
  because their outcomes have already been examined during earlier Atlas work.
- Historical membership is current-survivor-only. That bias blocks promotion regardless of the
  reported result.

## Frozen model

One LightGBM LambdaRank trial, grouped by signal date:

- relevance label: within-date net-return decile from 0 to 9;
- learning rate `0.02`, `7` leaves, maximum depth `3`;
- minimum `5,000` rows per leaf, feature fraction `0.8`, row fraction `0.8`;
- L1 `0.1`, L2 `10`, maximum `63` bins;
- maximum `500` trees with validation NDCG early stopping after `50` rounds;
- deterministic seeds, column-wise training and four threads.

Early stopping chooses only the number of trees. There is no hyperparameter grid. After that
choice, the model is refit on discovery plus validation for the reused historical diagnostic.
The registered trial count is one.

## Comparators and construction

- selected ridge ranker using the same features and windows;
- naive 60-session residual momentum;
- top ten equal-weight names at each rebalance.

The deep-liquidity floor makes each USD 500k position in a USD 5m ten-name book no more than 1% of
trailing ADV; ten percent position weight is below the existing 15% cap. Returns are reported at
normal and doubled costs. A rank score is not interpreted as an absolute expected return.

## Historical decision rule

The challenger is only a *candidate for fresh forward collection* if genuine validation has all
of the following:

1. positive median daily rank IC;
2. positive doubled-cost mean top-ten return;
3. at least 20 independent non-overlapping validation rebalance dates;
4. a better doubled-cost top-ten mean than both frozen comparators.

No historical result can authorize paper or real capital. Fresh evidence starts after the
artifact's registration cutoff. Promotion would require a separately registered point-in-time
universe, at least 120 unchanged forward market sessions with 60 matured signal dates, clustered
or block-bootstrap uncertainty, positive doubled-cost return, a confidence bound above zero, and
all normal Atlas risk and governance gates.

## Failure policy

The artifact and failed criteria remain stored. Thresholds, sleeves, horizon or features will not
be changed against the same reused diagnostic. Any such change is a separately preregistered
experiment and increases the strategy-family trial count.
