"""Compile and persist Atlas condition evidence from completed adjusted bars.

This module is deliberately outside the strategy lifecycle. It records descriptive condition
changes, diagnostic follow-through, and explicit per-user observation alerts. It never creates a
target, position, order, recommendation, or probability estimate.
"""

from __future__ import annotations

import datetime as dt
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from typing import Any

from sqlalchemy import and_, case, select, tuple_
from sqlalchemy.dialects.postgresql import insert as pg_insert

from bulls.analytics import (
    METHODOLOGY_VERSION,
    ConditionOutcome,
    build_condition_outcomes,
    build_condition_timelines,
    calibrate_condition_outcomes,
)
from bulls.core.db import bind_tenant_context
from bulls.core.models import (
    AlertEvent,
    ResearchConditionCalibration,
    ResearchConditionSubscription,
    ResearchConditionTransition,
)

EvidenceMode = str
ConditionIdentity = tuple[str, str, dt.date]
_WRITE_BATCH_SIZE = 200
_CALIBRATION_WARNING = (
    "Rolling 300-session diagnostic reconstructed from the current active universe. It has "
    "survivorship and overlapping-episode bias, excludes costs and executable entry/exit rules, "
    "and must not be represented as strategy performance."
)


@dataclass(frozen=True, slots=True)
class ExistingConditionEvidence:
    evidence_mode: EvidenceMode
    outcomes: dict[str, Any]


@dataclass(frozen=True, slots=True)
class CompiledConditionEvidence:
    rows: tuple[dict[str, Any], ...]
    outcomes: tuple[tuple[EvidenceMode, ConditionOutcome], ...]
    forward_observations: tuple[dict[str, Any], ...]
    history_start_date: dt.date | None


class CalibrationCollector:
    """Bounded in-memory collector for one market analytics run."""

    def __init__(self) -> None:
        self._groups: dict[tuple[str, str, EvidenceMode, int], list[ConditionOutcome]] = (
            defaultdict(list)
        )
        self._history_start_date: dt.date | None = None
        self._symbols = 0

    def add(self, compiled: CompiledConditionEvidence) -> None:
        self._symbols += 1
        if compiled.history_start_date is not None:
            self._history_start_date = min(
                self._history_start_date or compiled.history_start_date,
                compiled.history_start_date,
            )
        for evidence_mode, outcome in compiled.outcomes:
            self._groups[
                (
                    outcome.condition_key,
                    outcome.condition_version,
                    evidence_mode,
                    outcome.horizon_sessions,
                )
            ].append(outcome)

    def rows(self, market: str, as_of_date: dt.date) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for (condition_key, condition_version, evidence_mode, horizon), outcomes in sorted(
            self._groups.items()
        ):
            calibration = calibrate_condition_outcomes(outcomes)[0]
            rows.append(
                {
                    "market": market,
                    "condition_key": condition_key,
                    "condition_version": condition_version,
                    "methodology_version": METHODOLOGY_VERSION,
                    "evidence_mode": evidence_mode,
                    "horizon_sessions": horizon,
                    "as_of_date": as_of_date,
                    "history_start_date": self._history_start_date,
                    "observations": calibration.observations,
                    "matured": calibration.matured,
                    "pending": calibration.pending,
                    "average_return_pct": calibration.average_return_pct,
                    "median_return_pct": calibration.median_return_pct,
                    "positive_rate_pct": calibration.positive_rate_pct,
                    "average_benchmark_return_pct": (calibration.average_benchmark_return_pct),
                    "median_excess_return_pct": calibration.median_excess_return_pct,
                    "benchmark_observations": calibration.benchmark_observations,
                    "average_max_favorable_pct": calibration.average_max_favorable_pct,
                    "average_max_adverse_pct": calibration.average_max_adverse_pct,
                    "universe_size": self._symbols,
                    "point_in_time_complete": False,
                    "warning_text": _CALIBRATION_WARNING,
                    "computed_at": dt.datetime.now(dt.UTC),
                }
            )
        return rows


def _serialize_outcome(outcome: ConditionOutcome) -> dict[str, Any]:
    payload = asdict(outcome)
    payload.pop("condition_key")
    payload.pop("condition_version")
    payload.pop("observed_date")
    payload.pop("reference_close")
    payload.pop("horizon_sessions")
    if payload["outcome_date"] is not None:
        payload["outcome_date"] = payload["outcome_date"].isoformat()
    return payload


def _serialize_checks(checks: Sequence) -> list[dict[str, Any]]:
    return [asdict(check) for check in checks]


