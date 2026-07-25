"""Preregistered hypothesis registry.

Every hypothesis is frozen here *before* its holdout window is inspected. The ``spec_hash`` on
each :class:`~edge_discovery.harness.Spec` is recorded in the experiment ledger alongside the
result, so a later reader can verify that the specification was not edited to fit the outcome.

Each entry states an economic mechanism — who is forced, slow, constrained, or behaviourally
biased — because an indicator pattern without a mechanism is a data-mining artefact waiting to
happen. Hypotheses whose data does not exist are registered anyway, with ``runnable=False`` and
the missing dataset named, so the registry doubles as the acquisition backlog.

Trial families matter for multiple-testing correction: hypotheses in the same family test the
same underlying effect with different parameterisations, and the deflated Sharpe applied in the
report uses the family's trial count, not one.
"""

from __future__ import annotations

from dataclasses import dataclass

from .harness import Spec


@dataclass(frozen=True)
class Registered:
    spec: Spec
    runnable: bool
    blocked_on: tuple[str, ...] = ()


def _spec(**kwargs) -> Spec:
    return Spec(**kwargs)


# --------------------------------------------------------------------------------------------
# Family A — trend continuation after a controlled pullback (the owner's preferred mechanism)
# --------------------------------------------------------------------------------------------

A1 = _spec(
    key="us_trend_pullback_20d",
    name="US trend continuation after controlled pullback to the 20-day mean",
    market="US",
    family="trend_pullback",
    mechanism=(
        "Investors under-react to sustained improvement in a company's prospects, so an "
        "established uptrend resumes after a controlled pullback. The pullback must look like "
        "temporary supply absorption (shallow, low participation) rather than distribution "
        "(deep, heavy volume), which is what separates this from 'buy any dip'."
    ),
    direction="long",
    horizon=10,
    universe="US common/ADR, liquidity deciles 5-9, price>$5, >=252 bars of history",
    entry_rule=(
        "close>sma_200 and mom_12_1 in top 40% cross-sectionally; close pulled back to within "
        "2% of sma_20 from a 20-day high; pullback depth <= 1.5x ATR(14); 5-day volume below "
        "20-day average. Fill next session open."
    ),
    exit_rule="Time exit at 10 sessions.",
    invalidation="Close below the 20-session low that preceded entry.",
    expected_failure=(
        "The rule degenerates into short-term reversal and earns the reversal premium rather "
        "than a trend premium; or the trend filter simply loads on the momentum factor."
    ),
    thresholds={"pullback_atr": 1.5, "near_sma20_pct": 0.02, "mom_pctile": 0.60},
)

A2 = _spec(
    key="us_trend_pullback_shallow",
    name="US trend continuation, shallow-pullback variant",
    market="US",
    family="trend_pullback",
    mechanism=A1.mechanism + " Shallower pullbacks should indicate stronger residual demand.",
    direction="long",
    horizon=10,
    universe=A1.universe,
    entry_rule="As A1 but pullback depth <= 0.75x ATR(14).",
    exit_rule="Time exit at 10 sessions.",
    invalidation=A1.invalidation,
    expected_failure="Sample collapses; shallow pullbacks are indistinguishable from no pullback.",
    thresholds={"pullback_atr": 0.75, "near_sma20_pct": 0.02, "mom_pctile": 0.60},
)

A3 = _spec(
    key="us_trend_pullback_h21",
    name="US trend continuation, swing horizon",
    market="US",
    family="trend_pullback",
    mechanism=A1.mechanism,
    direction="long",
    horizon=21,
    universe=A1.universe,
    entry_rule="As A1.",
    exit_rule="Time exit at 21 sessions.",
    invalidation=A1.invalidation,
    expected_failure="Edge decays with horizon as the pullback information is absorbed.",
    thresholds=dict(A1.thresholds),
)

