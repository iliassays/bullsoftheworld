"""Reconcile verified DSE bonus/rights events into an auditable adjusted-close series.

Version 1 deliberately excludes cash dividends, splits, mergers, and total-return reinvestment.
The adjustment boundary is the first observed DSE session after the official record date. Missing
ratio, subscription price, record date, or reference price means abstain rather than estimate.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import re
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select, update

from bulls.core.db import get_sessionmaker
from bulls.core.models import Announcement, CorporateAction, DailyBar
from ingestion.news_decode import decode

CALCULATION_VERSION = "dse-bonus-rights-record-date-v1"
_RIGHTS_TERMS_MAX_AGE = dt.timedelta(days=730)
_RIGHTS_LANGUAGE = ("right share", "rights share", "right issue", "rights issue")
_NEGATIVE_RIGHTS_LANGUAGE = (
    "not in a position to accord",
    "rejected rights",
    "rejected right",
    "declines consent",
    "cannot be reviewed",
)
_RIGHTS_DATE_TOKEN = (
    r"(?:\d{1,2}[./-](?:\d{1,2}|[A-Za-z]+)[./-]\d{4}|"
    r"[A-Za-z]+\s+\d{1,2},?\s+\d{4}|\d{1,2}\s+[A-Za-z]+\s+\d{4})"
)


@dataclass(frozen=True)
class ActionCandidate:
    code: str
    action_type: str
    record_date: dt.date
    bonus_ratio: float | None
    rights_ratio: float | None
    rights_subscription_price: float | None
    source_announcement_ids: tuple[int, ...]
    known_at: dt.datetime


def _utc(value: dt.datetime) -> dt.datetime:
    return value.replace(tzinfo=value.tzinfo or dt.UTC).astimezone(dt.UTC)


def _details(announcement: Any) -> dict[str, Any]:
    parsed = decode(
        str(announcement.category),
        str(announcement.headline),
        str(announcement.body or ""),
    )
    if _has_rights_language(announcement):
        parsed.update(
            decode(
                "corporate_action",
                str(announcement.headline),
                str(announcement.body or ""),
            )
        )
    # Re-decoding lets a parser upgrade take effect before an explicit news retag. Persisted fields
    # still win only when the new deterministic decoder did not recover them.
    return {**(announcement.details or {}), **parsed}


def _has_rights_language(announcement: Any) -> bool:
    text = f"{announcement.headline} {announcement.body or ''}".lower()
    return any(phrase in text for phrase in _RIGHTS_LANGUAGE)


def _is_negative_rights_notice(announcement: Any) -> bool:
    text = f"{announcement.headline} {announcement.body or ''}".lower()
    return any(phrase in text for phrase in _NEGATIVE_RIGHTS_LANGUAGE)


def _is_rights_entitlement_record(announcement: Any) -> bool:
    """Require the parsed date to belong to rights entitlement, not an EGM or proceeds notice."""

    text = str(announcement.body or "")
    date_after_terms = re.search(
        rf"\brecord date\b.{{0,100}}?entitlement.{{0,50}}?rights?\s+shares?"
        rf".{{0,40}}?(?::|\bis\b|\bi\.?e\.?|\bwill be\b)\s*{_RIGHTS_DATE_TOKEN}",
        text,
        re.I | re.S,
    )
    date_before_terms = re.search(
        rf"\brecord date\b.{{0,40}}?(?::|\bis\b|\bi\.?e\.?|\bwill be\b)\s*"
        rf"{_RIGHTS_DATE_TOKEN}.{{0,80}}?entitlement.{{0,50}}?rights?\s+shares?",
        text,
        re.I | re.S,
    )
    return date_after_terms is not None or date_before_terms is not None


def verified_action_candidates(
    announcements: Iterable[Any],
) -> tuple[list[ActionCandidate], dict[str, int]]:
    """Build complete official-action candidates and count every fail-closed omission."""

    rows = list(announcements)
    decoded = {int(row.id): _details(row) for row in rows}
    candidates: dict[tuple[str, str, dt.date], ActionCandidate] = {}
    bonus_by_distribution: dict[tuple[str, str], tuple[ActionCandidate, Any]] = {}
    incomplete_bonus = incomplete_rights = superseded_bonus = 0

    for row in rows:
        details = decoded[int(row.id)]
        stock_pct = details.get("stock_pct")
        record_value = details.get("record_date")
        if stock_pct is None:
            continue
        if not record_value:
            incomplete_bonus += 1
            continue
        try:
            record_date = dt.date.fromisoformat(str(record_value))
            ratio = float(stock_pct) / 100.0
        except (TypeError, ValueError):
            incomplete_bonus += 1
            continue
        if ratio <= 0:
            incomplete_bonus += 1
            continue
        candidate = ActionCandidate(
            code=str(row.code).upper(),
            action_type="bonus",
            record_date=record_date,
            bonus_ratio=ratio,
            rights_ratio=None,
            rights_subscription_price=None,
            source_announcement_ids=(int(row.id),),
            known_at=_utc(row.created_at),
        )
        distribution_key = str(details.get("year_ended") or f"record:{record_date.isoformat()}")
        key = (candidate.code, distribution_key)
        previous = bonus_by_distribution.get(key)
        if previous is None or (
            row.published_at,
            candidate.known_at,
            int(row.id),
        ) >= (
            previous[1].published_at,
            previous[0].known_at,
            int(previous[1].id),
        ):
            if previous is not None and previous[0].record_date != candidate.record_date:
                superseded_bonus += 1
            bonus_by_distribution[key] = (candidate, row)

    for candidate, _ in bonus_by_distribution.values():
        candidates[(candidate.code, candidate.action_type, candidate.record_date)] = candidate

    rights_terms: dict[str, list[tuple[Any, dict[str, Any]]]] = {}
    rights_records: list[tuple[Any, dt.date]] = []
    for row in rows:
        if not _has_rights_language(row) or _is_negative_rights_notice(row):
            continue
        details = decoded[int(row.id)]
        if (
            details.get("rights_ratio") is not None
            and details.get("rights_subscription_price") is not None
        ):
            rights_terms.setdefault(str(row.code).upper(), []).append((row, details))
        if details.get("record_date") and _is_rights_entitlement_record(row):
            try:
                rights_records.append((row, dt.date.fromisoformat(str(details["record_date"]))))
            except ValueError:
                incomplete_rights += 1

    for record_row, record_date in rights_records:
        code = str(record_row.code).upper()
        eligible_terms = [
            item
            for item in rights_terms.get(code, [])
            if item[0].published_at <= record_row.published_at
            and record_row.published_at - item[0].published_at <= _RIGHTS_TERMS_MAX_AGE
        ]
        if not eligible_terms:
            incomplete_rights += 1
            continue
        terms_row, details = max(
            eligible_terms,
            key=lambda item: (item[0].published_at, _utc(item[0].created_at), int(item[0].id)),
        )
        try:
            ratio = float(details["rights_ratio"])
            price = float(details["rights_subscription_price"])
        except (TypeError, ValueError):
            incomplete_rights += 1
            continue
        if ratio <= 0 or price < 0 or record_date < record_row.published_at:
            incomplete_rights += 1
            continue
        source_ids = tuple(sorted({int(terms_row.id), int(record_row.id)}))
        candidate = ActionCandidate(
            code=code,
            action_type="rights",
            record_date=record_date,
            bonus_ratio=None,
            rights_ratio=ratio,
            rights_subscription_price=price,
            source_announcement_ids=source_ids,
            known_at=max(_utc(terms_row.created_at), _utc(record_row.created_at)),
        )
        key = (candidate.code, candidate.action_type, candidate.record_date)
        previous = candidates.get(key)
        if previous is None or candidate.known_at >= previous.known_at:
            candidates[key] = candidate

    output = sorted(
        candidates.values(),
        key=lambda item: (item.code, item.record_date, item.action_type),
    )
    return output, {
        "verified": len(output),
        "incomplete_bonus": incomplete_bonus,
        "incomplete_rights": incomplete_rights,
        "superseded_bonus": superseded_bonus,
    }


def theoretical_adjustment_factor(
    *,
    reference_close: float,
    bonus_ratio: float = 0.0,
    rights_ratio: float = 0.0,
    rights_subscription_price: float = 0.0,
) -> float:
    """Return the backward factor for a combined record-date entitlement."""

    if reference_close <= 0 or min(bonus_ratio, rights_ratio, rights_subscription_price) < 0:
        raise ValueError("corporate-action adjustment inputs must be non-negative")
    if bonus_ratio == 0 and rights_ratio == 0:
        raise ValueError("at least one bonus or rights entitlement is required")
    theoretical_ex = (reference_close + rights_ratio * rights_subscription_price) / (
        1.0 + bonus_ratio + rights_ratio
    )
    return theoretical_ex / reference_close


async def reconcile(session, *, market: str = "DSE") -> dict[str, int]:
    if market != "DSE":
        raise ValueError("bonus/right adjustment v1 is registered only for DSE")
    announcements = list(
        await session.scalars(
            select(Announcement)
            .where(Announcement.market == market)
            .order_by(Announcement.code, Announcement.published_at, Announcement.id)
        )
    )
    candidates, diagnostics = verified_action_candidates(announcements)
    existing = {
        (row.code, row.action_type, row.record_date): row
        for row in await session.scalars(
            select(CorporateAction).where(CorporateAction.market == market)
        )
    }
    for candidate in candidates:
        key = (candidate.code, candidate.action_type, candidate.record_date)
        row = existing.get(key)
        values = {
            "bonus_ratio": candidate.bonus_ratio,
            "rights_ratio": candidate.rights_ratio,
            "rights_subscription_price": candidate.rights_subscription_price,
            "source_announcement_ids": list(candidate.source_announcement_ids),
            "known_at": candidate.known_at,
            "calculation_version": CALCULATION_VERSION,
        }
        if row is None:
            row = CorporateAction(
                market=market,
                code=candidate.code,
                action_type=candidate.action_type,
                record_date=candidate.record_date,
                status="verified",
                quality_flags=[],
                **values,
            )
            session.add(row)
            existing[key] = row
        else:
            for field, value in values.items():
                setattr(row, field, value)

    # Newly ingested rows with no applicable action are still explicitly adjusted to their raw
    # close. Recompute full history only for the small set of securities with verified actions.
    await session.execute(
        update(DailyBar)
        .where(DailyBar.market == market, DailyBar.adjusted_close.is_(None))
        .values(adjusted_close=DailyBar.close)
    )
    action_codes = sorted({action.code for action in existing.values()})
    bars = (
        list(
            await session.scalars(
                select(DailyBar)
                .where(DailyBar.market == market, DailyBar.code.in_(action_codes))
                .order_by(DailyBar.code, DailyBar.date)
            )
        )
        if action_codes
        else []
    )
    bars_by_code: dict[str, list[DailyBar]] = {}
    for bar in bars:
        bars_by_code.setdefault(bar.code, []).append(bar)
        bar.adjusted_close = float(bar.close)

    actions_by_event: dict[tuple[str, dt.date], list[CorporateAction]] = {}
    for action in existing.values():
        actions_by_event.setdefault((action.code, action.record_date), []).append(action)

    applied_events: dict[str, list[tuple[dt.date, float]]] = {}
    unsafe = waiting_for_session = 0
    for (code, record_date), actions in sorted(actions_by_event.items()):
        security_bars = bars_by_code.get(code, [])
        effective_bar = next((bar for bar in security_bars if bar.date > record_date), None)
        reference_bar = next(
            (
                bar
                for bar in reversed(security_bars)
                if effective_bar and bar.date < effective_bar.date
            ),
            None,
        )
        if effective_bar is None or reference_bar is None:
            waiting_for_session += 1
            for action in actions:
                action.status = "verified"
                action.effective_session = None
                action.reference_close = None
                action.adjustment_factor = None
                action.quality_flags = [
                    {"code": "awaiting_completed_session", "record_date": record_date.isoformat()}
                ]
            continue
        bonus_ratio = sum(action.bonus_ratio or 0.0 for action in actions)
        rights_actions = [action for action in actions if action.action_type == "rights"]
        rights_ratio = sum(action.rights_ratio or 0.0 for action in rights_actions)
        rights_value = sum(
            (action.rights_ratio or 0.0) * (action.rights_subscription_price or 0.0)
            for action in rights_actions
        )
        rights_price = rights_value / rights_ratio if rights_ratio > 0 else 0.0
        factor = theoretical_adjustment_factor(
            reference_close=float(reference_bar.close),
            bonus_ratio=bonus_ratio,
            rights_ratio=rights_ratio,
            rights_subscription_price=rights_price,
        )
        # A distribution should not increase the backward price. Fail closed on economically
        # inconsistent terms instead of manufacturing an upward adjustment.
        if factor > 1.000001:
            unsafe += 1
            for action in actions:
                action.status = "verified"
                action.effective_session = None
                action.reference_close = None
                action.adjustment_factor = None
                action.quality_flags = [
                    {"code": "factor_above_one", "calculated_factor": round(factor, 8)}
                ]
            continue
        for action in actions:
            action.status = "applied"
            action.effective_session = effective_bar.date
            action.reference_close = float(reference_bar.close)
            action.adjustment_factor = factor
            action.quality_flags = [{"code": "combined_entitlement"}] if len(actions) > 1 else []
        applied_events.setdefault(code, []).append((effective_bar.date, factor))

    for code, security_bars in bars_by_code.items():
        events = sorted(applied_events.get(code, []))
        for bar in security_bars:
            cumulative_factor = 1.0
            for effective_session, factor in events:
                if bar.date < effective_session:
                    cumulative_factor *= factor
            bar.adjusted_close = round(float(bar.close) * cumulative_factor, 6)

    await session.flush()
    adjusted_rows = int(
        await session.scalar(
            select(func.count())
            .select_from(DailyBar)
            .where(DailyBar.market == market, DailyBar.adjusted_close.isnot(None))
        )
        or 0
    )
    return {
        **diagnostics,
        "applied_events": sum(len(items) for items in applied_events.values()),
        "waiting_for_session": waiting_for_session,
        "unsafe": unsafe,
        "daily_rows_populated": adjusted_rows,
    }


async def run(market: str = "DSE") -> dict[str, int]:
    async with get_sessionmaker()() as session:
        result = await reconcile(session, market=market)
        await session.commit()
        return result


def main() -> None:
    market = sys.argv[1].upper() if len(sys.argv) > 1 else "DSE"
    print(f"[corporate-actions] reconciling {market} bonus/right adjustments")
    print(f"[corporate-actions] done: {asyncio.run(run(market))}")


if __name__ == "__main__":
    main()