def compile_condition_evidence(
    *,
    market: str,
    code: str,
    bars: Sequence,
    benchmark_closes: Mapping[dt.date, float] | None = None,
    forward_date: dt.date | None = None,
    existing: Mapping[ConditionIdentity, ExistingConditionEvidence] | None = None,
) -> CompiledConditionEvidence:
    """Compile state changes and later-bar outcomes for one symbol.

    Existing evidence modes always win. This preserves an earlier genuinely forward observation
    when a later rolling-window rebuild sees the same date as historical data.
    """

    existing = existing or {}
    timelines = build_condition_timelines(bars)
    outcomes = build_condition_outcomes(bars, benchmark_closes=benchmark_closes)
    outcomes_by_observation: dict[ConditionIdentity, list[ConditionOutcome]] = defaultdict(list)
    for outcome in outcomes:
        outcomes_by_observation[
            (outcome.condition_key, outcome.condition_version, outcome.observed_date)
        ].append(outcome)

    rows: list[dict[str, Any]] = []
    tagged_outcomes: list[tuple[EvidenceMode, ConditionOutcome]] = []
    forward_observations: list[dict[str, Any]] = []
    for timeline in timelines:
        for change in timeline.state_changes:
            identity = (timeline.key, timeline.version, change.date)
            previous = existing.get(identity)
            evidence_mode = (
                "forward"
                if (previous is not None and previous.evidence_mode == "forward")
                or forward_date == change.date
                else "reconstructed"
            )
            observation_outcomes = outcomes_by_observation.get(identity, [])
            outcome_payload = {
                str(outcome.horizon_sessions): _serialize_outcome(outcome)
                for outcome in observation_outcomes
            }
            row = {
                "market": market,
                "code": code,
                "condition_key": timeline.key,
                "condition_version": timeline.version,
                "methodology_version": METHODOLOGY_VERSION,
                "as_of_date": change.date,
                "state": change.state,
                "previous_state": change.previous_state,
                "reference_close": change.close,
                "checks": _serialize_checks(change.checks),
                "outcomes": outcome_payload,
                "evidence_mode": evidence_mode,
                "updated_at": dt.datetime.now(dt.UTC),
            }
            if (
                previous is None
                or previous.outcomes != outcome_payload
                or previous.evidence_mode != evidence_mode
            ):
                rows.append(row)
            for outcome in observation_outcomes:
                tagged_outcomes.append((evidence_mode, outcome))
            if (
                evidence_mode == "forward"
                and forward_date == change.date
                and change.state == "observed"
                and change.previous_state != "observed"
            ):
                forward_observations.append(row)

    return CompiledConditionEvidence(
        rows=tuple(rows),
        outcomes=tuple(tagged_outcomes),
        forward_observations=tuple(forward_observations),
        history_start_date=bars[0].date if bars else None,
    )


async def load_existing_condition_evidence(
    session,
    *,
    market: str,
    codes: Sequence[str],
) -> dict[str, dict[ConditionIdentity, ExistingConditionEvidence]]:
    if not codes:
        return {}
    rows = (
        await session.execute(
            select(
                ResearchConditionTransition.code,
                ResearchConditionTransition.condition_key,
                ResearchConditionTransition.condition_version,
                ResearchConditionTransition.as_of_date,
                ResearchConditionTransition.evidence_mode,
                ResearchConditionTransition.outcomes,
            ).where(
                ResearchConditionTransition.market == market,
                ResearchConditionTransition.code.in_(codes),
                ResearchConditionTransition.methodology_version == METHODOLOGY_VERSION,
            )
        )
    ).all()
    grouped: dict[str, dict[ConditionIdentity, ExistingConditionEvidence]] = defaultdict(dict)
    for code, condition_key, condition_version, as_of_date, evidence_mode, outcomes in rows:
        grouped[code][(condition_key, condition_version, as_of_date)] = ExistingConditionEvidence(
            evidence_mode=evidence_mode,
            outcomes=outcomes or {},
        )
    return dict(grouped)


def _chunks(rows: Sequence[dict[str, Any]]) -> Iterable[Sequence[dict[str, Any]]]:
    for start in range(0, len(rows), _WRITE_BATCH_SIZE):
        yield rows[start : start + _WRITE_BATCH_SIZE]


async def persist_condition_transitions(session, rows: Sequence[dict[str, Any]]) -> int:
    written = 0
    for chunk in _chunks(rows):
        stmt = pg_insert(ResearchConditionTransition).values(list(chunk))
        promote_to_forward = and_(
            ResearchConditionTransition.evidence_mode == "reconstructed",
            stmt.excluded.evidence_mode == "forward",
        )
        result = await session.execute(
            stmt.on_conflict_do_update(
                index_elements=[
                    "market",
                    "code",
                    "condition_key",
                    "condition_version",
                    "methodology_version",
                    "as_of_date",
                ],
                set_={
                    "state": case(
                        (promote_to_forward, stmt.excluded.state),
                        else_=ResearchConditionTransition.state,
                    ),
                    "previous_state": case(
                        (promote_to_forward, stmt.excluded.previous_state),
                        else_=ResearchConditionTransition.previous_state,
                    ),
                    "reference_close": case(
                        (promote_to_forward, stmt.excluded.reference_close),
                        else_=ResearchConditionTransition.reference_close,
                    ),
                    "checks": case(
                        (promote_to_forward, stmt.excluded.checks),
                        else_=ResearchConditionTransition.checks,
                    ),
                    "outcomes": stmt.excluded.outcomes,
                    "evidence_mode": case(
                        (promote_to_forward, "forward"),
                        else_=ResearchConditionTransition.evidence_mode,
                    ),
                    "updated_at": stmt.excluded.updated_at,
                },
            )
        )
        written += max(0, int(result.rowcount or 0))
    return written