A4 = _spec(
    key="dse_trend_pullback_20d",
    name="DSE trend continuation after controlled pullback",
    market="DSE",
    family="trend_pullback",
    mechanism=A1.mechanism + " DSE's retail dominance should make under-reaction larger.",
    direction="long",
    horizon=10,
    universe="DSE, liquidity deciles 5-9, >=252 bars",
    entry_rule="As A1 on raw closes.",
    exit_rule="Time exit at 10 sessions.",
    invalidation=A1.invalidation,
    expected_failure=(
        "Raw closes make bonus/rights ex-dates look like pullbacks, manufacturing entries at "
        "prices that never fell. Circuit limits also truncate the pullback distribution."
    ),
    thresholds=dict(A1.thresholds),
)

# --------------------------------------------------------------------------------------------
# Family B — compression and volume-confirmed breakout
# --------------------------------------------------------------------------------------------

B1 = _spec(
    key="us_compression_breakout",
    name="US volatility compression into a volume-confirmed breakout",
    market="US",
    family="compression_breakout",
    mechanism=(
        "A narrowing range means supply and demand have reached temporary balance near a "
        "reference price. A breakout on expanded participation signals that balance broke, and "
        "traders anchored to the old range are slow to re-price."
    ),
    direction="long",
    horizon=21,
    universe="US common/ADR, liquidity deciles 4-9, price>$5, >=252 bars",
    entry_rule=(
        "Within 15% of the 52-week high; ATR(14) <= 0.8x ATR(14) twenty sessions earlier; close "
        "clears the prior 20-session high; breakout-session volume >= 1.5x the 20-day average. "
        "Fill next session open."
    ),
    exit_rule="Time exit at 21 sessions.",
    invalidation="Close below the 20-session base low.",
    expected_failure=(
        "Breakouts are a well-known retail pattern; any premium may be arbitraged away or "
        "consumed by the spread in the small caps where the pattern is most visible."
    ),
    thresholds={"atr_contraction": 0.8, "vol_multiple": 1.5, "from_high_pct": -0.15},
)

B2 = _spec(
    key="us_52w_high_breakout",
    name="US new 52-week high",
    market="US",
    family="compression_breakout",
    mechanism=(
        "The 52-week high is a salient anchor. The disposition effect makes holders sell winners "
        "too early, capping the price near the anchor; once it clears, under-reaction resolves."
    ),
    direction="long",
    horizon=21,
    universe=B1.universe,
    entry_rule="Close is a new 252-session high. Fill next session open.",
    exit_rule="Time exit at 21 sessions.",
    invalidation="Close below the 20-session low.",
    expected_failure="Pure momentum proxy; no incremental information over 12-1 momentum.",
    thresholds={},
)

B3 = _spec(
    key="us_post_breakout_retest",
    name="US first pullback to a cleared breakout level",
    market="US",
    family="compression_breakout",
    mechanism=(
        "The breakout level converts from resistance to support because buyers who missed the "
        "move anchor their bids there. This is an entry-timing variant of B1, not a new factor."
    ),
    direction="long",
    horizon=21,
    universe=B1.universe,
    entry_rule=(
        "A B1 breakout occurred 3-10 sessions ago; price has since traded back to within 3% of "
        "the breakout trigger while holding above it. Fill next session open."
    ),
    exit_rule="Time exit at 21 sessions.",
    invalidation="Close below the breakout trigger by more than 3%.",
    expected_failure="Duplicates B1's factor; must not become a separate book.",
    thresholds={"retest_pct": 0.03},
)

B4 = _spec(
    key="dse_compression_breakout",
    name="DSE volatility compression breakout",
    market="DSE",
    family="compression_breakout",
    mechanism=B1.mechanism,
    direction="long",
    horizon=21,
    universe="DSE, liquidity deciles 4-9, >=252 bars",
    entry_rule="As B1 on raw closes.",
    exit_rule="Time exit at 21 sessions.",
    invalidation="Close below the 20-session base low.",
    expected_failure="Circuit limits truncate breakout days; raw closes contaminate the base.",
    thresholds=dict(B1.thresholds),
)

# --------------------------------------------------------------------------------------------
# Family C — failed breakdown reversal
# --------------------------------------------------------------------------------------------

