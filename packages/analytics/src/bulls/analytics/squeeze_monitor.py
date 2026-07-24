"""Deterministic squeeze-taxonomy evaluator (methodology ``squeeze-monitor-v1``).

Design contract (docs/research/squeeze-research-2026-07-24.md): pure functions over completed
EOD inputs; no I/O, no LLM, no composite score. Each family produces a typed assessment with a
state, price geometry, evidence and counter-evidence, and an explicit reason for any state
change. Families whose authoritative datasets do not exist are *registered as blocked* by the
caller, never silently approximated here — in particular, nothing in this module may emit the
words "short squeeze": Atlas has no short-interest or borrow data, and FINRA daily short-marked
volume cannot establish positioning.
"""

from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import BaseModel, Field

METHODOLOGY_VERSION = "squeeze-monitor-v1"

type SqueezeFamily = Literal[
    "compression_breakout",
    "failed_breakdown_reversal",
    "supply_constrained_breakout",
]
type SqueezeState = Literal[
    "watch",
    "forming",
    "trigger_ready",
    "confirmed",
    "exhausted",
    "failed",
    "none",
]

FAMILY_LABELS: dict[SqueezeFamily, str] = {
    "compression_breakout": "Compression breakout setup",
    "failed_breakdown_reversal": "Failed-breakdown reversal",
    "supply_constrained_breakout": "Supply-constrained breakout",
}

# v1 thresholds — priors, not fitted values. Changing any of them is a methodology bump.
NEAR_HIGH_PCT = -15.0
ATR_CONTRACTION_RATIO = 0.8
DRY_UP_REL_VOLUME_5D = 0.9
TIGHT_RANGE_ATR_MULTIPLE = 1.5
TRIGGER_PROXIMITY = 0.03
BREAKOUT_REL_VOLUME = 1.5
RECLAIM_REL_VOLUME = 1.2
FAILURE_TRIGGER_FRACTION = 0.97
EXHAUSTION_SMA50_EXTENSION = 1.25
EXHAUSTION_3S_GAIN = 0.20
SUPPORT_WINDOW = (11, 60)  # sessions ago (inclusive) used for reference support
UNDERCUT_FRACTION = 0.99
RECLAIM_FRACTION = 1.02
BASE_WINDOW = 20
FLOAT_SCARCITY_RATIO = 0.35
SPONSOR_CONCENTRATION_PCT = 50.0


class SqueezeBar(BaseModel):
    date: dt.date
    open: float = Field(gt=0)
    high: float = Field(gt=0)
    low: float = Field(gt=0)
    close: float = Field(gt=0)
    volume: float = Field(ge=0)


class SqueezeInputs(BaseModel):
    """Completed-data inputs for one ticker. Optional fields degrade to missing-evidence notes."""

    market: Literal["DSE", "US"]
    code: str
    bars: list[SqueezeBar]  # ascending, ~120 completed sessions
    last_close: float = Field(gt=0)
    sma_50: float | None = None
    sma_200: float | None = None
    pct_from_52w_high: float | None = None
    relative_volume: float | None = None
    rel_volume_5d: float | None = None
    cmf_20: float | None = None
    obv_slope: float | None = None
    avg_volume_20: float | None = None
    market_cap_mn: float | None = None
    free_float_cap_mn: float | None = None
    sponsor_pct: float | None = None
    institute_delta: float | None = None
    foreign_delta: float | None = None
    # US supporting context only — worded by this module, never as positioning evidence.
    short_marked_share_5d: float | None = None
    recent_dilution_filing: bool = False
    insider_net_selling_30d: bool = False
    prior_state: SqueezeState = "none"
    prior_trigger_price: float | None = None


class SqueezeAssessment(BaseModel):
    family: SqueezeFamily
    state: SqueezeState
    setup_price: float | None
    trigger_price: float | None
    invalidation_price: float | None
    risk_per_share: float | None
    planning_objective_price: float | None  # trigger + 2R — risk geometry, never a forecast
    expected_holding: str
    supporting_evidence: list[str]
    counter_evidence: list[str]
    data_quality: list[str]
    missing_evidence: list[str]
    reason: str
    methodology_version: str = METHODOLOGY_VERSION


def _atr(bars: list[SqueezeBar], period: int = 14) -> float | None:
    if len(bars) < period + 1:
        return None
    true_ranges = []
    for previous, current in zip(bars[-period - 1 : -1], bars[-period:], strict=True):
        true_ranges.append(
            max(
                current.high - current.low,
                abs(current.high - previous.close),
                abs(current.low - previous.close),
            )
        )
    return sum(true_ranges) / period


