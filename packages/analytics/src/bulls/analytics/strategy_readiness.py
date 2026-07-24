"""Declarative readiness catalog for every Atlas strategy family, including blocked ones.

The registry in ``research_strategy.STRATEGIES`` holds only implemented, runnable strategies.
This catalog is wider: it records every evaluated strategy family, its evidentiary status, and —
for anything not ready — the exact datasets that are missing. The catalog is the single place
the API and UI may read "why is this blocked" from, so the reason shown to an operator is always
the reason the research audit established, not prose invented at render time.

Statuses:
    ``backtest_ready``  — point-in-time inputs exist for a gated historical run.
    ``diagnostic_only`` — the engine can run it, but a known data defect (survivorship,
                          missing adjustments, short history) caps the result at diagnostic;
                          it can never satisfy promotion gates on current data.
    ``blocked``         — a required dataset does not exist at all; the engine must refuse.

Sources for the dataset facts: the 2026-07-24 production inventory (see
``docs/research/atlas-decision-archive-audit-2026-07-24.md`` section C) and
``docs/research/atlas-model-certification.md``.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

ReadinessStatus = Literal["backtest_ready", "diagnostic_only", "blocked"]
Direction = Literal["long", "short", "long_short"]


class MissingDataset(BaseModel):
    key: str = Field(min_length=1)
    description: str = Field(min_length=1)


class StrategyReadiness(BaseModel):
    key: str = Field(min_length=1, max_length=64)
    name: str
    market: Literal["DSE", "US"]
    direction: Direction
    horizon: Literal["scalp", "swing", "position"]
    implemented_strategy_key: str | None = None
    status: ReadinessStatus
    economic_hypothesis: str
    rationale: str
    missing_data: list[MissingDataset] = Field(default_factory=list)


_US_SURVIVORSHIP = MissingDataset(
    key="us_delisted_price_history",
    description=(
        "Delisted/acquired US price histories: only ~50 of ~11k stored symbols are inactive, "
        "so multi-year backtests run on survivors and overstate returns."
    ),
)
_US_MEMBERSHIP = MissingDataset(
    key="us_historical_universe_membership",
    description=(
        "Point-in-time listing/universe membership: security_listing_observations began "
        "2026-07-17; historical eligibility cannot be reconstructed before that."
    ),
)
_DSE_ADJUSTMENTS = MissingDataset(
    key="dse_corporate_action_adjustments",
    description=(
        "DSE daily bars carry no adjusted closes; bonus/rights/split ex-dates appear as raw "
        "price moves and contaminate any return, stop, or signal computed across them."
    ),
)
_DSE_HISTORY = MissingDataset(
    key="dse_price_history_depth",
    description=(
        "DSE bars start 2024-06-27 (~492 sessions); the 756-session historical gate cannot "
        "pass, and no full regime cycle is observable."
    ),
)
_BORROW = MissingDataset(
    key="us_borrow_locate_dataset",
    description=(
        "Point-in-time borrow availability, locate outcomes, borrow fees, recall/buy-in and "
        "squeeze controls. FINRA daily short-marked volume is not a substitute."
    ),
)
_INTRADAY_DSE = MissingDataset(
    key="dse_intraday_history",
    description=(
        "DSE intraday capture began 2026-07-20 (four sessions); no intraday backtest or "
        "realistic scalp execution evidence exists."
    ),
)
_INTRADAY_US = MissingDataset(
    key="us_intraday_history",
    description="No US intraday bars are stored at all.",
)
_F13_HISTORY = MissingDataset(
    key="us_13f_depth",
    description=(
        "13F aggregates cover 2024-06-30 through 2026-03-31 (~8 quarters) with a 45-day lag — "
        "far below the sample needed for an ownership-change strategy."
    ),
)
_OPTIONS = MissingDataset(
    key="us_options_dataset",
    description="No options dataset is licensed or stored (Cboe evaluation pending).",
)
_MARKET_EQUITY_HISTORY = MissingDataset(
    key="us_historical_market_equity",
    description=(
        "Historical shares outstanding x price for the full window plus NYSE/AMEX/NASDAQ "
        "exchange tags — required for published-factor reproduction and value-weighted sleeves."
    ),
)

STRATEGY_READINESS: dict[str, StrategyReadiness] = {
    entry.key: entry
    for entry in (
        StrategyReadiness(
            key="dse_reversal_v1",
            name="DSE liquid mean reversion",
            market="DSE",
            direction="long",
            horizon="swing",
            implemented_strategy_key="dse_reversal_v1",
            status="diagnostic_only",
            economic_hypothesis=(
                "Retail-dominated overreaction in liquid DSE names mean-reverts over days to "
                "weeks once forced flows exhaust."
            ),
            rationale=(
                "Runs on raw closes with frequent bonus/rights issues unadjusted, and on ~2 "
                "years of history; both defeat promotion-grade evidence."
            ),
            missing_data=[_DSE_ADJUSTMENTS, _DSE_HISTORY],
        ),
        StrategyReadiness(
            key="dse_trend_pullback",
            name="DSE trend continuation / micro-pullback",
            market="DSE",
            direction="long",
            horizon="swing",
            status="diagnostic_only",
            economic_hypothesis=(
                "Strong-trend names with controlled pullbacks continue as under-reaction "
                "resolves; the owner's preferred setup, adopted only on evidence."
            ),
            rationale="Same corporate-action and history-depth defects as every DSE backtest.",
            missing_data=[_DSE_ADJUSTMENTS, _DSE_HISTORY],
        ),
        StrategyReadiness(
            key="dse_scalp",
            name="DSE intraday scalping",
            market="DSE",
            direction="long",
            horizon="scalp",
            status="blocked",
            economic_hypothesis="Intraday liquidity provision / momentum bursts.",
            rationale="Four sessions of intraday data; no execution evidence of any kind.",
            missing_data=[_INTRADAY_DSE],
        ),
        StrategyReadiness(
            key="us_breakout_v1",
            name="US volatility-contraction breakout",
            market="US",
            direction="long",
            horizon="swing",
            implemented_strategy_key="us_breakout_v1",
            status="diagnostic_only",
            economic_hypothesis=(
                "Range compression with rising participation resolves upward when supply is "
                "absorbed (under-reaction / limited attention)."
            ),
            rationale=(
                "Ten years of adjusted bars exist, but the stored universe is survivors-only "
                "and historical membership is unreconstructable — breakout stats on survivors "
                "are inflated by construction."
            ),
            missing_data=[_US_SURVIVORSHIP, _US_MEMBERSHIP],
        ),
        StrategyReadiness(
            key="us_liquid_mean_reversion",
            name="US large-cap liquid mean reversion",
            market="US",
            direction="long",
            horizon="swing",
            status="diagnostic_only",
            economic_hypothesis=(
                "Short-horizon overreaction in continuously listed mega/large caps reverts; "
                "delisting risk is structurally lowest in this tier, which bounds the "
                "survivorship error instead of ignoring it."
            ),
            rationale=(
                "Nearest-to-ready US price strategy: restricting to mega/large caps with "
                "continuous 10-year listings makes the survivorship error small and "
                "quantifiable, but it must still be measured before promotion evidence counts."
            ),
            missing_data=[_US_SURVIVORSHIP],
        ),
        StrategyReadiness(
            key="us_insider_cluster_v1",
            name="US insider-purchase clusters (System A)",
            market="US",
            direction="long",
            horizon="position",
            implemented_strategy_key="us_insider_cluster_v1",
            status="diagnostic_only",
            economic_hypothesis=(
                "Clustered, opportunistic open-market officer/director purchases carry "
                "information (Cohen-Malloy-Pomorski); dissemination-time entry captures the "
                "documented drift."
            ),
            rationale=(
                "Events are point-in-time via EDGAR accepted_at (strong), but issuers that "
                "later delisted are missing from the price store, so bad outcomes are "
                "under-sampled."
            ),
            missing_data=[_US_SURVIVORSHIP],
        ),
        StrategyReadiness(
            key="us_activist_13d_v1",
            name="US activist 13D follower (preregistered roster)",
            market="US",
            direction="long",
            horizon="position",
            implemented_strategy_key="us_activist_13d_v1",
            status="diagnostic_only",
            economic_hypothesis=(
                "Campaigns by documented multi-campaign activists produce ~7% abnormal "
                "returns without one-year reversal (Brav et al.); filer identity, not the "
                "aggregate 13D tape, carries the edge."
            ),
            rationale=(
                "13D/G events exist point-in-time from 2021-06; the sample is thin and the "
                "price store is survivors-only, so results stay diagnostic."
            ),
            missing_data=[_US_SURVIVORSHIP],
        ),
        StrategyReadiness(
            key="us_forced_seller_v1",
            name="US forced-seller / spin-off dislocation (System B)",
            market="US",
            direction="long",
            horizon="position",
            implemented_strategy_key="us_forced_seller_v1",
            status="blocked",
            economic_hypothesis=(
                "Non-fundamental supply (index deletion, spin-off toxic waste, fund "
                "liquidation) depresses prices; drift concentrates in year two "
                "(Cusatis-Miles-Woolridge)."
            ),
            rationale=(
                "Preregistered event datasets (spin-off ex-dates, index deletions, forced "
                "flows) have not been built; the certification doc keeps System B parked."
            ),
            missing_data=[
                MissingDataset(
                    key="us_forced_flow_events",
                    description=(
                        "Point-in-time spin-off distributions, index add/delete events and "
                        "fund-liquidation records with dissemination timestamps."
                    ),
                ),
                _US_SURVIVORSHIP,
            ],
        ),
        StrategyReadiness(
            key="us_factor_sleeve_v1",
            name="US value-quality-momentum factor sleeve (System C)",
            market="US",
            direction="long",
            horizon="position",
            implemented_strategy_key="us_factor_sleeve_v1",
            status="diagnostic_only",
            economic_hypothesis=(
                "Compensated factor premia (value, quality, momentum, low-vol tilt) harvested "
                "in a liquidity-screened sleeve with monthly rebalance."
            ),
            rationale=(
                "SEC Company Facts are point-in-time from 2018 (strong), but the sleeve "
                "universe is survivors-only and the published-momentum reproduction control "
                "is blocked on historical market equity and exchange membership."
            ),
            missing_data=[_US_SURVIVORSHIP, _US_MEMBERSHIP, _MARKET_EQUITY_HISTORY],
        ),
        StrategyReadiness(
            key="us_earnings_drift",
            name="US post-disclosure drift (small-cap only)",
            market="US",
            direction="long",
            horizon="swing",
            status="diagnostic_only",
            economic_hypothesis=(
                "Residual post-earnings drift survives only in small, low-attention names "
                "(Martineau 2022 kills it in non-microcaps); costs decide everything."
            ),
            rationale=(
                "known_at-stamped Company Facts exist from 2018; small-cap execution costs "
                "and survivorship must both be measured before any claim."
            ),
            missing_data=[_US_SURVIVORSHIP],
        ),
        StrategyReadiness(
            key="us_13f_ownership_change",
            name="US institutional-ownership change follower",
            market="US",
            direction="long",
            horizon="position",
            status="blocked",
            economic_hypothesis=(
                "Concentrated, low-turnover managers' top overweights carry conditional "
                "information (Cohen-Polk-Silli); aggregate 13F flow does not."
            ),
            rationale=(
                "Only ~8 quarters of 13F aggregates exist with a 45-day lag — no sample. "
                "13F omits shorts and swaps entirely; must never be described as live flow."
            ),
            missing_data=[_F13_HISTORY],
        ),
        StrategyReadiness(
            key="us_short_breakdown",
            name="US short-side breakdown / failed breakout",
            market="US",
            direction="short",
            horizon="swing",
            status="blocked",
            economic_hypothesis=(
                "Distribution and failed breakouts resolve downward; short carry costs and "
                "squeeze risk dominate realized economics."
            ),
            rationale=(
                "Research may model the signal, but no paper short may ever fill without "
                "borrow/locate/fee/recall data; direction capability is fail-closed."
            ),
            missing_data=[_BORROW, _US_SURVIVORSHIP],
        ),
        StrategyReadiness(
            key="us_long_short_rv",
            name="US long/short relative value",
            market="US",
            direction="long_short",
            horizon="position",
            status="blocked",
            economic_hypothesis="Convergence between economically linked pairs/sleeves.",
            rationale="Short leg blocked on borrow data; factor infrastructure incomplete.",
            missing_data=[_BORROW, _US_MEMBERSHIP, _MARKET_EQUITY_HISTORY],
        ),
        StrategyReadiness(
            key="us_scalp",
            name="US intraday scalping",
            market="US",
            direction="long",
            horizon="scalp",
            status="blocked",
            economic_hypothesis="Intraday microstructure edges.",
            rationale="No US intraday data exists at all.",
            missing_data=[_INTRADAY_US],
        ),
        StrategyReadiness(
            key="us_catalyst_continuation",
            name="US catalyst-window continuation",
            market="US",
            direction="long",
            horizon="swing",
            status="diagnostic_only",
            economic_hypothesis=(
                "Confirmed catalysts with verified outcomes extend moves as attention and "
                "position adjustment complete."
            ),
            rationale=(
                "research_catalyst_events exists but is weeks old; US windows are inferred "
                "from filing cadence, not confirmed dates. Collect forward before testing."
            ),
            missing_data=[
                MissingDataset(
                    key="catalyst_outcome_history",
                    description=(
                        "A seasoned catalyst archive with realized outcomes; the table began "
                        "collecting in July 2026."
                    ),
                )
            ],
        ),
        StrategyReadiness(
            key="us_options_flow",
            name="US options-signal strategies",
            market="US",
            direction="long",
            horizon="swing",
            status="blocked",
            economic_hypothesis="Directional/positioning information in options order flow.",
            rationale="No options dataset is licensed; Cboe evaluation is pending.",
            missing_data=[_OPTIONS],
        ),
        StrategyReadiness(
            key="dse_sponsor_accumulation",
            name="DSE sponsor/insider accumulation",
            market="DSE",
            direction="long",
            horizon="position",
            status="diagnostic_only",
            economic_hypothesis=(
                "Sponsor-director purchases and rising sponsor ownership in a sound company "
                "signal informed accumulation in a disclosure-driven market."
            ),
            rationale=(
                "DSE insider-category disclosures and monthly ownership snapshots exist, but "
                "snapshot coverage is sparse and only ~2 years of aligned price history "
                "exists; corporate-action adjustment is also missing."
            ),
            missing_data=[_DSE_ADJUSTMENTS, _DSE_HISTORY],
        ),
        # ---- Squeeze taxonomy families (docs/research/squeeze-research-2026-07-24.md) ----
        StrategyReadiness(
            key="us_short_squeeze",
            name="US short squeeze",
            market="US",
            direction="long",
            horizon="swing",
            status="diagnostic_only",
            economic_hypothesis=(
                "A constrained float with materially elevated short positioning, rising borrow "
                "pressure, improving structure and abnormal demand may force covering when "
                "resistance breaks."
            ),
            rationale=(
                "FINRA bi-monthly consolidated short interest now supplies authoritative "
                "positioning — open short position, days-to-cover, and change versus the prior "
                "settlement — gated on its dissemination date, so short interest may finally be "
                "described as such. Two defects cap every result below promotion: the ratio is "
                "against shares outstanding because Atlas has no verified US free float (0 of "
                "~11k symbols), and positioning is fortnightly and up to two weeks stale by "
                "construction. Borrow, cost-to-borrow, locates and FTDs remain absent, so squeeze "
                "*mechanics* cannot be confirmed and SHORT EXECUTION STAYS BLOCKED — this is a "
                "long-side research family only."
            ),
            missing_data=[
                MissingDataset(
                    key="us_free_float",
                    description=(
                        "Verified US free float, so short interest can be expressed as % of "
                        "float rather than the understating % of shares outstanding."
                    ),
                ),
                _BORROW,
                MissingDataset(
                    key="us_ftd_regsho",
                    description=(
                        "SEC failures-to-deliver files and Reg SHO threshold status "
                        "(free; not yet ingested)."
                    ),
                ),
            ],
        ),
        StrategyReadiness(
            key="us_gamma_squeeze",
            name="US gamma/options squeeze",
            market="US",
            direction="long",
            horizon="swing",
            status="blocked",
            economic_hypothesis=(
                "Concentrated near-dated call open interest can force dealer hedge-buying as "
                "spot approaches high-gamma strikes; decays hard after expiry."
            ),
            rationale=(
                "No option-chain history (OI, volume, IV, Greeks) exists; without "
                "opening/closing classification, option volume cannot prove new positioning, "
                "and any dealer-gamma sign would be an assumption that must be labeled."
            ),
            missing_data=[_OPTIONS],
        ),
        StrategyReadiness(
            key="us_float_liquidity_squeeze",
            name="US float/liquidity squeeze",
            market="US",
            direction="long",
            horizon="swing",
            status="blocked",
            economic_hypothesis=(
                "Scarce tradable supply meeting abnormal demand produces outsized moves "
                "without any short-positioning requirement."
            ),
            rationale=(
                "Verified US free float is absent (0 of ~11k symbols). Shares outstanding "
                "exists point-in-time but was rejected as a float proxy — it systematically "
                "understates scarcity and would fabricate the family's core feature."
            ),
            missing_data=[
                MissingDataset(
                    key="us_verified_free_float",
                    description=(
                        "Verified free float (outstanding minus insider/strategic lockups) "
                        "per symbol with history."
                    ),
                )
            ],
        ),
        StrategyReadiness(
            key="failed_breakdown_reversal",
            name="Failed-breakdown reversal (squeeze monitor)",
            market="US",
            direction="long",
            horizon="swing",
            status="diagnostic_only",
            economic_hypothesis=(
                "A support undercut that is rapidly reclaimed with participation traps late "
                "sellers; named honestly — without positioning data it is never called a "
                "confirmed short squeeze."
            ),
            rationale=(
                "Implemented in the squeeze monitor as a taxonomy (squeeze-monitor-v1); no "
                "backtest has validated it and the US price store is survivors-only."
            ),
            missing_data=[_US_SURVIVORSHIP],
        ),
        StrategyReadiness(
            key="dse_supply_constrained_breakout",
            name="DSE supply-constrained breakout",
            market="DSE",
            direction="long",
            horizon="swing",
            status="diagnostic_only",
            economic_hypothesis=(
                "Verified scarce free float or sponsor-locked supply meeting compression and "
                "accumulation resolves upward on demand shocks — a supply/demand condition, "
                "not a short squeeze (DSE has no short-sale mechanism)."
            ),
            rationale=(
                "Implemented in the squeeze monitor (DSE free float is verified for 359/396 "
                "symbols); raw closes and ~2 years of history cap it at diagnostic."
            ),
            missing_data=[_DSE_ADJUSTMENTS, _DSE_HISTORY],
        ),
    )
}


def readiness_for_market(market: Literal["DSE", "US"]) -> list[StrategyReadiness]:
    return [entry for entry in STRATEGY_READINESS.values() if entry.market == market]