C1 = _spec(
    key="us_failed_breakdown",
    name="US failed breakdown below multi-week support",
    market="US",
    family="failed_breakdown",
    mechanism=(
        "Stops cluster below visible support. When price undercuts it and immediately reclaims, "
        "the decline was liquidity-driven rather than information-driven, and the forced sellers "
        "are already out — the supply overhang is gone."
    ),
    direction="long",
    horizon=10,
    universe="US common/ADR, liquidity deciles 4-9, price>$5, >=252 bars",
    entry_rule=(
        "Reference support = min low of sessions -60..-11. Any low in the last 7 sessions "
        "(excluding today) undercut 0.99x support. Today's close >= 1.02x support with relative "
        "volume >= 1.2. Fill next session open."
    ),
    exit_rule="Time exit at 10 sessions.",
    invalidation="Close below the undercut low.",
    expected_failure=(
        "Without the uptrend precondition this is just buying bounces in downtrends, which is "
        "where survivorship bias does its worst damage."
    ),
    thresholds={"reclaim_pct": 1.02, "relvol": 1.2},
)

C2 = _spec(
    key="us_failed_breakdown_uptrend",
    name="US failed breakdown, uptrend-gated",
    market="US",
    family="failed_breakdown",
    mechanism=C1.mechanism + " Gated to an intact medium-term uptrend.",
    direction="long",
    horizon=10,
    universe=C1.universe,
    entry_rule="As C1 plus close > sma_200.",
    exit_rule="Time exit at 10 sessions.",
    invalidation="Close below the undercut low.",
    expected_failure="Sample shrinks sharply; the gate may remove the effect along with the risk.",
    thresholds=dict(C1.thresholds),
)

C3 = _spec(
    key="dse_failed_breakdown",
    name="DSE failed breakdown",
    market="DSE",
    family="failed_breakdown",
    mechanism=C1.mechanism,
    direction="long",
    horizon=10,
    universe="DSE, liquidity deciles 4-9",
    entry_rule="As C1 on raw closes.",
    exit_rule="Time exit at 10 sessions.",
    invalidation="Close below the undercut low.",
    expected_failure="Floor-price rules can pin DSE prices at support, faking undercuts.",
    thresholds=dict(C1.thresholds),
)

# --------------------------------------------------------------------------------------------
# Family D — cross-sectional short-term mean reversion
# --------------------------------------------------------------------------------------------

D1 = _spec(
    key="us_reversal_5d",
    name="US 5-session cross-sectional reversal",
    market="US",
    family="mean_reversion",
    mechanism=(
        "Liquidity demanders who must sell quickly pay a concession to whoever supplies the "
        "other side. Buying the most-sold names collects that concession. The premium is "
        "compensation for inventory risk, so it should be strongest where volatility is high "
        "and weakest where the move carried real information."
    ),
    direction="long",
    horizon=5,
    universe="US common/ADR, liquidity deciles 5-9, price>$5",
    entry_rule="ret_5 in the bottom decile within the eligible universe that session. Fill next open.",
    exit_rule="Time exit at 5 sessions.",
    invalidation="None — this is a systematic cross-sectional sleeve, not a single-name thesis.",
    expected_failure=(
        "Survivorship: the worst 5-day losers include names that later failed and were never "
        "loaded. This is the hypothesis most inflated by the survivors-only panel."
    ),
    thresholds={"decile": 0.10},
)

D2 = _spec(
    key="us_reversal_5d_megacap",
    name="US 5-session reversal, most-liquid decile only",
    market="US",
    family="mean_reversion",
    mechanism=D1.mechanism + " Restricting to the most liquid names bounds survivorship error.",
    direction="long",
    horizon=5,
    universe="US common/ADR, liquidity decile 9 only, price>$5",
    entry_rule="As D1 within decile 9.",
    exit_rule="Time exit at 5 sessions.",
    invalidation="None.",
    expected_failure="Liquid names are the most arbitraged; the premium may be gone after costs.",
    thresholds={"decile": 0.10},
)