def _round(value: float | None) -> float | None:
    return round(value, 6) if value is not None else None


def _geometry(
    trigger: float | None, invalidation: float | None
) -> tuple[float | None, float | None]:
    if trigger is None or invalidation is None or trigger <= invalidation:
        return None, None
    risk = trigger - invalidation
    return _round(risk), _round(trigger + 2 * risk)


def _common_context(inputs: SqueezeInputs) -> tuple[list[str], list[str], list[str]]:
    """Supporting / counter / data-quality strings shared by every family."""

    supporting: list[str] = []
    counter: list[str] = []
    quality: list[str] = []
    if (
        inputs.market == "US"
        and inputs.short_marked_share_5d is not None
        and inputs.short_marked_share_5d >= 0.60
    ):
        supporting.append(
            f"Short-marked volume share elevated ({inputs.short_marked_share_5d:.0%} "
            "5-session, volume-weighted) — this is not short interest and cannot "
            "establish positioning."
        )
    if inputs.recent_dilution_filing:
        counter.append(
            "Recent financing/dilution filing (S-1/S-3/424B family) within 90 days."
        )
    if inputs.insider_net_selling_30d:
        counter.append("Net insider open-market selling within 30 days.")
    if inputs.market == "DSE":
        quality.append(
            "DSE prices are raw exchange closes without corporate-action adjustment; a bonus "
            "or rights ex-date can flip this state."
        )
        if inputs.institute_delta is not None and inputs.institute_delta < 0:
            counter.append("Institutional holding declined in the latest monthly snapshot.")
        if inputs.foreign_delta is not None and inputs.foreign_delta < 0:
            counter.append("Foreign holding declined in the latest monthly snapshot.")
    if inputs.market == "US":
        quality.append(
            "US universe currently stores survivors only; archived setups over-represent "
            "companies that did not delist."
        )
    return supporting, counter, quality


def _eligible(inputs: SqueezeInputs) -> tuple[bool, list[str]]:
    missing: list[str] = []
    if inputs.sma_200 is None:
        missing.append("200-session average unavailable (insufficient history).")
    if len(inputs.bars) < 60:
        missing.append("Fewer than 60 completed sessions of price history.")
    if inputs.sma_200 is not None and inputs.last_close <= inputs.sma_200:
        return False, missing
    return not missing, missing


def _exhaustion(inputs: SqueezeInputs) -> str | None:
    """Cross-family too-late detector. Returns the reason string when late."""

    if inputs.sma_50 is not None and inputs.last_close > inputs.sma_50 * EXHAUSTION_SMA50_EXTENSION:
        return (
            f"Too extended: close is more than {EXHAUSTION_SMA50_EXTENSION - 1:.0%} above the "
            "50-session average."
        )
    bars = inputs.bars
    if len(bars) >= 4:
        gain_3s = bars[-1].close / bars[-4].close - 1
        if gain_3s > EXHAUSTION_3S_GAIN and (
            inputs.relative_volume is not None and inputs.relative_volume < 1.0
        ):
            return "Too extended: >20% three-session gain with fading participation."
        recent_high = max(bar.high for bar in bars[-BASE_WINDOW:])
        upper_wicks = sum(
            1
            for bar in bars[-3:]
            if bar.high > bar.low and (bar.close - bar.low) / (bar.high - bar.low) < 0.5
        )
        if bars[-1].high >= recent_high and upper_wicks >= 2 and gain_3s > 0.08:
            return "Too extended: repeated upper wicks at a fresh 20-session high."
    return None


