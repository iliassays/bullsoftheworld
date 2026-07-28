"""EdgeRegistry — the machine-readable verdict on every hypothesis in this program.

Statuses, in the order a hypothesis can move through them:

``rejected``
    Tested and failed. On the US panel this verdict is strong: the survivors-only sample is
    biased *in favour* of long strategies, so a hypothesis that loses money here would lose more
    on a complete sample. These are not "inconclusive" results.
``data_blocked``
    Cannot be tested at all with what exists. The blocking dataset is named.
``forward_collection``
    The dataset exists but is too young for a historical claim; evidence accrues daily.
``diagnostic``
    Survives the robustness gates but cannot be certified for capital — either because the
    survivorship bound makes a positive result an upper bound rather than a measurement, or
    because it is an externally documented effect rather than a discovery here.
``paper_eligible``
    Cleared every gate in the mandate, including an independent benchmark and a complete
    universe. **Nothing in this program reaches this status**, and nothing should be promoted to
    it without the delisted-history acquisition described in the report.

This module is data, not policy. It never flips a production strategy status — promotion stays
a human decision made against `docs/research/atlas-investment-mandate.md`.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

RUN_DATE = "2026-07-28"
METHODOLOGY = "atlas-edge-discovery-v1"


@dataclass(frozen=True)
class Edge:
    key: str
    market: str
    family: str
    status: str
    horizon_sessions: int | None
    verdict: str
    evidence: str
    blocked_on: tuple[str, ...] = ()
    metrics: dict = field(default_factory=dict)


REGISTRY: tuple[Edge, ...] = (
    # ---------------------------------------------------------------- rejected (US, conclusive)
    Edge(
        key="us_bullish_ma20_50_v1",
        market="US",
        family="trend_transition",
        status="rejected",
        horizon_sessions=63,
        verdict="A fresh 20/50 bullish crossover is a lagging trend fact, not an entry edge.",
        evidence="Validation mean/median net -0.37%/-2.76%, cohort excess -1.44% with 95% CI "
        "[-1.98%, -0.86%], profit factor 0.90. Holdout mean/median net -0.31%/-3.19%, "
        "win rate 21.96%, profit factor 0.93, and -0.84% after removing the two largest "
        "winners. Rejected before any UI or paper strategy was created.",
        metrics={
            "validation_excess_pct": -1.4445,
            "holdout_excess_pct": -0.9164,
            "holdout_median_net_pct": -3.1869,
            "holdout_profit_factor": 0.9251,
            "holdout_trades": 1334,
        },
    ),
    Edge(
        key="us_reversal_5d",
        market="US",
        family="mean_reversion",
        status="rejected",
        horizon_sessions=5,
        verdict="Cross-sectional short-term reversal is not merely absent in liquid US equities "
        "— it is significantly negative after costs, and it got worse over time.",
        evidence="Discovery -8.2bps, validation -24.6bps (t=-6.55), holdout -47.8bps (t=-5.97). "
        "Negative in all three chronological windows on a sample biased in its favour: "
        "the worst 5-day losers that later delisted are absent from the panel entirely, "
        "so the true result is worse than measured.",
        metrics={"holdout_excess_bps": -47.8, "holdout_t": -5.97, "events": 62960},
    ),
    Edge(
        key="us_reversal_1d",
        market="US",
        family="mean_reversion",
        status="rejected",
        horizon_sessions=5,
        verdict="Single-session reversal is the worst-performing systematic rule tested.",
        evidence="Discovery -13.8bps, validation -44.8bps (t=-7.83), holdout -72.8bps (t=-5.58). "
        "Buying one-day losers buys the news that caused the drop.",
        metrics={"holdout_excess_bps": -72.8, "holdout_t": -5.58, "events": 31401},
    ),
    Edge(
        key="us_reversal_5d_megacap",
        market="US",
        family="mean_reversion",
        status="rejected",
        horizon_sessions=5,
        verdict="Restricting reversal to the most liquid decile — the variant the 2026-07-24 "
        "audit called 'nearest to ready' — does not rescue it.",
        evidence="Discovery -11.5bps, validation -2.4bps, holdout -21.9bps (t=-2.20). The "
        "liquidity restriction bounds survivorship error but leaves no edge to bound.",
        metrics={"holdout_excess_bps": -21.9, "holdout_t": -2.20, "events": 12478},
    ),
    Edge(
        key="us_failed_breakdown",
        market="US",
        family="failed_breakdown",
        status="rejected",
        horizon_sessions=10,
        verdict="Failed-breakdown reclaims lose money in every window, with and without an "
        "uptrend gate.",
        evidence="Base rule: -45.0 / -67.5 / -89.6bps across discovery/validation/holdout, "
        "holdout t=-2.92. Uptrend-gated variant: -92.3 / -90.2 / -36.0bps. The gate "
        "changed the sample, not the sign.",
        metrics={"holdout_excess_bps": -89.6, "holdout_t": -2.92, "events": 7140},
    ),
    Edge(
        key="us_capitulation_volume",
        market="US",
        family="forced_selling",
        status="rejected",
        horizon_sessions=10,
        verdict="Buying multi-day declines into volume spikes is a large, consistent loser.",
        evidence="-67.5 / -128.4 / -181.3bps across the three windows. This is the hypothesis "
        "most flattered by survivorship — the capitulations that ended in delisting "
        "are wholly absent — and it still loses badly.",
        metrics={"holdout_excess_bps": -181.3, "events": 877},
    ),
    Edge(
        key="baseline_high_relvol",
        market="US",
        family="baseline",
        status="rejected",
        horizon_sessions=21,
        verdict="High relative volume is a significantly NEGATIVE predictor, not a neutral one.",
        evidence="-63.3 / -143.7 / -169.3bps, holdout t=-4.14. Any strategy whose entries "
        "correlate with a volume spike inherits this drag and must overcome it before "
        "it can claim an edge.",
        metrics={"holdout_excess_bps": -169.3, "holdout_t": -4.14, "events": 28738},
    ),
    Edge(
        key="us_52w_high_breakout",
        market="US",
        family="compression_breakout",
        status="rejected",
        horizon_sessions=21,
        verdict="A new 52-week high carries no tradeable premium once costs are charged.",
        evidence="Discovery -93.5bps (t=-4.47), validation -46.7bps, holdout +39.4bps (t=1.41, "
        "CI [-81, 161]). The one positive window is statistically indistinguishable "
        "from zero and follows two significantly negative ones.",
        metrics={"holdout_excess_bps": 39.4, "holdout_t": 1.41},
    ),
    Edge(
        key="us_compression_breakout",
        market="US",
        family="compression_breakout",
        status="rejected",
        horizon_sessions=21,
        verdict="Volatility compression into a volume-confirmed breakout does not survive costs. "
        "This is the logic family behind the registered us_breakout_v1 book.",
        evidence="Discovery +18.3bps (t=0.49), validation +32.2bps (t=0.67), holdout -111.4bps "
        "(t=-1.06); every window's confidence interval spans zero and the holdout is "
        "sharply negative at 3x costs (-156.7bps). Hit rate below 50% in all three "
        "windows.",
        metrics={"holdout_excess_bps": -111.4, "holdout_cost3x_bps": -156.7, "events": 638},
    ),
    Edge(
        key="us_post_breakout_retest",
        market="US",
        family="compression_breakout",
        status="rejected",
        horizon_sessions=21,
        verdict="The retest entry variant does not repair the breakout family.",
        evidence="-46.4 / +34.2 / +12.1bps with confidence intervals spanning zero throughout "
        "(holdout CI [-290, 231] on 1,241 events). No incremental information over the "
        "parent rule, as preregistered.",
        metrics={"holdout_excess_bps": 12.1, "events": 1241},
    ),
    Edge(
        key="us_vol_contraction",
        market="US",
        family="volatility",
        status="rejected",
        horizon_sessions=21,
        verdict="Volatility contraction predicts magnitude, not direction — confirmed, and the "
        "directional read is significantly negative.",
        evidence="-62.6 / -57.0 / -105.1bps. Useful for position sizing; useless as an entry.",
        metrics={"holdout_excess_bps": -105.1},
    ),
    Edge(
        key="us_low_volatility",
        market="US",
        family="volatility",
        status="rejected",
        horizon_sessions=21,
        verdict="No residual low-volatility premium after the control buckets on volatility.",
        evidence="-30.8 / -34.5 / -34.3bps. Largely differenced away by design, as preregistered; "
        "reported as a specification check rather than a market finding.",
        metrics={"holdout_excess_bps": -34.3},
    ),
    Edge(
        key="us_trend_pullback_20d",
        market="US",
        family="trend_pullback",
        status="rejected",
        horizon_sessions=10,
        verdict="THE OWNER'S PREFERRED MECHANISM, daily 10-session form: no edge. Not a loser — "
        "a null.",
        evidence="Excess +22.9 / -2.4 / +6.7bps across discovery/validation/holdout; the "
        "validation and holdout confidence intervals straddle zero (t=-0.17 and "
        "t=+0.42); hit rate 51%/48%/51%. Negative in every window at 3x costs "
        "(-9.6/-33.4/-24.1bps). Walk-forward decays: +38.1, +36.4, -2.1, +7.1, -8.6bps "
        "across five 2-year folds. Whatever was there before 2021 is not there now.",
        metrics={"holdout_excess_bps": 6.7, "folds_bps": [38.1, 36.4, -2.1, 7.1, -8.6]},
    ),
    Edge(
        key="us_trend_pullback_shallow",
        market="US",
        family="trend_pullback",
        status="rejected",
        horizon_sessions=10,
        verdict="Tightening the pullback depth collapses the sample without creating an edge.",
        evidence="380 holdout events, excess indistinguishable from zero, CI [-94, 107].",
        metrics={"holdout_events": 380},
    ),
    Edge(
        key="us_trend_pullback_h21",
        market="US",
        family="trend_pullback",
        status="rejected",
        horizon_sessions=21,
        verdict="The 21-session form is the best-looking trend-pullback variant and it still "
        "fails: it flips sign inside the ±25% parameter band.",
        evidence="Out-of-sample +26.5bps (t=1.67) at registered thresholds, but "
        "pullback_atr -25% gives -9.7bps — a sign flip inside the sensitivity band, "
        "which is an automatic rejection. Walk-forward decays +109, +105, +18, +46, "
        "+0.3bps. Deflated Sharpe 0.00 against 62 trials.",
        metrics={
            "oos_excess_bps": 26.5,
            "sensitivity_min_bps": -9.7,
            "folds_bps": [109.4, 105.0, 17.5, 45.8, 0.3],
            "deflated_sharpe": 0.0,
        },
    ),
    Edge(
        key="us_momentum_with_pullback",
        market="US",
        family="momentum",
        status="rejected",
        horizon_sessions=21,
        verdict="Conditioning momentum on a short-term pullback DEGRADES it. This is the "
        "cleanest available test of the owner's preferred mechanism, and it answers no.",
        evidence="Out-of-sample +42.7bps vs plain momentum's +54.5bps on the same window and "
        "control. Worse in four of five walk-forward folds (+31 vs +40, +54 vs +87, "
        "+29 vs +18, +62 vs +64, +16 vs +42) while discarding 70% of the sample. "
        "Holdout alone: -27.2bps. The pullback filter removes good trades, not bad ones.",
        metrics={
            "oos_excess_bps": 42.7,
            "plain_momentum_oos_bps": 54.5,
            "holdout_excess_bps": -27.2,
            "deflated_sharpe": 0.0,
        },
    ),
    # ------------------------------------------------------------------------ rejected (DSE)
    Edge(
        key="dse_bullish_ma20_50_v1",
        market="DSE",
        family="trend_transition",
        status="rejected",
        horizon_sessions=63,
        verdict="The DSE 20/50 bullish crossover is sparse, late and benchmark-negative.",
        evidence="Only 15 validation and 24 holdout trades. Holdout median net -3.24%, "
        "signal-date cohort excess -3.30%, stressed cohort -1.57%, and mean net -1.50% "
        "after removing the two largest winners. The positive untrimmed mean is a small "
        "winner-tail effect, not an admissible edge.",
        metrics={
            "holdout_excess_pct": -3.3034,
            "holdout_median_net_pct": -3.238,
            "holdout_stressed_cohort_pct": -1.5716,
            "holdout_trades": 24,
        },
    ),
    Edge(
        key="dse_compression_breakout",
        market="DSE",
        family="compression_breakout",
        status="rejected",
        horizon_sessions=21,
        verdict="The largest apparent excess in the whole program (+460bps) and it fails "
        "sensitivity outright.",
        evidence="Registered thresholds give +460.3bps out-of-sample on 147 events, but "
        "atr_contraction -25% gives -120.9bps — a sign flip inside the ±25% band. "
        "147 events across 2 years on raw closes cannot support a claim regardless.",
        metrics={"oos_excess_bps": 460.3, "sensitivity_min_bps": -120.9, "events": 147},
    ),
    Edge(
        key="dse_failed_breakdown",
        market="DSE",
        family="failed_breakdown",
        status="rejected",
        horizon_sessions=10,
        verdict="Positive only in the discovery window; negative once out of sample.",
        evidence="Discovery +923.0bps, validation -83.4bps, holdout -39.1bps. A textbook "
        "in-sample artefact.",
        metrics={"discovery_bps": 923.0, "holdout_bps": -39.1},
    ),
    Edge(
        key="dse_reversal_5d",
        market="DSE",
        family="mean_reversion",
        status="rejected",
        horizon_sessions=5,
        verdict="No edge. This is the mechanism behind the live dse_reversal_v1 shadow book.",
        evidence="-15.8 / -28.6 / +1.1bps; every interval spans zero. Additionally confounded: "
        "raw closes make bonus and rights ex-dates present as extreme 5-day losses, so "
        "the rule preferentially buys corporate actions rather than dislocations.",
        metrics={"holdout_excess_bps": 1.1},
    ),
    Edge(
        key="dse_trend_pullback_20d",
        market="DSE",
        family="trend_pullback",
        status="rejected",
        horizon_sessions=10,
        verdict="Insufficient evidence and unstable across the parameter band.",
        evidence="248 out-of-sample events, t=0.90. Perturbations range from +12.9bps to "
        "+146.1bps — a 10x spread inside ±25%, which is instability, not an edge.",
        metrics={"events": 248, "t_stat": 0.90},
    ),
    # ------------------------------------------------------------------------------ diagnostic
    Edge(
        key="us_momentum_12_1",
        market="US",
        family="momentum",
        status="diagnostic",
        horizon_sessions=21,
        verdict="Survives every robustness gate and STILL does not beat a passive index. "
        "Simulated as an actual portfolio it returns 12.16% CAGR against SPY's 14.82%, "
        "with 30.3% volatility and a 47% drawdown. It is also a 30-year-old published "
        "anomaly already implemented as System C's momentum factor, not a discovery.",
        evidence="Positive in all three chronological windows (+49.2 / +66.5 / +24.2bps), all "
        "five walk-forward folds (+40.2, +87.3, +17.6, +63.5, +42.2bps), and every "
        "±25% perturbation (+54.0 to +63.4bps). Positive at 3x costs over the combined "
        "out-of-sample window (+17.3bps), though the holdout alone turns slightly "
        "negative at 3x (-12.0bps). Hit rate is below 50% in every window (47-49%), so "
        "the mean is carried by the right tail — consistent with momentum's known "
        "return profile, and the reason fold consistency matters more here than any "
        "single window. Annualised out-of-sample Sharpe 0.65. "
        "Survivorship works AGAINST this result "
        "rather than for it: the delisted failures that are missing from the panel "
        "would have sat in the loser deciles and dragged the control down, so the true "
        "excess is likely larger than measured. Deflated Sharpe is 0.00 against the 62 "
        "specifications tried here, but that penalty is arguably misapplied — momentum "
        "was preregistered as an external control, not selected by this search. "
        "Two findings cap it regardless: the excess is concentrated in very few "
        "sessions (dropping the best 5% of signal dates cuts the mean from +51.2bps to "
        "+14.3bps), and the portfolio simulation underperforms SPY. The matched-control "
        "excess measures factor efficacy against comparable stocks; that peer group "
        "itself lost to the cap-weighted index, so a positive control-relative number "
        "coexists with a negative investability verdict.",
        metrics={
            "holdout_excess_bps": 24.2,
            "cost_3x_bps": 17.3,
            "sharpe_annualised": 0.649,
            "folds_bps": [40.2, 87.3, 17.6, 63.5, 42.2],
            "deflated_sharpe": 0.0,
            "portfolio_nav_per_100": 282.00,
            "spy_nav_per_100": 348.43,
            "cagr_pct": 12.16,
            "spy_cagr_pct": 14.82,
            "max_drawdown_pct": -46.9,
            "annual_vol_pct": 30.3,
            "excess_ex_best_5pct_days_bps": 14.3,
        },
    ),
    # -------------------------------------------------------------------------- data_blocked
    Edge(
        key="dse_momentum_12_1",
        market="DSE",
        family="momentum",
        status="data_blocked",
        horizon_sessions=21,
        verdict="Reads positive (+66.0bps out-of-sample, t=2.96) and must not be believed.",
        evidence="A 12-1 momentum feature needs 252 sessions of warm-up; DSE has 492 sessions "
        "total, leaving one non-overlapping period. Worse, the 252-session lookback "
        "spans a corporate action on roughly 11.5% of the panel, and DSE has zero "
        "adjusted closes, so the momentum input itself is corrupted on those rows.",
        blocked_on=(
            "DSE corporate-action adjustment factors",
            "DSE history depth — 2.0 years cannot support a 12-month formation window",
        ),
        metrics={"oos_excess_bps": 66.0, "t_stat": 2.96, "panel_corrupted_pct": 11.5},
    ),
    Edge(
        key="us_short_interest_accel",
        market="US",
        family="short_positioning",
        status="forward_collection",
        horizon_sessions=21,
        verdict="Cannot be tested. The short-interest history is 8 settlement dates, not the "
        "multi-year history the squeeze specification claims.",
        evidence="Verified 2026-07-25: short_interest_biweekly holds 84,395 rows across exactly "
        "8 settlement dates, 2026-03-31 to 2026-07-15. known_at gating is correct "
        "(settlement + ~13 days). This is a well-built forward collection roughly 16 "
        "weeks old.",
        blocked_on=(
            "short-interest history — 8 settlement dates available",
            "US free float — 0 of 11,072 codes have it; the ratio can only use shares "
            "outstanding, which understates scarcity",
            "borrow / locate / cost-to-borrow — no vendor; short execution stays blocked",
        ),
    ),
    Edge(
        key="us_insider_cluster_buy",
        market="US",
        family="insider",
        status="rejected",
        horizon_sessions=63,
        verdict="TESTED 2026-07-25 and rejected by its own preregistered kill criterion. The "
        "cluster framing carries no information: the single-buyer variant BEATS it out of "
        "sample (+75.0 vs -39.7bps holdout), and on filter-operative data the two are "
        "indistinguishable (+157.5 vs +167.3bps). Breadth is the entire mechanism the "
        "spec claimed, and breadth is absent.",
        evidence="Frozen spec hash a08385df87d90213, recorded before the extract was pulled. "
        "Discovery +162.4bps (t=2.00), validation +167.1 (t=2.18), holdout -39.7 "
        "(t=-0.40, hit 42%) — the holdout sits at the harness null (-37.0bps, which is "
        "-(average cost); gross null excess -7.7bps confirms the harness is unbiased at "
        "this horizon). Two further disqualifications: (a) the 10b5-1 null returns "
        "+471.7bps (t=3.94) on filter-operative data, LARGER than the opportunistic "
        "set, and the routine null +119.9bps — both were preregistered as having to be "
        "~zero, and a positive null was preregistered as invalidating the primary; "
        "(b) the 10b5-1 checkbox is 0.0% populated before 2023 (verified: 0 of 39,483 "
        "rows in 2021-22 vs 4.7-9.8% from 2023), so the positive discovery and early "
        "validation windows were computed with the spec's central filter inoperative. "
        "The wide null CIs ([-704,+1516] on 659 events) say the honest reading is not "
        "'scheduled buys predict' but 'five years of US Form 4 cannot distinguish any "
        "of these four groups from each other'.",
        metrics={
            "holdout_excess_bps": -39.7,
            "holdout_t": -0.40,
            "holdout_hit_rate": 0.42,
            "single_buyer_holdout_bps": 75.0,
            "plan_null_bps": 471.7,
            "routine_null_bps": 119.9,
            "harness_null_bps": -37.0,
            "events_on_panel": 10068,
            "plan_flag_pct_pre_2023": 0.0,
        },
    ),
    Edge(
        key="us_insider_single_buy",
        market="US",
        family="insider",
        status="diagnostic",
        horizon_sessions=63,
        verdict="A generic 'an officer or director bought on the open market' read is positive "
        "and beats the harness null, but it CANNOT be attributed to insider information "
        "and must not be presented as a validated signal.",
        evidence="+167.3bps (t=3.22, CI [+79,+268]) on filter-operative data; holdout +75.0bps "
        "(t=0.78, CI spans zero). Three reasons it stays diagnostic: the scheduled and "
        "routine nulls are similarly positive, so nothing isolates information from a "
        "shared characteristic tilt; insider buying concentrates in beaten-down small "
        "caps whose failures are wholly absent from this survivors-only panel, making "
        "the favourable bias larger here than for any price-based family; and hit rate "
        "is 47-48%, so the mean rests on the right tail.",
        blocked_on=(
            "US delisted price histories — the bias direction is maximally favourable "
            "for this family, so a positive result is an especially loose upper bound",
        ),
        metrics={
            "filter_operative_bps": 167.3,
            "filter_operative_t": 3.22,
            "holdout_excess_bps": 75.0,
            "hit_rate": 0.48,
        },
    ),
    Edge(
        key="us_insider_plan_buy_null",
        market="US",
        family="insider",
        status="rejected",
        horizon_sessions=63,
        verdict="Registered NULL. Did not behave as a null — which is the finding, and it is what "
        "rejects the primary hypothesis rather than a result in its own right.",
        evidence="+471.7bps (t=3.94) but CI [-704,+1516] on 659 events across 485 dates (~1.4 "
        "events per date). Untestable before 2023 because the checkbox did not exist. "
        "A pre-scheduled purchase cannot contain current information, so a large "
        "positive here measures sample noise, not predictive content.",
        metrics={"excess_bps": 471.7, "t_stat": 3.94, "ci_low_bps": -704.1, "events": 659},
    ),
    Edge(
        key="us_insider_routine_buy_null",
        market="US",
        family="insider",
        status="rejected",
        horizon_sessions=63,
        verdict="Registered NULL. Cohen-Malloy-Pomorski's central claim — that calendar-routine "
        "insiders carry ZERO predictive power — does not reproduce on this panel.",
        evidence="+119.9bps (t=1.24, CI [-108,+369]) on filter-operative data, statistically "
        "indistinguishable from the opportunistic sets. Either the routine/opportunistic "
        "distinction does not survive out of the paper's 1989-2007 sample, or 760 events "
        "is too few to resolve it. Both readings block the primary.",
        metrics={"excess_bps": 119.9, "t_stat": 1.24, "events": 760},
    ),
    Edge(
        key="us_quality_value",
        market="US",
        family="fundamental",
        status="data_blocked",
        horizon_sessions=126,
        verdict="The best-instrumented untested hypothesis in the platform.",
        evidence="4.22M SEC Company Facts observations across 5,188 codes with genuine known_at "
        "point-in-time gating from 2018-07-19 — the only large dataset here with real "
        "PIT semantics. Position-horizon fundamentals are also the family least "
        "damaged by survivorship, because quality screens systematically avoid the "
        "names that delist.",
        blocked_on=(
            "SEC Company Facts extract not in the research cache (2.8GB)",
            "US delisted price histories",
        ),
    ),
    Edge(
        key="us_activist_13d",
        market="US",
        family="ownership",
        status="forward_collection",
        horizon_sessions=63,
        verdict="Thin but real; keep collecting.",
        evidence="153,658 stake events across 9,593 subjects from 2021-06-30. Five years spans "
        "a regime change (the post-2024 five-business-day deadline), so pooling across "
        "it would mix two different disclosure speeds.",
        blocked_on=("event depth", "extract not in the research cache"),
    ),
    Edge(
        key="us_pead_smallcap",
        market="US",
        family="event_drift",
        status="data_blocked",
        horizon_sessions=63,
        verdict="Cannot construct a surprise measure.",
        evidence="No analyst-consensus dataset exists in the platform, so 'surprise' cannot be "
        "defined. EDGAR accepted_at gives timing but not expectation.",
        blocked_on=("earnings consensus / expectation data",),
    ),
    Edge(
        key="us_13f_cloning",
        market="US",
        family="ownership",
        status="data_blocked",
        horizon_sessions=63,
        verdict="No usable sample.",
        evidence="636,631 positions but only 8 quarters, each disclosed with a 45-day lag.",
        blocked_on=("13F history depth — revisit at 20+ quarters",),
    ),
    Edge(
        key="us_gamma_squeeze",
        market="US",
        family="options",
        status="data_blocked",
        horizon_sessions=10,
        verdict="No options data of any kind exists.",
        evidence="Zero rows. No open interest, volume, strike, expiry, implied volatility or "
        "Greeks. Cboe DataShop evaluation pending with the owner.",
        blocked_on=("option chain history", "opening/closing trade classification"),
    ),
    Edge(
        key="us_index_deletion",
        market="US",
        family="forced_selling",
        status="data_blocked",
        horizon_sessions=21,
        verdict="No historical index membership.",
        evidence="Security master is current-state only; PIT listing capture began 2026-07-17.",
        blocked_on=("historical index constituent data",),
    ),
    Edge(
        key="dse_sponsor_accumulation",
        market="DSE",
        family="ownership",
        status="data_blocked",
        horizon_sessions=63,
        verdict="The most distinctively DSE hypothesis in the registry, and the data is too "
        "sparse to test it.",
        evidence="1,567 shareholding rows across 395 codes — about 4 snapshots per company over "
        "10 years. Coverage is uneven and must be verified per code before any use.",
        blocked_on=("DSE shareholding snapshot depth", "DSE corporate-action adjustment"),
    ),
    Edge(
        key="dse_low_float_demand",
        market="DSE",
        family="structure",
        status="data_blocked",
        horizon_sessions=21,
        verdict="Free float exists as a current snapshot only, so it cannot be used point-in-time.",
        evidence="359 of 396 DSE codes carry free_float_cap_mn, but ticker_analytics holds one "
        "current row per symbol with no history. Using today's float to select a 2024 "
        "entry is look-ahead.",
        blocked_on=("free-float history",),
    ),
    Edge(
        key="dse_circuit_transition",
        market="DSE",
        family="structure",
        status="data_blocked",
        horizon_sessions=5,
        verdict="Circuit rules changed over the sample and are not stored effective-dated.",
        evidence="Forensic evidence that the band matters: 89 sessions fell more than 10% in a "
        "day, and 70.8% sit within 10 days of a corporate-action or dividend "
        "announcement against a 15.6% base rate — a 4.55x lift.",
        blocked_on=("effective-dated DSE circuit-limit and floor-price rules",),
    ),
    Edge(
        key="dse_scalp_intraday",
        market="DSE",
        family="intraday",
        status="data_blocked",
        horizon_sessions=1,
        verdict="The owner's preferred mechanism in its native intraday form. Four sessions of "
        "data. Refuse.",
        evidence="intraday_bars holds 26,573 rows across 4 session dates (2026-07-20 to "
        "2026-07-23). At the current accrual rate, a 2-year intraday history exists in "
        "mid-2028.",
        blocked_on=("DSE intraday history — 4 sessions collected",),
    ),
    Edge(
        key="us_scalp_intraday",
        market="US",
        family="intraday",
        status="data_blocked",
        horizon_sessions=1,
        verdict="No US intraday data whatsoever.",
        evidence="Zero rows.",
        blocked_on=("US intraday history",),
    ),
    Edge(
        key="us_catalyst_continuation",
        market="US",
        family="catalyst",
        status="forward_collection",
        horizon_sessions=10,
        verdict="Collection began July 2026; US catalyst windows are inferred, never confirmed.",
        evidence="research_catalyst_events is weeks old.",
        blocked_on=("catalyst outcome history — revisit after 2 quarters",),
    ),
)


def to_json() -> str:
    payload = {
        "methodology": METHODOLOGY,
        "run_date": RUN_DATE,
        "paper_eligible_count": sum(1 for e in REGISTRY if e.status == "paper_eligible"),
        "counts": {
            status: sum(1 for e in REGISTRY if e.status == status)
            for status in (
                "rejected",
                "data_blocked",
                "forward_collection",
                "diagnostic",
                "paper_eligible",
            )
        },
        "edges": [asdict(edge) for edge in REGISTRY],
    }
    return json.dumps(payload, indent=2)


if __name__ == "__main__":
    out = Path(
        "/private/tmp/claude-501/-Users-iliashossain-project-millionare-bulls-of-the-world"
        "/f8d6f3a8-9d5b-4636-ac60-804fe70fad22/scratchpad/results/edge_registry.json"
    )
    out.write_text(to_json())
    payload = json.loads(to_json())
    print(json.dumps(payload["counts"], indent=2))
    print(f"paper_eligible: {payload['paper_eligible_count']}")