D3 = _spec(
    key="us_reversal_1d",
    name="US 1-session reversal",
    market="US",
    family="mean_reversion",
    mechanism=D1.mechanism + " Single-session dislocations are the purest liquidity events.",
    direction="long",
    horizon=5,
    universe=D1.universe,
    entry_rule="Single-session return in the bottom 5% of the eligible universe. Fill next open.",
    exit_rule="Time exit at 5 sessions.",
    invalidation="None.",
    expected_failure="One-day drops are often news; buying them buys the news.",
    thresholds={"pctile": 0.05},
)

D4 = _spec(
    key="dse_reversal_5d",
    name="DSE 5-session cross-sectional reversal",
    market="DSE",
    family="mean_reversion",
    mechanism=D1.mechanism + " This is the mechanism behind the live dse_reversal_v1 shadow book.",
    direction="long",
    horizon=5,
    universe="DSE, liquidity deciles 5-9",
    entry_rule="As D1 on raw closes.",
    exit_rule="Time exit at 5 sessions.",
    invalidation="None.",
    expected_failure=(
        "Bonus/rights ex-dates present as extreme 5-day losses, so the rule preferentially buys "
        "corporate actions rather than dislocations — a mechanical loss, not a market effect."
    ),
    thresholds={"decile": 0.10},
)

# --------------------------------------------------------------------------------------------
# Family E — cross-sectional momentum
# --------------------------------------------------------------------------------------------

E1 = _spec(
    key="us_momentum_12_1",
    name="US 12-1 cross-sectional momentum",
    market="US",
    family="momentum",
    mechanism=(
        "Gradual information diffusion plus disposition-driven under-reaction. The canonical "
        "anomaly; included as a control so newer hypotheses must prove they add something."
    ),
    direction="long",
    horizon=21,
    universe="US common/ADR, liquidity deciles 4-9, price>$5, >=252 bars",
    entry_rule="mom_12_1 in the top decile that session. Fill next open.",
    exit_rule="Time exit at 21 sessions.",
    invalidation="None.",
    expected_failure="Well documented as decaying post-publication and crash-prone after drawdowns.",
    thresholds={"decile": 0.10},
)

E2 = _spec(
    key="us_momentum_with_pullback",
    name="US momentum conditioned on short-term weakness",
    market="US",
    family="momentum",
    mechanism=(
        "Combines the two effects that operate at different frequencies: buy long-horizon "
        "winners (momentum) while they are short-horizon losers (reversal). This is the "
        "cross-sectional expression of the owner's preferred trend-pullback idea and is the "
        "cleanest way to test whether 'the pullback' adds anything to plain momentum."
    ),
    direction="long",
    horizon=21,
    universe=E1.universe,
    entry_rule="mom_12_1 top decile AND ret_5 in the bottom 30% of that decile. Fill next open.",
    exit_rule="Time exit at 21 sessions.",
    invalidation="None.",
    expected_failure="The two effects cancel rather than compound.",
    thresholds={"mom_decile": 0.10, "st_pctile": 0.30},
)

E3 = _spec(
    key="dse_momentum_12_1",
    name="DSE 12-1 cross-sectional momentum",
    market="DSE",
    family="momentum",
    mechanism=E1.mechanism,
    direction="long",
    horizon=21,
    universe="DSE, liquidity deciles 4-9, >=252 bars",
    entry_rule="As E1 on raw closes.",
    exit_rule="Time exit at 21 sessions.",
    invalidation="None.",
    expected_failure="Two years of history cannot establish a 12-month-formation effect.",
    thresholds={"decile": 0.10},
)

# --------------------------------------------------------------------------------------------
# Family F — volatility structure
# --------------------------------------------------------------------------------------------