def evaluate_compression_breakout(inputs: SqueezeInputs) -> SqueezeAssessment:
    supporting, counter, quality = _common_context(inputs)
    eligible, missing = _eligible(inputs)
    bars = inputs.bars
    # The base high/low exclude the most recent 3 sessions: confirmation is judged against the
    # base that existed *before* the candidate breakout candles, otherwise a breakout could
    # raise its own trigger and never confirm.
    base_bars = bars[-(BASE_WINDOW + 3) : -3] if len(bars) > BASE_WINDOW + 3 else bars[:-3]
    trigger = max((bar.high for bar in base_bars), default=None)
    invalidation = min((bar.low for bar in base_bars), default=None)
    risk, objective = _geometry(trigger, invalidation)

    def assessment(state: SqueezeState, reason: str) -> SqueezeAssessment:
        return SqueezeAssessment(
            family="compression_breakout",
            state=state,
            setup_price=_round(inputs.last_close),
            trigger_price=_round(trigger),
            invalidation_price=_round(invalidation),
            risk_per_share=risk,
            planning_objective_price=objective,
            expected_holding="Approximately 10-40 completed sessions",
            supporting_evidence=supporting,
            counter_evidence=counter,
            data_quality=quality,
            missing_evidence=missing,
            reason=reason,
        )

    if not eligible or trigger is None or invalidation is None:
        return assessment("none", "Eligibility preconditions not met.")

    # Failure check first: a previously archived trigger/confirmation that gave way.
    if (
        inputs.prior_state in {"trigger_ready", "confirmed"}
        and inputs.prior_trigger_price is not None
        and inputs.last_close < inputs.prior_trigger_price * FAILURE_TRIGGER_FRACTION
    ):
        return assessment(
            "failed",
            "Close fell below 97% of the archived trigger after the setup had "
            f"{inputs.prior_state.replace('_', ' ')} status.",
        )

    late = _exhaustion(inputs)
    if late is not None:
        return assessment("exhausted", late)

    near_high = inputs.pct_from_52w_high is not None and inputs.pct_from_52w_high >= NEAR_HIGH_PCT
    atr_now = _atr(bars)
    atr_then = _atr(bars[:-BASE_WINDOW]) if len(bars) > BASE_WINDOW + 15 else None
    contraction = (
        atr_now is not None and atr_then is not None and atr_now <= ATR_CONTRACTION_RATIO * atr_then
    )
    if contraction:
        supporting.append("Volatility contraction: 14-session ATR fell ≥20% over 20 sessions.")
    if inputs.rel_volume_5d is not None and inputs.rel_volume_5d < DRY_UP_REL_VOLUME_5D:
        supporting.append("Constructive volume dry-up (5-session volume below 60-session pace).")
    if inputs.cmf_20 is not None and inputs.cmf_20 > 0:
        supporting.append("Positive 20-session money flow (accumulation).")
    if inputs.obv_slope is not None and inputs.obv_slope > 0:
        supporting.append("Rising on-balance volume (participation leads price).")

    recently_confirmed = (
        any(bar.close > trigger for bar in bars[-3:])
        and inputs.relative_volume is not None
        and inputs.relative_volume >= BREAKOUT_REL_VOLUME
    )
    if recently_confirmed:
        return assessment(
            "confirmed",
            "Close exceeded the 20-session base high within the last 3 sessions with "
            f"relative volume ≥ {BREAKOUT_REL_VOLUME:.1f}x.",
        )
    if not near_high:
        return assessment("none", "Price is not within 15% of its 52-week high.")
    if contraction:
        atr_value = atr_now or 0.0
        recent = bars[-5:]
        recent_range = max(bar.high for bar in recent) - min(bar.low for bar in recent)
        tight = atr_value > 0 and recent_range <= TIGHT_RANGE_ATR_MULTIPLE * atr_value
        close_to_trigger = inputs.last_close >= trigger * (1 - TRIGGER_PROXIMITY)
        if tight and close_to_trigger:
            return assessment(
                "trigger_ready",
                "Base is tight (5-session range within 1.5 ATR) and price sits within 3% "
                "of the base high.",
            )
        return assessment("forming", "Base near the 52-week high with contracting volatility.")
    return assessment("watch", "Within 15% of the 52-week high; volatility not yet contracting.")


