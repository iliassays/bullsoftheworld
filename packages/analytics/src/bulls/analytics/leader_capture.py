"""Point-in-time financial evidence for the Atlas US leader-capture family."""

from __future__ import annotations

import datetime as dt
from collections import defaultdict
from collections.abc import Iterable

from pydantic import BaseModel

from bulls.analytics.research_strategy import StrategyEvidenceObservation

EVIDENCE_VERSION = "us-leader-evidence-v1"
LEADER_METRICS = frozenset({"revenue", "net_income", "operating_cash_flow"})


class LeaderFinancialFact(BaseModel):
    """Normalized filing fact with the timestamp at which Atlas could know it."""

    code: str
    metric: str
    value: float
    period_start: dt.date | None = None
    period_end: dt.date
    period_type: str
    form: str
    accession_number: str
    source_url: str
    known_at: dt.datetime
    normalization_version: str


def _utc(value: dt.datetime) -> dt.datetime:
    return value.replace(tzinfo=dt.UTC) if value.tzinfo is None else value.astimezone(dt.UTC)


def _nearest_prior(
    facts: list[LeaderFinancialFact],
    target: LeaderFinancialFact,
    *,
    minimum_days: int,
    maximum_days: int,
) -> LeaderFinancialFact | None:
    eligible = [
        fact
        for fact in facts
        if minimum_days <= (target.period_end - fact.period_end).days <= maximum_days
    ]
    if not eligible:
        return None
    desired = (minimum_days + maximum_days) / 2
    return min(
        eligible,
        key=lambda fact: (
            abs((target.period_end - fact.period_end).days - desired),
            -fact.period_end.toordinal(),
        ),
    )


def _growth(current: float, prior: float) -> float | None:
    if prior <= 0:
        return None
    return (current / prior - 1.0) * 100


def _fact_near(
    facts: list[LeaderFinancialFact],
    period_end: dt.date,
    *,
    tolerance_days: int = 7,
) -> LeaderFinancialFact | None:
    eligible = [
        fact for fact in facts if abs((fact.period_end - period_end).days) <= tolerance_days
    ]
    return max(eligible, key=lambda fact: fact.period_end, default=None)


def _financial_snapshot(
    state: dict[tuple[str, dt.date], LeaderFinancialFact],
    *,
    known_at: dt.datetime,
) -> StrategyEvidenceObservation | None:
    by_metric: dict[str, list[LeaderFinancialFact]] = defaultdict(list)
    for fact in state.values():
        by_metric[fact.metric].append(fact)
    for values in by_metric.values():
        values.sort(key=lambda fact: fact.period_end)

    revenue = by_metric["revenue"]
    if len(revenue) < 6:
        return None
    current = revenue[-1]
    previous_quarter = _nearest_prior(revenue, current, minimum_days=45, maximum_days=150)
    prior_year = _nearest_prior(revenue, current, minimum_days=300, maximum_days=430)
    if previous_quarter is None or prior_year is None:
        return None
    previous_prior_year = _nearest_prior(
        revenue,
        previous_quarter,
        minimum_days=300,
        maximum_days=430,
    )
    if previous_prior_year is None:
        return None
    revenue_growth = _growth(current.value, prior_year.value)
    previous_revenue_growth = _growth(previous_quarter.value, previous_prior_year.value)
    if revenue_growth is None or previous_revenue_growth is None:
        return None

    features: dict[str, float | bool | str | None] = {
        "revenue_growth_yoy_pct": revenue_growth,
        "revenue_acceleration_pct": revenue_growth - previous_revenue_growth,
        "reported_earnings_confirmation": False,
        "net_income_growth_yoy_pct": None,
        "net_income_acceleration_pct": None,
        "net_income_turnaround": False,
        "operating_cash_flow_positive": None,
        "latest_filing_form": current.form,
    }
    sources = {
        fact.source_url
        for fact in (current, prior_year, previous_quarter, previous_prior_year)
        if fact.source_url
    }

    net_income = by_metric["net_income"]
    income_current = _fact_near(net_income, current.period_end)
    income_prior = _fact_near(net_income, prior_year.period_end)
    income_previous = _fact_near(net_income, previous_quarter.period_end)
    income_previous_prior = _fact_near(net_income, previous_prior_year.period_end)
    if income_current is not None and income_prior is not None:
        income_growth = _growth(income_current.value, income_prior.value)
        turnaround = income_prior.value <= 0 < income_current.value
        features["net_income_growth_yoy_pct"] = income_growth
        features["net_income_turnaround"] = turnaround
        if income_previous is not None and income_previous_prior is not None:
            previous_income_growth = _growth(
                income_previous.value,
                income_previous_prior.value,
            )
            if income_growth is not None and previous_income_growth is not None:
                features["net_income_acceleration_pct"] = income_growth - previous_income_growth
        features["reported_earnings_confirmation"] = bool(
            turnaround
            or (income_growth is not None and income_growth > 0)
            or (
                isinstance(features["net_income_acceleration_pct"], float)
                and features["net_income_acceleration_pct"] > 0
            )
        )
        sources.update(
            fact.source_url
            for fact in (
                income_current,
                income_prior,
                income_previous,
                income_previous_prior,
            )
            if fact is not None and fact.source_url
        )

    cash_flow = _fact_near(by_metric["operating_cash_flow"], current.period_end)
    if cash_flow is not None:
        features["operating_cash_flow_positive"] = cash_flow.value > 0
        if cash_flow.source_url:
            sources.add(cash_flow.source_url)

    return StrategyEvidenceObservation(
        known_at=known_at,
        effective_date=current.period_end,
        features=features,
        sources=sorted(sources),
        normalization_version=EVIDENCE_VERSION,
    )


def build_leader_evidence(
    facts: Iterable[LeaderFinancialFact],
) -> dict[str, list[StrategyEvidenceObservation]]:
    """Replay filing revisions and produce only evidence observable at each knowledge time."""

    grouped: dict[str, dict[dt.datetime, list[LeaderFinancialFact]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for fact in facts:
        if fact.metric not in LEADER_METRICS or fact.period_type != "quarter":
            continue
        grouped[fact.code.upper()][_utc(fact.known_at)].append(fact)

    output: dict[str, list[StrategyEvidenceObservation]] = {}
    for code, by_known_at in grouped.items():
        state: dict[tuple[str, dt.date], LeaderFinancialFact] = {}
        observations: list[StrategyEvidenceObservation] = []
        for known_at in sorted(by_known_at):
            revisions = sorted(
                by_known_at[known_at],
                key=lambda fact: (
                    fact.metric,
                    fact.period_end,
                    fact.accession_number,
                    fact.source_url,
                ),
            )
            for fact in revisions:
                state[(fact.metric, fact.period_end)] = fact
            snapshot = _financial_snapshot(state, known_at=known_at)
            if snapshot is None:
                continue
            if observations and snapshot.features == observations[-1].features:
                continue
            observations.append(snapshot)
        output[code] = observations
    return output