F1 = _spec(
    key="us_low_volatility",
    name="US low-volatility sleeve",
    market="US",
    family="volatility",
    mechanism=(
        "Leverage-constrained investors bid up high-beta names, leaving low-volatility names "
        "cheap on a risk-adjusted basis. A level effect, so it should show in Sharpe, not in "
        "raw excess return."
    ),
    direction="long",
    horizon=21,
    universe="US common/ADR, liquidity deciles 4-9, price>$5",
    entry_rule="vol_60 in the bottom decile that session. Fill next open.",
    exit_rule="Time exit at 21 sessions.",
    invalidation="None.",
    expected_failure=(
        "The matched control already buckets on volatility, so this design largely differences "
        "the effect away. Expected to read near zero by construction — a specification check."
    ),
    thresholds={"decile": 0.10},
)

F2 = _spec(
    key="us_vol_contraction",
    name="US volatility contraction",
    market="US",
    family="volatility",
    mechanism=(
        "Realised volatility is persistent and mean-reverting; contraction predicts expansion. "
        "Direction-agnostic, so it is a diagnostic for position sizing, not an entry signal."
    ),
    direction="long",
    horizon=21,
    universe=F1.universe,
    entry_rule="vol_20 <= 0.6x vol_60. Fill next open.",
    exit_rule="Time exit at 21 sessions.",
    invalidation="None.",
    expected_failure="Predicts magnitude, not sign; expected to show no directional edge.",
    thresholds={"contraction": 0.6},
)

# --------------------------------------------------------------------------------------------
# Family G — forced selling and dislocation
# --------------------------------------------------------------------------------------------

G1 = _spec(
    key="us_capitulation_volume",
    name="US capitulation: multi-day decline into a volume spike",
    market="US",
    family="forced_selling",
    mechanism=(
        "Margin calls and risk-limit breaches force sales regardless of value. The volume spike "
        "marks the transfer of stock from constrained to unconstrained holders, after which the "
        "selling pressure is mechanically exhausted."
    ),
    direction="long",
    horizon=10,
    universe="US common/ADR, liquidity deciles 5-9, price>$5",
    entry_rule=(
        "ret_5 <= -12%, today's volume >= 2.5x the 20-day average, close > sma_200 before the "
        "decline began. Fill next open."
    ),
    exit_rule="Time exit at 10 sessions.",
    invalidation="Close 8% below entry.",
    expected_failure=(
        "Indistinguishable from information-driven repricing. Strongly inflated by "
        "survivorship — the capitulations that ended in delisting are absent."
    ),
    thresholds={"decline": -0.12, "vol_multiple": 2.5},
)

# --------------------------------------------------------------------------------------------
# Family H — baselines the complex rules must beat
# --------------------------------------------------------------------------------------------

H1 = _spec(
    key="baseline_high_relvol",
    name="Baseline: simple high relative volume",
    market="US",
    family="baseline",
    mechanism="No mechanism claimed. The simplest attention proxy; complex rules must beat it.",
    direction="long",
    horizon=21,
    universe="US common/ADR, liquidity deciles 4-9, price>$5",
    entry_rule="Volume >= 2x the 20-day average. Fill next open.",
    exit_rule="Time exit at 21 sessions.",
    invalidation="None.",
    expected_failure="Expected to be approximately zero after costs.",
    thresholds={"relvol": 2.0},
)

H2 = _spec(
    key="baseline_random",
    name="Baseline: random eligible securities",
    market="US",
    family="baseline",
    mechanism=(
        "No mechanism. A deterministic pseudo-random selection from the eligible universe. Its "
        "measured excess must be indistinguishable from zero; if it is not, the harness itself "
        "is biased and every other result is void."
    ),
    direction="long",
    horizon=21,
    universe="US common/ADR, liquidity deciles 4-9, price>$5",
    entry_rule="Deterministic hash of (code, date) selects ~2% of eligible rows. Fill next open.",
    exit_rule="Time exit at 21 sessions.",
    invalidation="None.",
    expected_failure="None — this is the harness's own null calibration.",
    thresholds={"rate": 0.02},
)

PRICE_BASED: tuple[Registered, ...] = tuple(
    Registered(spec=spec, runnable=True)
    for spec in (
        A1,
        A2,
        A3,
        A4,
        B1,
        B2,
        B3,
        B4,
        C1,
        C2,
        C3,
        D1,
        D2,
        D3,
        D4,
        E1,
        E2,
        E3,
        F1,
        F2,
        G1,
        H1,
        H2,
    )
)