async def persist_condition_calibrations(session, rows: Sequence[dict[str, Any]]) -> int:
    written = 0
    for chunk in _chunks(rows):
        stmt = pg_insert(ResearchConditionCalibration).values(list(chunk))
        excluded_keys = {
            "market",
            "condition_key",
            "condition_version",
            "methodology_version",
            "evidence_mode",
            "horizon_sessions",
        }
        result = await session.execute(
            stmt.on_conflict_do_update(
                index_elements=list(excluded_keys),
                set_={
                    key: getattr(stmt.excluded, key) for key in chunk[0] if key not in excluded_keys
                },
            )
        )
        written += max(0, int(result.rowcount or 0))
    return written


_CONDITION_TITLES = {
    "trend_alignment": {
        "en": "${code} trend alignment became observed",
        "bn": "${code}-এ ট্রেন্ড অ্যালাইনমেন্ট দেখা গেছে",
    },
    "participation_expansion": {
        "en": "${code} participation expansion became observed",
        "bn": "${code}-এ ভলিউম অংশগ্রহণ বৃদ্ধি দেখা গেছে",
    },
    "controlled_pullback_context": {
        "en": "${code} controlled pullback context became observed",
        "bn": "${code}-এ নিয়ন্ত্রিত পুলব্যাক কনটেক্সট দেখা গেছে",
    },
}


def condition_alert_text(
    market: str, code: str, condition_key: str, as_of_date: dt.date
) -> tuple[dict[str, str], dict[str, str]]:
    template = _CONDITION_TITLES[condition_key]
    title = {"en": template["en"].replace("{code}", code)}
    body = {
        "en": (
            f"The completed {as_of_date} session changed this research condition to observed. "
            "Review the actual checks, counter-evidence, and limitations in Atlas. This is not "
            "a trade signal or order."
        )
    }
    if market == "DSE":
        title["bn"] = template["bn"].replace("{code}", code)
        body["bn"] = (
            f"{as_of_date} সমাপ্ত সেশনে এই গবেষণা শর্তটি পর্যবেক্ষিত হয়েছে। Atlas-এ প্রকৃত "
            "চেক, বিপরীত প্রমাণ ও সীমাবদ্ধতা দেখুন। এটি ট্রেড সিগন্যাল বা অর্ডার নয়।"
        )
    return title, body


async def dispatch_condition_alerts(
    session,
    *,
    tenant_id: str,
    market: str,
    observations: Sequence[dict[str, Any]],
) -> int:
    """Notify only explicitly subscribed users; source keys make retries harmless."""

    if not observations:
        return 0
    await bind_tenant_context(session, tenant_id)
    identities = {
        (row["code"], row["condition_key"], row["condition_version"]) for row in observations
    }
    subscriptions = list(
        await session.scalars(
            select(ResearchConditionSubscription).where(
                ResearchConditionSubscription.tenant_id == tenant_id,
                ResearchConditionSubscription.market == market,
                ResearchConditionSubscription.methodology_version == METHODOLOGY_VERSION,
                ResearchConditionSubscription.enabled.is_(True),
                tuple_(
                    ResearchConditionSubscription.code,
                    ResearchConditionSubscription.condition_key,
                    ResearchConditionSubscription.condition_version,
                ).in_(identities),
            )
        )
    )
    observations_by_identity = {
        (row["code"], row["condition_key"], row["condition_version"]): row for row in observations
    }
    alert_rows: list[dict[str, Any]] = []
    for subscription in subscriptions:
        row = observations_by_identity[
            (subscription.code, subscription.condition_key, subscription.condition_version)
        ]
        title, body = condition_alert_text(
            market, subscription.code, subscription.condition_key, row["as_of_date"]
        )
        alert_rows.append(
            {
                "tenant_id": tenant_id,
                "user_id": subscription.user_id,
                "market": market,
                "code": subscription.code,
                "kind": "research_condition",
                "title_i18n": title,
                "body_i18n": body,
                "source_key": (
                    f"atlas-condition:{market}:{subscription.code}:"
                    f"{subscription.condition_key}:{subscription.condition_version}:"
                    f"{row['as_of_date'].isoformat()}"
                ),
            }
        )
        subscription.last_alerted_on = row["as_of_date"]

    written = 0
    for chunk in _chunks(alert_rows):
        stmt = pg_insert(AlertEvent).values(list(chunk))
        result = await session.execute(
            stmt.on_conflict_do_nothing(
                index_elements=["tenant_id", "user_id", "source_key"],
                index_where=AlertEvent.source_key.isnot(None),
            )
        )
        written += max(0, int(result.rowcount or 0))
    return written