def evaluate_failed_breakdown(inputs: SqueezeInputs) -> SqueezeAssessment:
    supporting, counter, quality = _common_context(inputs)
    bars = inputs.bars
    missing: list[str] = []
    if len(bars) < SUPPORT_WINDOW[1] + 5:
        missing.append("Insufficient history to establish a reference support level.")

    def assessment(
        state: SqueezeState,
        reason: str,
        *,
        trigger: float | None = None,
        invalidation: float | None = None,
    ) -> SqueezeAssessment:
        risk, objective = _geometry(trigger, invalidation)
        return SqueezeAssessment(
            family="failed_breakdown_reversal",
            state=state,
            setup_price=_round(inputs.last_close),
            trigger_price=_round(trigger),
            invalidation_price=_round(invalidation),
            risk_per_share=risk,
            planning_objective_price=objective,
            expected_holding="Approximately 5-30 completed sessions",
            supporting_evidence=supporting,
            counter_evidence=counter,
            data_quality=quality,
            missing_evidence=missing,
            reason=reason,
        )

    if missing:
        return assessment("none", "Not enough completed history for this family.")
    support = min(bar.low for bar in bars[-SUPPORT_WINDOW[1] : -SUPPORT_WINDOW[0] + 1])
    recent = bars[-7:]
    undercut_bars = [bar for bar in recent if bar.low < support * UNDERCUT_FRACTION]
    if not undercut_bars:
        return assessment("none", "No support undercut in the last 7 sessions.")
    undercut_low = min(bar.low for bar in undercut_bars)
    trigger = support * RECLAIM_FRACTION
    if inputs.last_close < support * FAILURE_TRIGGER_FRACTION:
        # "Failed" is only meaningful for something that was previously a live setup. A stock
        # simply breaking down and continuing lower was never a reversal candidate, and
        # archiving it would fill the record with non-setups.
        if inputs.prior_state in {"watch", "forming", "trigger_ready", "confirmed"}:
            return assessment(
                "failed",
                "Price closed more than 3% below the broken support; the breakdown succeeded.",
                trigger=trigger,
                invalidation=undercut_low,
            )
        return assessment(
            "none",
            "Price is extending below support; this is an active breakdown, not a reversal "
            "setup.",
        )
    late = _exhaustion(inputs)
    if late is not None:
        return assessment("exhausted", late, trigger=trigger, invalidation=undercut_low)
    supporting.append(
        f"Support near {support:.2f} was undercut and price recovered above it — sellers "
        "failed to extend the move."
    )
    if (
        inputs.last_close >= trigger
        and inputs.relative_volume is not None
        and inputs.relative_volume >= RECLAIM_REL_VOLUME
    ):
        return assessment(
            "confirmed",
            "Close reclaimed 102% of the broken support with elevated participation. This is "
            "a failed-breakdown reversal; short-positioning evidence does not exist.",
            trigger=trigger,
            invalidation=undercut_low,
        )
    if inputs.last_close > support:
        return assessment(
            "forming",
            "Price is back above the undercut support but has not confirmed the reclaim "
            "with volume.",
            trigger=trigger,
            invalidation=undercut_low,
        )
    return assessment(
        "watch",
        "Undercut occurred; price has not yet recovered the support level.",
        trigger=trigger,
        invalidation=undercut_low,
    )


def evaluate_supply_constrained(inputs: SqueezeInputs) -> SqueezeAssessment:
    """DSE-only supply/demand family. Never described as a short squeeze."""

    base = evaluate_compression_breakout(inputs)
    missing = list(base.missing_evidence)
    supporting = list(base.supporting_evidence)
    scarcity = False
    if inputs.free_float_cap_mn is None or inputs.market_cap_mn in (None, 0):
        missing.append("Verified free float unavailable for this symbol.")
    else:
        ratio = inputs.free_float_cap_mn / inputs.market_cap_mn
        if ratio <= FLOAT_SCARCITY_RATIO:
            scarcity = True
            supporting.append(
                f"Free float is only {ratio:.0%} of market capitalization (supply scarcity)."
            )
        if (
            inputs.avg_volume_20 is not None
            and inputs.free_float_cap_mn > 0
        ):
            turnover = (
                inputs.avg_volume_20 * inputs.last_close / (inputs.free_float_cap_mn * 1_000_000)
            )
            supporting.append(
                f"20-session average turnover is {turnover:.2%} of the free-float value."
            )
    if inputs.sponsor_pct is not None and inputs.sponsor_pct >= SPONSOR_CONCENTRATION_PCT:
        scarcity = True
        supporting.append(
            f"Sponsor/director holding is {inputs.sponsor_pct:.0f}% (locked supply)."
        )
    if not scarcity:
        return base.model_copy(
            update={
                "family": "supply_constrained_breakout",
                "state": "none",
                "supporting_evidence": supporting,
                "missing_evidence": missing,
                "reason": "No verified supply-scarcity condition (float ratio or sponsor lock).",
            }
        )
    return base.model_copy(
        update={
            "family": "supply_constrained_breakout",
            "supporting_evidence": supporting,
            "missing_evidence": missing,
            "expected_holding": "Approximately 10-40 completed sessions",
            "reason": base.reason + " Supply-scarcity precondition is met.",
        }
    )


def evaluate_families(inputs: SqueezeInputs) -> list[SqueezeAssessment]:
    """Evaluate every family applicable to the input's market. Blocked families are the
    caller's concern (they are registered, not evaluated)."""

    assessments = [
        evaluate_compression_breakout(inputs),
        evaluate_failed_breakdown(inputs),
    ]
    if inputs.market == "DSE":
        assessments.append(evaluate_supply_constrained(inputs))
    return assessments