# --------------------------------------------------------------------------------------------
# Family I — insider purchase clusters (Form 4). Frozen 2026-07-25 BEFORE the Form 4 extract was
# pulled; the two nulls (I3, I4) exist to falsify I1 and were registered at the same moment.
#
# Survivorship warning specific to this family: insider buying concentrates in beaten-down small
# caps, and the ones that went to zero are wholly absent from the panel. So the favourable bias
# here is larger than for any price-based family. Under the harness's asymmetry rule a negative
# result is still conclusive, but a positive result is an especially loose upper bound.
# --------------------------------------------------------------------------------------------

_INSIDER_UNIVERSE = (
    "US common/ADR, liquidity deciles 2-9, price>$1, >=252 bars of history. Deciles 0-1 are "
    "excluded because their 100-150bps round-trip cost dominates any plausible effect."
)
_INSIDER_MECHANISM_CORE = (
    "An officer or director buying with their own money pays a real, undiversified cost to hold "
    "a concentrated position they already have career exposure to. That cost makes the purchase "
    "credible in a way no disclosure or forecast is. Cohen-Malloy-Pomorski (2012) show the "
    "predictive content sits entirely in *opportunistic* trades: insiders on a calendar programme "
    "carry zero. Several insiders acting inside one window is harder to explain by personal "
    "liquidity than one is, which is why breadth rather than size is the primary axis."
)

I1 = _spec(
    key="us_insider_cluster_buy",
    name="US opportunistic insider purchase cluster (>=2 buyers/90d)",
    market="US",
    family="insider",
    mechanism=_INSIDER_MECHANISM_CORE,
    direction="long",
    horizon=63,
    universe=_INSIDER_UNIVERSE,
    entry_rule=(
        "Form 4 code P acquisitions, is_10b5_1_plan false, buyer is officer or director, buyer "
        "not calendar-routine (no purchase in the same calendar month in 3 consecutive prior "
        "years). Signal fires on the EDGAR accepted_at date at which >=2 DISTINCT such buyers "
        "exist in the trailing 90 calendar days. One signal per (code, date). Fill next open."
    ),
    exit_rule="Time exit at 63 sessions.",
    invalidation="None — fixed horizon, so the measurement is of drift, not of a managed trade.",
    expected_failure=(
        "Reject if the excess is negative or its CI spans zero out of sample; reject if the "
        "10b5-1 null (I3) or the routine null (I4) shows a comparable excess, because that would "
        "prove the filters carry no information and the signal is just 'firms whose insiders "
        "buy'; reject if the effect sits only in the two least liquid deciles retained."
    ),
    thresholds={"min_buyers": 2.0, "window_days": 90.0, "routine_years": 3.0},
)

I2 = _spec(
    key="us_insider_single_buy",
    name="US opportunistic insider purchase, single buyer only",
    market="US",
    family="insider",
    mechanism=(
        _INSIDER_MECHANISM_CORE
        + " This variant isolates exactly one buyer to test whether BREADTH is the mechanism. "
        "Published work puts cluster excess at roughly twice a single buy; if I2 matches I1, "
        "breadth is decoration and the cluster framing is wrong."
    ),
    direction="long",
    horizon=63,
    universe=_INSIDER_UNIVERSE,
    entry_rule=(
        "As I1 but exactly ONE distinct qualifying buyer in the trailing 90 days. Mutually "
        "exclusive with I1 by construction."
    ),
    exit_rule="Time exit at 63 sessions.",
    invalidation="None.",
    expected_failure="Expected positive but materially smaller than I1. If >= I1, reject I1.",
    thresholds={"min_buyers": 1.0, "max_buyers": 1.0, "window_days": 90.0},
)

