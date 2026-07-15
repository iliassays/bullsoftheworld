"""Deterministic, evidence-bounded financial interpretation for Atlas research.

This module is intentionally narrower than a general language model. It converts registered facts
into finance-specific claim drafts, diagnostic lenses, conditional scenarios, and evidence requests.
It never fetches data, calculates authoritative source metrics, predicts prices, or makes portfolio
decisions. The research loop verifies every claim draft against the supplied fact ledger.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, Field


class FinancialLens(BaseModel):
    key: Literal[
        "fundamentals",
        "valuation",
        "market_structure",
        "liquidity_risk",
        "ownership_disclosure",
        "regulatory_positioning",
        "evidence_change",
    ]
    label: str
    assessment: Literal["constructive", "balanced", "caution", "unknown"]
    summary: str
    fact_keys: list[str] = Field(default_factory=list)


class FinancialScenario(BaseModel):
    key: Literal["base", "upside", "downside"]
    title: str
    state: Literal["current", "conditional"]
    condition: str
    implication: str
    watch_items: list[str]


class EvidenceRequest(BaseModel):
    priority: Literal["high", "medium", "routine"]
    question: str
    reason: str


@dataclass(frozen=True, slots=True)
class ClaimDraft:
    key: str
    side: Literal["supporting", "counter"]
    statement: str
    fact_keys: tuple[str, ...]
    confidence: float
    rule: str


@dataclass(frozen=True, slots=True)
class FinancialReasoningPack:
    claim_drafts: tuple[ClaimDraft, ...]
    lenses: tuple[FinancialLens, ...]
    scenarios: tuple[FinancialScenario, ...]
    evidence_requests: tuple[EvidenceRequest, ...]
    invalidation_rules: tuple[str, ...]


def _number(facts: dict[str, Any], key: str) -> float | None:
    value = facts.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _boolean(facts: dict[str, Any], key: str) -> bool | None:
    value = facts.get(key)
    return value if isinstance(value, bool) else None


def _text(facts: dict[str, Any], key: str) -> str | None:
    value = facts.get(key)
    return value if isinstance(value, str) and value.strip() else None


def _fmt(value: float, digits: int = 1) -> str:
    return f"{value:,.{digits}f}"


def _fundamental_lens(facts: dict[str, Any], claims: list[ClaimDraft]) -> FinancialLens:
    roe = _number(facts, "roe_pct")
    growth = _number(facts, "eps_growth_yoy_pct")
    keys = [
        key
        for key, value in (("roe_pct", roe), ("eps_growth_yoy_pct", growth))
        if value is not None
    ]
    if roe is None and growth is None:
        return FinancialLens(
            key="fundamentals",
            label="Earnings quality",
            assessment="unknown",
            summary="Profitability and earnings direction are not sufficiently populated.",
        )
    if growth is not None and growth < 0:
        claims.append(
            ClaimDraft(
                key="earnings_contraction",
                side="counter",
                statement=f"Normalized EPS growth is contracting ({_fmt(growth)}% year over year).",
                fact_keys=("eps_growth_yoy_pct",),
                confidence=0.9,
                rule="eps_growth_yoy_pct < 0",
            )
        )
    if roe is not None and roe < 0:
        claims.append(
            ClaimDraft(
                key="negative_profitability",
                side="counter",
                statement=f"Normalized return on equity is negative ({_fmt(roe)}%).",
                fact_keys=("roe_pct",),
                confidence=0.9,
                rule="roe_pct < 0",
            )
        )
    if roe is not None and growth is not None and roe >= 10 and growth >= 10:
        claims.append(
            ClaimDraft(
                key="fundamental_support",
                side="supporting",
                statement=(
                    f"Profitability and earnings direction align: ROE is {_fmt(roe)}% and "
                    f"normalized EPS growth is {_fmt(growth)}% year over year."
                ),
                fact_keys=("roe_pct", "eps_growth_yoy_pct"),
                confidence=0.9,
                rule="roe_pct >= 10 and eps_growth_yoy_pct >= 10",
            )
        )
        assessment = "constructive"
        summary = "Profitability and earnings growth currently reinforce each other."
    elif (growth is not None and growth < 0) or (roe is not None and roe < 0):
        assessment = "caution"
        summary = "At least one normalized earnings-quality measure is deteriorating."
    else:
        assessment = "balanced"
        components = []
        if roe is not None:
            components.append(f"ROE {_fmt(roe)}%")
        if growth is not None:
            components.append(f"EPS growth {_fmt(growth)}% YoY")
        summary = "; ".join(components) + ". The measures do not yet form a strong joint signal."
    return FinancialLens(
        key="fundamentals",
        label="Earnings quality",
        assessment=assessment,
        summary=summary,
        fact_keys=keys,
    )


def _valuation_lens(facts: dict[str, Any], claims: list[ClaimDraft]) -> FinancialLens:
    pe = _number(facts, "pe_ratio")
    pb = _number(facts, "pb_ratio")
    sector = _number(facts, "pe_vs_sector")
    growth = _number(facts, "eps_growth_yoy_pct")
    keys = [
        key
        for key, value in (("pe_ratio", pe), ("pb_ratio", pb), ("pe_vs_sector", sector))
        if value is not None
    ]
    if not keys:
        return FinancialLens(
            key="valuation",
            label="Valuation",
            assessment="unknown",
            summary="No normalized positive-earnings valuation comparison is available.",
        )
    if pe is not None and sector is not None and 0 < sector <= 0.85:
        claims.append(
            ClaimDraft(
                key="relative_valuation_support",
                side="supporting",
                statement=(
                    f"The positive-earnings P/E is {_fmt(pe, 2)}x, or {_fmt(sector, 2)}x "
                    "the sector median."
                ),
                fact_keys=("pe_ratio", "pe_vs_sector"),
                confidence=0.85,
                rule="pe_ratio > 0 and 0 < pe_vs_sector <= 0.85",
            )
        )
        assessment = "constructive" if growth is None or growth >= 0 else "caution"
        summary = (
            "The shares trade at a sector discount, but contracting earnings make the discount "
            "a possible value trap."
            if growth is not None and growth < 0
            else "The normalized positive-earnings multiple is below the sector median."
        )
    elif sector is not None and sector >= 1.25:
        claims.append(
            ClaimDraft(
                key="valuation_premium",
                side="counter",
                statement=f"The P/E is {_fmt(sector, 2)}x the sector median, leaving less valuation support.",
                fact_keys=("pe_vs_sector",),
                confidence=0.8,
                rule="pe_vs_sector >= 1.25",
            )
        )
        assessment = "caution"
        summary = "The market assigns a material premium to the normalized sector multiple."
    else:
        assessment = "balanced"
        values = []
        if pe is not None:
            values.append(f"P/E {_fmt(pe, 2)}x")
        if pb is not None:
            values.append(f"P/B {_fmt(pb, 2)}x")
        summary = "; ".join(values) + ". No strong sector-relative valuation edge is established."
    return FinancialLens(
        key="valuation",
        label="Valuation",
        assessment=assessment,
        summary=summary,
        fact_keys=keys,
    )


def _market_structure_lens(facts: dict[str, Any], claims: list[ClaimDraft]) -> FinancialLens:
    above_50 = _boolean(facts, "above_sma_50")
    above_200 = _boolean(facts, "above_sma_200")
    momentum_3m = _number(facts, "mom_3_1_pct")
    rsi = _number(facts, "rsi_14")
    relative_volume = _number(facts, "relative_volume")
    keys = [
        key
        for key, value in (
            ("above_sma_50", above_50),
            ("above_sma_200", above_200),
            ("mom_3_1_pct", momentum_3m),
            ("rsi_14", rsi),
            ("relative_volume", relative_volume),
        )
        if value is not None
    ]
    constructive = (
        above_50 is True
        and above_200 is True
        and momentum_3m is not None
        and momentum_3m > 0
        and (rsi is None or rsi < 75)
    )
    if constructive:
        fact_keys = ["above_sma_50", "above_sma_200", "mom_3_1_pct"]
        if rsi is not None:
            fact_keys.append("rsi_14")
        claims.append(
            ClaimDraft(
                key="price_structure_support",
                side="supporting",
                statement=(
                    "The completed-session trend is above both the 50- and 200-session averages, "
                    f"with {_fmt(momentum_3m)}% three-month momentum"
                    + (f" and RSI {_fmt(rsi)}." if rsi is not None else ".")
                ),
                fact_keys=tuple(fact_keys),
                confidence=0.9,
                rule="above_sma_50 and above_sma_200 and mom_3_1_pct > 0 and rsi_14 < 75",
            )
        )
    if rsi is not None and rsi >= 75:
        claims.append(
            ClaimDraft(
                key="extension_risk",
                side="counter",
                statement=f"RSI is {_fmt(rsi)}, indicating elevated entry-timing and crowding risk.",
                fact_keys=("rsi_14",),
                confidence=0.85,
                rule="rsi_14 >= 75",
            )
        )
    if above_50 is False and above_200 is False and momentum_3m is not None and momentum_3m < 0:
        claims.append(
            ClaimDraft(
                key="trend_deterioration",
                side="counter",
                statement=(
                    "The completed-session price is below both major moving averages and "
                    f"three-month momentum is {_fmt(momentum_3m)}%."
                ),
                fact_keys=("above_sma_50", "above_sma_200", "mom_3_1_pct"),
                confidence=0.9,
                rule="not above_sma_50 and not above_sma_200 and mom_3_1_pct < 0",
            )
        )
    if constructive:
        assessment = "constructive"
        summary = "Trend alignment is constructive on completed sessions."
    elif rsi is not None and rsi >= 75:
        assessment = "caution"
        summary = "The move is extended enough that timing risk dominates the technical read."
    elif above_50 is False and above_200 is False:
        assessment = "caution"
        summary = "The completed-session trend remains below both major moving averages."
    elif keys:
        assessment = "balanced"
        summary = "The available trend and participation measures are mixed."
    else:
        assessment = "unknown"
        summary = "Trend structure is not sufficiently populated."
    return FinancialLens(
        key="market_structure",
        label="Price structure",
        assessment=assessment,
        summary=summary,
        fact_keys=keys,
    )


def _liquidity_lens(
    *,
    market: Literal["DSE", "US"],
    cap_tier: str,
    facts: dict[str, Any],
    flags: set[str],
    claims: list[ClaimDraft],
) -> FinancialLens:
    adv = _number(facts, "average_daily_value_mn")
    volatility = _number(facts, "volatility_pct")
    threshold = 55.0 if market == "DSE" else 80.0
    keys = [
        key
        for key, value in (("average_daily_value_mn", adv), ("volatility_pct", volatility))
        if value is not None
    ]
    keys.append("cap_tier")
    if cap_tier in {"micro", "penny"}:
        claims.append(
            ClaimDraft(
                key="small_cap_fragility",
                side="counter",
                statement=(
                    f"The {cap_tier}-capitalization tier increases liquidity, financing, and gap risk."
                ),
                fact_keys=("cap_tier",),
                confidence=1.0,
                rule="cap_tier in {'micro', 'penny'}",
            )
        )
    if volatility is not None and volatility >= threshold:
        claims.append(
            ClaimDraft(
                key="high_volatility",
                side="counter",
                statement=(
                    f"Annualized completed-session volatility is {_fmt(volatility)}%, above the "
                    f"{market} research threshold of {_fmt(threshold, 0)}%."
                ),
                fact_keys=("volatility_pct",),
                confidence=0.95,
                rule=f"volatility_pct >= {threshold}",
            )
        )
    if "Below liquidity floor" in flags:
        assessment = "caution"
        summary = "Average traded value is below the market policy's research liquidity floor."
    elif cap_tier in {"micro", "penny"} or (volatility is not None and volatility >= threshold):
        assessment = "caution"
        summary = "Size or volatility creates a material implementation burden."
    elif adv is None:
        assessment = "unknown"
        summary = "Executable capacity cannot be assessed because average traded value is missing."
    else:
        assessment = "balanced"
        summary = f"Average completed-session traded value is {_fmt(adv, 2)} million; sizing remains policy-bounded."
    return FinancialLens(
        key="liquidity_risk",
        label="Liquidity and risk",
        assessment=assessment,
        summary=summary,
        fact_keys=keys,
    )


def _dse_ownership_lens(facts: dict[str, Any], claims: list[ClaimDraft]) -> FinancialLens:
    ownership = _number(facts, "institutional_ownership_pct")
    change = _number(facts, "institutional_ownership_change_pp")
    as_of = _text(facts, "ownership_as_of_date")
    if ownership is None:
        return FinancialLens(
            key="ownership_disclosure",
            label="Reported ownership",
            assessment="unknown",
            summary="No validated periodic ownership composition is available at the cutoff.",
        )
    suffix = f" as of {as_of}" if as_of else ""
    if change is not None and change >= 0.5:
        claims.append(
            ClaimDraft(
                key="reported_institutional_increase",
                side="supporting",
                statement=(
                    f"Reported institutional ownership increased {change:+.2f} percentage points "
                    f"to {ownership:.2f}%{suffix}; the disclosure does not reveal trade dates."
                ),
                fact_keys=(
                    "institutional_ownership_pct",
                    "institutional_ownership_change_pp",
                    "ownership_as_of_date",
                ),
                confidence=0.8,
                rule="institutional_ownership_change_pp >= 0.5",
            )
        )
        assessment = "constructive"
        summary = "The latest periodic disclosure shows higher institutional ownership, not live fund flow."
    elif change is not None and change <= -0.5:
        claims.append(
            ClaimDraft(
                key="reported_institutional_decrease",
                side="counter",
                statement=(
                    f"Reported institutional ownership decreased {change:.2f} percentage points "
                    f"to {ownership:.2f}%{suffix}; the disclosure does not reveal trade dates."
                ),
                fact_keys=(
                    "institutional_ownership_pct",
                    "institutional_ownership_change_pp",
                    "ownership_as_of_date",
                ),
                confidence=0.8,
                rule="institutional_ownership_change_pp <= -0.5",
            )
        )
        assessment = "caution"
        summary = "The latest periodic disclosure shows lower institutional ownership, not session-level selling."
    else:
        assessment = "balanced"
        change_text = "no prior comparison" if change is None else f"{change:+.2f} pp change"
        summary = f"Reported institutional ownership is {ownership:.2f}% ({change_text}){suffix}."
    return FinancialLens(
        key="ownership_disclosure",
        label="Reported ownership",
        assessment=assessment,
        summary=summary,
        fact_keys=[
            key
            for key in (
                "institutional_ownership_pct",
                "institutional_ownership_change_pp",
                "ownership_as_of_date",
            )
            if facts.get(key) is not None
        ],
    )


def _us_positioning_lens(facts: dict[str, Any], claims: list[ClaimDraft]) -> FinancialLens:
    breadth = _number(facts, "13f_net_breadth_pct")
    net_change = _number(facts, "13f_net_change_pct")
    managers = _number(facts, "13f_manager_count")
    report_date = _text(facts, "13f_report_date")
    finra = _number(facts, "finra_short_marked_share_pct")
    finra_average = _number(facts, "finra_average_20_pct")
    keys = [
        key
        for key in (
            "13f_net_breadth_pct",
            "13f_net_change_pct",
            "13f_manager_count",
            "13f_report_date",
            "finra_short_marked_share_pct",
            "finra_average_20_pct",
        )
        if facts.get(key) is not None
    ]
    if breadth is not None and breadth >= 20 and (net_change is None or net_change >= 0):
        claims.append(
            ClaimDraft(
                key="reported_13f_breadth_support",
                side="supporting",
                statement=(
                    f"Quarter-end 13F breadth is {breadth:+.1f}%"
                    + (
                        f" across {int(managers)} reporting managers"
                        if managers is not None
                        else ""
                    )
                    + (f" for {report_date}" if report_date else "")
                    + "; filings are delayed and do not reveal current positions."
                ),
                fact_keys=tuple(
                    key
                    for key in ("13f_net_breadth_pct", "13f_manager_count", "13f_report_date")
                    if facts.get(key) is not None
                ),
                confidence=0.75,
                rule="13f_net_breadth_pct >= 20 and 13f_net_change_pct >= 0 when available",
            )
        )
        assessment = "constructive"
        summary = "Delayed quarter-end manager breadth is positive; it is not a live flow signal."
    elif (breadth is not None and breadth <= -20) or (net_change is not None and net_change <= -10):
        claims.append(
            ClaimDraft(
                key="reported_13f_reduction",
                side="counter",
                statement=(
                    "The latest delayed 13F aggregate shows net reducing behavior at quarter end; "
                    "it does not reveal current holdings or trade dates."
                ),
                fact_keys=tuple(
                    key
                    for key in ("13f_net_breadth_pct", "13f_net_change_pct", "13f_report_date")
                    if facts.get(key) is not None
                ),
                confidence=0.75,
                rule="13f_net_breadth_pct <= -20 or 13f_net_change_pct <= -10",
            )
        )
        assessment = "caution"
        summary = "Delayed quarter-end holdings show reducing behavior and require current-filing follow-up."
    elif breadth is not None or net_change is not None:
        assessment = "balanced"
        summary = "The latest delayed 13F aggregate is mixed or lacks a decisive breadth change."
    else:
        assessment = "unknown"
        summary = "No matched quarterly 13F aggregate is available at the cutoff."
    if finra is not None:
        comparison = (
            f" versus a {_fmt(finra_average)}% 20-session baseline"
            if finra_average is not None
            else " while its baseline is still forming"
        )
        summary += (
            f" FINRA short-marked volume is {_fmt(finra)}%{comparison}; this describes trade "
            "marking mechanics, not short interest or bearish conviction."
        )
    return FinancialLens(
        key="regulatory_positioning",
        label="Regulatory positioning",
        assessment=assessment,
        summary=summary,
        fact_keys=keys,
    )


def _evidence_lens(facts: dict[str, Any], official_count: int) -> FinancialLens:
    latest = _text(facts, "latest_official_evidence")
    latest_date = _text(facts, "latest_official_evidence_date")
    if latest is None:
        return FinancialLens(
            key="evidence_change",
            label="Official evidence",
            assessment="unknown",
            summary="No current official record is available in the bounded evidence pack.",
        )
    date_text = f" ({latest_date})" if latest_date else ""
    return FinancialLens(
        key="evidence_change",
        label="Official evidence",
        assessment="balanced",
        summary=f"Latest of {official_count} indexed official records: {latest}{date_text}.",
        fact_keys=["latest_official_evidence", "latest_official_evidence_date"],
    )


def _scenario_pack(
    *, market: Literal["DSE", "US"], cap_tier: str, facts: dict[str, Any]
) -> tuple[FinancialScenario, ...]:
    growth = _number(facts, "eps_growth_yoy_pct")
    resistance = _number(facts, "nearest_resistance")
    support = _number(facts, "nearest_support")
    base_conditions = []
    if growth is not None:
        base_conditions.append(f"normalized EPS growth remains near {_fmt(growth)}% YoY")
    base_conditions.append("the latest official record remains uncontradicted")
    base_conditions.append("liquidity stays inside the current policy envelope")
    upside_watch = ["A subsequent filing confirms or improves the normalized earnings trend."]
    if resistance is not None:
        upside_watch.append(
            f"Completed-session price holds above resistance near {_fmt(resistance, 2)} with broad participation."
        )
    else:
        upside_watch.append("Price structure confirms without an extreme momentum reading.")
    if market == "DSE":
        upside_watch.append(
            "The next periodic ownership disclosure confirms, rather than reverses, institutional participation."
        )
    else:
        upside_watch.append(
            "A newer 13F or beneficial-owner filing confirms rather than contradicts the disclosed positioning."
        )
    downside_watch = ["A new filing weakens earnings quality, liquidity, or the capital structure."]
    if support is not None:
        downside_watch.append(f"Completed-session price loses support near {_fmt(support, 2)}.")
    else:
        downside_watch.append("Trend and participation deteriorate together on completed sessions.")
    if cap_tier in {"micro", "penny"}:
        downside_watch.append(
            "Financing, dilution, or marketability risk increases before fundamentals improve."
        )
    return (
        FinancialScenario(
            key="base",
            title="Base case",
            state="current",
            condition="; ".join(base_conditions).capitalize() + ".",
            implication="The evidence supports continued monitoring, not a price target or automatic position.",
            watch_items=["Reconcile the next material filing against this evidence fingerprint."],
        ),
        FinancialScenario(
            key="upside",
            title="Upside confirmation",
            state="conditional",
            condition="Fundamental evidence and market confirmation improve together.",
            implication="The thesis earns higher confidence only after the listed confirmations are observed.",
            watch_items=upside_watch,
        ),
        FinancialScenario(
            key="downside",
            title="Downside invalidation",
            state="conditional",
            condition="A material evidence or implementation condition deteriorates.",
            implication="The current thesis is downgraded or rejected; adverse price action alone is not explained as causality.",
            watch_items=downside_watch,
        ),
    )


def _evidence_requests(
    *, market: Literal["DSE", "US"], facts: dict[str, Any], official_count: int
) -> tuple[EvidenceRequest, ...]:
    requests: list[EvidenceRequest] = []
    if _number(facts, "roe_pct") is None and _number(facts, "eps_growth_yoy_pct") is None:
        requests.append(
            EvidenceRequest(
                priority="high",
                question="What is the latest normalized profitability and earnings direction?",
                reason="A thesis should not infer business quality from price behavior alone.",
            )
        )
    if official_count == 0:
        requests.append(
            EvidenceRequest(
                priority="high",
                question="What is the latest material issuer or exchange filing?",
                reason="No current official record anchors the research cutoff.",
            )
        )
    if _number(facts, "average_daily_value_mn") is None:
        requests.append(
            EvidenceRequest(
                priority="high",
                question="What executable size can the completed-session liquidity support?",
                reason="Capacity and exit risk cannot be bounded without average traded value.",
            )
        )
    if market == "DSE" and _number(facts, "institutional_ownership_pct") is None:
        requests.append(
            EvidenceRequest(
                priority="medium",
                question="What changed in the latest periodic ownership composition?",
                reason="DSE ownership claims require issuer-reported snapshots and comparison dates.",
            )
        )
    if market == "US" and _number(facts, "13f_manager_count") is None:
        requests.append(
            EvidenceRequest(
                priority="medium",
                question="Is there a matched current and prior 13F ownership aggregate?",
                reason="Institutional positioning cannot be inferred from price or FINRA daily short volume.",
            )
        )
    if market == "US" and _number(facts, "finra_short_marked_share_pct") is None:
        requests.append(
            EvidenceRequest(
                priority="routine",
                question="Has the latest FINRA short-volume file been matched to this ticker?",
                reason="The data is contextual market-mechanics evidence, not a thesis gate.",
            )
        )
    if not requests:
        requests.append(
            EvidenceRequest(
                priority="routine",
                question="What changed in the next material filing relative to this evidence fingerprint?",
                reason="The next review should focus on a measurable evidence differential, not regenerate static prose.",
            )
        )
    return tuple(requests)


def build_financial_reasoning(
    *,
    market: Literal["DSE", "US"],
    cap_tier: str,
    facts: dict[str, Any],
    flags: list[str],
    official_evidence_count: int,
) -> FinancialReasoningPack:
    """Build a finance-specific reasoning pack from an already validated fact ledger."""

    claims: list[ClaimDraft] = []
    lenses = [
        _fundamental_lens(facts, claims),
        _valuation_lens(facts, claims),
        _market_structure_lens(facts, claims),
        _liquidity_lens(
            market=market,
            cap_tier=cap_tier,
            facts=facts,
            flags=set(flags),
            claims=claims,
        ),
        (
            _dse_ownership_lens(facts, claims)
            if market == "DSE"
            else _us_positioning_lens(facts, claims)
        ),
        _evidence_lens(facts, official_evidence_count),
    ]
    invalidation = [
        "Reject or downgrade the thesis when a newer official filing contradicts a supporting claim.",
        "Reject implementation when liquidity falls below policy or the risk burden reaches 85/100.",
    ]
    support = _number(facts, "nearest_support")
    if support is not None:
        invalidation.append(
            f"Reassess market confirmation after a completed-session break below support near {_fmt(support, 2)}."
        )
    if market == "DSE" and _number(facts, "institutional_ownership_change_pp") not in (None, 0):
        invalidation.append(
            "Reassess the ownership interpretation when the next periodic disclosure reverses the reported change."
        )
    if market == "US" and _number(facts, "13f_manager_count") is not None:
        invalidation.append(
            "Reassess institutional positioning when a newer quarter or beneficial-owner filing contradicts the delayed 13F aggregate."
        )
    return FinancialReasoningPack(
        claim_drafts=tuple(claims),
        lenses=tuple(lenses),
        scenarios=_scenario_pack(market=market, cap_tier=cap_tier, facts=facts),
        evidence_requests=_evidence_requests(
            market=market,
            facts=facts,
            official_count=official_evidence_count,
        ),
        invalidation_rules=tuple(invalidation),
    )
