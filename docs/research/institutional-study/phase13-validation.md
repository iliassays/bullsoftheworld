# Phase 13 — Backtesting & Validation Protocol

**Date:** 2026-07-19. This protocol extends the Atlas admission process (mandate steps 1–7, which
remain binding) with study-specific requirements derived from Phases 1–12's evidence. It exists
because the failure record includes *validation* failures, not just trading failures: Two Sigma's
unsupervised model changes (V, SEC order), the alt-data restated-panel backtest trap (Phase 3),
and the industry's documented habit of selecting the best-looking backtest from an undocumented
search (the mandate's multiple-testing clause).

## 13.1 Data requirements (fail any → the experiment is data-blocked, not approximated)

1. **Point-in-time everything:** signals may use only information timestamped before the signal
   time (filing dissemination time for System A — EDGAR acceptance timestamps, not filing dates;
   corporate-action effective dates for System B; publication-lagged fundamentals for System C).
2. **Survivorship:** universe reconstructed per-date including delisted/acquired names. The
   filings systems are especially exposed — activist targets get acquired at high rates
   (Brav et al. — part of the documented return IS the acquisition premium; excluding acquired
   names deletes the effect).
3. **Corporate-action safety** and split/dividend-adjusted prices with unadjusted preserved
   (fills happen at unadjusted prices).
4. **Vendor-restatement quarantine:** any dataset that silently restates history (13F
   aggregators, estimate feeds) is used only via archived point-in-time snapshots we capture
   ourselves going forward. This is the App Annie/panel lesson generalized (Phase 3).

## 13.2 Cost model (Phase 7's numbers, pessimistic side binding)

- One-way cost = half-spread + fees, with half-spread measured per-name (not assumed); tiers
  stress-tested at 10/30/50 bps one-way. Any system whose edge dies at 30 bps one-way in its
  actual universe is dead (Ancerno institutional realized ~13–30 bps — V; retail in small caps
  is worse, not better, because spread replaces impact — Phase 7 §7.5).
- No fills at the open (adverse selection — Phase 7 §7.4); fills modeled at next observable
  price after signal, never same-bar.
- Decay haircut: published anomaly magnitudes × 0.5 (McLean–Pontiff — V) before any capital
  conclusion is drawn.

## 13.3 Test design

1. **Preregistration before holdout:** the immutable spec (mandate step 2) is committed to the
   repo *before* the untouched test window is run; the commit hash is the preregistration
   receipt. (The repo is the stone tablet — Phase 11.A.5.)
2. **Chronological splits only;** no shuffled CV for anything with serial structure.
3. **All variants logged:** every parameterization attempted is recorded in the experiment file,
   including failures; the final report carries a deflated performance statistic (deflated
   Sharpe or equivalent false-discovery control) computed over the *full* trial count — the
   mandate's clause, made mechanical.
4. **Baselines run in the same harness:** cap-weighted index, 1/N over the same universe, and —
   for System C — a naive single-factor version of itself. Beating only a strawman is a null
   result.
5. **Regime reporting:** results split by the documented stress windows relevant to each system
   (2008-shape, 2020-shape, 2022 rates-shape; factor drought 2017–20 for System C — the AQR arc
   is the stress test, Phase 9). A system unprofitable in one entire regime is reported as such,
   not averaged into respectability.
6. **Small-cap tiers reported separately** (mandate rule, reinforced by Phase 2/3: the anomalies
   and the costs live in the same names — the collision must be visible, not netted).

## 13.4 Forward-shadow requirements (beyond the mandate's step 5)

- Persist intended/constrained/rejected/filled orders (mandate) **plus** the counterfactual
  fill-at-signal price, so implementation shortfall is measured continuously (Perold — the
  institutional metric applied to ourselves).
- Event books (A/B) log *non-events* too: filings screened and rejected, with reasons — the
  disqualification layer is a testable model only if its rejections are recorded (Phase 4).
- The behavior gap is instrumented: every manual override of the system (there should be none;
  there will be some) is a logged event with a written reason. The override log is reviewed in
  the post-mortem cycle — this is the Druckenmiller-2000 counter-device (Phase 11).

## 13.5 Promotion and kill (inherits mandate step 6–7; additions)

- Promotion requires the mandate's gates **plus**: the deflated statistic positive; both nulls
  beaten after stressed costs; and a written "what would make us exit before target"
  answer for the *system itself* (the ninth question of Phase 4, applied at system level).
- Kill triggers additional to the mandate's: the economic mechanism's documented precondition
  disappears (e.g., 13D deadline rules change again; spin-off tax rules change); or the
  validation assumptions are found violated (a data vendor restated history under us).
- **A killed system's record is an asset** — it stays in the repo with its full trial log. The
  study's own method (failures as evidence-5 controls) applies to our failures too.