I3 = _spec(
    key="us_insider_plan_buy_null",
    name="NULL: 10b5-1 scheduled insider purchases only",
    market="US",
    family="insider",
    mechanism=(
        "No mechanism claimed. A purchase executed under a pre-arranged Rule 10b5-1 plan was "
        "scheduled before the insider could act on anything current, so it must carry no "
        "predictive content. This is the sharpest available falsification test of the whole "
        "family: if scheduled buys predict as well as opportunistic ones, then the filter "
        "apparatus in fintel_insider_algo is measuring firm characteristics, not information."
    ),
    direction="long",
    horizon=63,
    universe=_INSIDER_UNIVERSE,
    entry_rule=(
        "Form 4 code P acquisitions with is_10b5_1_plan TRUE, officer or director, >=1 buyer in "
        "the trailing 90 days. Fill next open."
    ),
    exit_rule="Time exit at 63 sessions.",
    invalidation="None.",
    expected_failure=(
        "Expected indistinguishable from zero. A significant positive result invalidates I1 and "
        "I2 rather than supporting them."
    ),
    thresholds={"window_days": 90.0},
)

I4 = _spec(
    key="us_insider_routine_buy_null",
    name="NULL: calendar-routine insider purchases only",
    market="US",
    family="insider",
    mechanism=(
        "No mechanism claimed. The second half of the Cohen-Malloy-Pomorski split: insiders who "
        "buy in the same calendar month year after year are on a programme. Registered so the "
        "routine/opportunistic distinction is measured on our own data rather than imported on "
        "the strength of a 2012 paper."
    ),
    direction="long",
    horizon=63,
    universe=_INSIDER_UNIVERSE,
    entry_rule=(
        "Form 4 code P acquisitions by buyers classified calendar-routine (purchase in the same "
        "calendar month in 3 consecutive prior years), non-plan, officer or director. Fill next "
        "open."
    ),
    exit_rule="Time exit at 63 sessions.",
    invalidation="None.",
    expected_failure="Expected indistinguishable from zero, per CMP. A positive result invalidates I1.",
    thresholds={"routine_years": 3.0, "window_days": 90.0},
)

INSIDER: tuple[Registered, ...] = tuple(
    Registered(spec=spec, runnable=True) for spec in (I1, I2, I3, I4)
)


# --------------------------------------------------------------------------------------------
# Registered but NOT runnable on the current extract. Each names the dataset that unblocks it.
# --------------------------------------------------------------------------------------------


def _blocked(key, name, market, family, mechanism, blocked_on, horizon=21, direction="long"):
    return Registered(
        spec=_spec(
            key=key,
            name=name,
            market=market,
            family=family,
            mechanism=mechanism,
            direction=direction,
            horizon=horizon,
            universe="see mechanism",
            entry_rule="preregistered on data arrival",
            exit_rule=f"Time exit at {horizon} sessions.",
            invalidation="preregistered on data arrival",
            expected_failure="not yet testable",
        ),
        runnable=False,
        blocked_on=blocked_on,
    )


BLOCKED: tuple[Registered, ...] = (
    _blocked(
        "us_pead_smallcap",
        "US post-earnings drift, small caps",
        "US",
        "event_drift",
        "Limited investor attention means small-cap earnings surprises are absorbed slowly. "
        "Documented as dead in mid/large caps post-2006, so only the small-cap variant is worth "
        "testing.",
        (
            "earnings surprise history (actual vs consensus) — no consensus dataset exists",
            "point-in-time announcement timestamps beyond EDGAR accepted_at",
        ),
    ),
    _blocked(
        "us_filing_gap_drift",
        "US drift after a large filing-day gap",
        "US",
        "event_drift",
        "A gap on a filing date marks information the market is still absorbing.",
        ("EDGAR filing extract not pulled into the research cache (available in production)",),
    ),
    # us_insider_cluster_buy moved to Family I (runnable) on 2026-07-25 once the Form 4 extract
    # was pulled. Its blocker was cache logistics, not missing data.
    _blocked(
        "us_insider_discretionary_sell",
        "US discretionary insider selling",
        "US",
        "insider",
        "Non-10b5-1 selling is discretionary and therefore informative, unlike scheduled sales.",
        ("short execution blocked: no borrow, locate, or cost-to-borrow dataset",),
        direction="short",
    ),
    _blocked(
        "us_activist_13d",
        "US activist 13D entry",
        "US",
        "ownership",
        "An activist filing 13D has committed capital and intends to force change; the market "
        "under-reacts to the credibility of that commitment.",
        (
            "13D/G history begins 2021-06-30 — five years, thin for event counts",
            "extract not pulled into the research cache",
        ),
    ),
    _blocked(
        "us_short_interest_accel",
        "US short-interest acceleration with price confirmation",
        "US",
        "short_positioning",
        "Rising short interest into rising price means shorts are being carried at a loss and "
        "may be forced to cover.",
        (
            "short interest is EIGHT settlement dates (2026-03-31 to 2026-07-15) — verified "
            "2026-07-25; this is a forward collection, not a history",
            "no US free float: the ratio can only use shares outstanding, understating scarcity",
        ),
    ),
    _blocked(
        "us_gamma_squeeze",
        "US dealer-gamma squeeze",
        "US",
        "options",
        "Dealers short calls must buy the underlying as it rises, mechanically amplifying moves.",
        ("no options dataset at all — no OI, volume, strike, expiry, IV or Greeks",),
    ),
    _blocked(
        "us_index_deletion",
        "US index-deletion forced selling",
        "US",
        "forced_selling",
        "Index funds must sell deletions regardless of price, on a known date.",
        ("no historical index membership data",),
    ),
    _blocked(
        "us_quality_value",
        "US quality-value combination",
        "US",
        "fundamental",
        "Cheap-and-profitable firms are systematically underpriced because investors "
        "extrapolate recent growth.",
        (
            "SEC Company Facts extract not pulled into the research cache (2.8GB; available with "
            "real known_at point-in-time gating from 2018-07-19)",
        ),
    ),
    _blocked(
        "dse_sponsor_accumulation",
        "DSE sponsor/insider accumulation",
        "DSE",
        "ownership",
        "Sponsors buying into their own float signals private information and simultaneously "
        "reduces tradeable supply.",
        (
            "DSE shareholding history is sparse: 1,567 rows across 395 codes (~4 snapshots each)",
            "no corporate-action adjustment to measure the price response cleanly",
        ),
    ),
    _blocked(
        "dse_circuit_transition",
        "DSE behaviour after circuit-limit sessions",
        "DSE",
        "structure",
        "A limit-locked session leaves unfilled demand that carries into the next session.",
        ("effective-dated DSE circuit-limit rules are not stored; limits changed over the period",),
    ),
    _blocked(
        "dse_low_float_demand",
        "DSE low-float supply squeeze",
        "DSE",
        "structure",
        "A small free float means modest demand moves price a lot.",
        ("free_float_cap_mn is a current snapshot with no history — cannot be used point-in-time",),
    ),
    _blocked(
        "us_catalyst_continuation",
        "US catalyst continuation",
        "US",
        "catalyst",
        "Scheduled catalysts concentrate information release.",
        ("catalyst archive began July 2026; US windows are inferred, never confirmed",),
    ),
    _blocked(
        "us_scalp_intraday",
        "US intraday scalp",
        "US",
        "intraday",
        "Intraday liquidity provision.",
        ("no US intraday history whatsoever",),
    ),
    _blocked(
        "dse_scalp_intraday",
        "DSE intraday scalp / session VWAP pullback",
        "DSE",
        "intraday",
        "The owner's preferred mechanism in its native form: a micro-pullback to session VWAP.",
        ("DSE intraday history is FOUR sessions (2026-07-20 to 2026-07-23) — verified 2026-07-25",),
    ),
    _blocked(
        "us_13f_cloning",
        "US 13F institutional-ownership change",
        "US",
        "ownership",
        "Skilled managers' position changes carry information.",
        ("13F history is 8 quarters with a 45-day lag — no usable sample",),
    ),
)

ALL: tuple[Registered, ...] = PRICE_BASED + INSIDER + BLOCKED
