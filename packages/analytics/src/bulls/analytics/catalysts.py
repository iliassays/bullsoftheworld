"""Deterministic catalyst-event derivation from already-ingested official records.

Two adapters share one typed draft contract:

- DSE: decoded announcements already carry record dates, AGM/EGM dates, board-meeting dates, and
  spot-market windows. Those become `confirmed` events with official confidence.
- US: EDGAR periodic filings (10-K/10-Q) imply the next report through filing cadence. That is an
  `inferred_cadence` *window*, never a confirmed date, and the UI must present it as such.

No language model is involved; every event cites the official source record it was derived from.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import itertools
from collections.abc import Iterable, Mapping
from statistics import median
from typing import Any

from pydantic import BaseModel, ConfigDict, model_validator

US_REPORT_WINDOW_HALF_SPAN_DAYS = 12
_US_PERIODIC_FORMS = {"10-K", "10-Q", "10-K/A", "10-Q/A", "20-F", "40-F"}
_MIN_CADENCE_FILINGS = 3


class CatalystDraft(BaseModel):
    model_config = ConfigDict(frozen=True)

    market: str
    code: str
    event_type: str
    title: str
    timing_kind: str
    confirmed_date: dt.date | None = None
    window_start: dt.date | None = None
    window_end: dt.date | None = None
    confidence: str
    source_type: str
    source_ref: str
    source_url: str | None = None
    known_at: dt.datetime
    expected_evidence: str | None = None
    details: dict[str, Any] | None = None

    @model_validator(mode="after")
    def validate_timing(self) -> CatalystDraft:
        if self.timing_kind == "confirmed":
            if self.confirmed_date is None or self.window_start or self.window_end:
                raise ValueError("confirmed events carry exactly a confirmed_date")
        elif self.timing_kind == "window":
            if self.confirmed_date is not None or not (self.window_start and self.window_end):
                raise ValueError("window events carry exactly a window range")
            if self.window_start > self.window_end:
                raise ValueError("window_start must not exceed window_end")
        else:
            raise ValueError(f"unknown timing_kind {self.timing_kind!r}")
        return self

    def dedupe_key(self, tenant_id: str) -> str:
        timing = (
            self.confirmed_date.isoformat()
            if self.confirmed_date
            else f"{self.window_start}..{self.window_end}"
        )
        raw = "|".join(
            (tenant_id, self.market, self.code, self.event_type, timing, self.source_ref)
        )
        return hashlib.sha256(raw.encode()).hexdigest()


def _parse_date(value: Any) -> dt.date | None:
    if not value:
        return None
    try:
        return dt.date.fromisoformat(str(value))
    except ValueError:
        return None


def _known_at(published_at: dt.date) -> dt.datetime:
    """DSE announcements carry only a publication date; the day end is the honest upper bound."""
    return dt.datetime.combine(published_at, dt.time(23, 59), tzinfo=dt.UTC)


def dse_events_from_announcement(
    *,
    market: str,
    code: str,
    published_at: dt.date,
    category: str,
    headline: str,
    details: Mapping[str, Any] | None,
    source_ref: str,
    source_url: str | None = None,
) -> list[CatalystDraft]:
    """Project one decoded announcement onto typed confirmed events.

    Dates already in the past when the announcement was published are historical narration, not
    upcoming catalysts, and are skipped.
    """
    if not details:
        return []
    drafts: list[CatalystDraft] = []
    known_at = _known_at(published_at)

    def add(event_type: str, date: dt.date | None, title: str, expected: str) -> None:
        if date is None or date < published_at:
            return
        drafts.append(
            CatalystDraft(
                market=market,
                code=code,
                event_type=event_type,
                title=title,
                timing_kind="confirmed",
                confirmed_date=date,
                confidence="official_confirmed",
                source_type="dse_announcement",
                source_ref=source_ref,
                source_url=source_url,
                known_at=known_at,
                expected_evidence=expected,
                details={"category": category, "headline": headline[:300]},
            )
        )

    add(
        "record_date",
        _parse_date(details.get("record_date")),
        f"{code} record date",
        "Entitlement snapshot; verify shareholder position changes after the record date.",
    )
    add(
        "agm",
        _parse_date(details.get("agm_date")),
        f"{code} annual general meeting",
        "AGM outcome: dividend approval, board changes, and shareholder resolutions.",
    )
    add(
        "egm",
        _parse_date(details.get("egm_date")),
        f"{code} extraordinary general meeting",
        "EGM outcome and the specific agenda it was called for.",
    )
    add(
        "board_meeting",
        _parse_date(details.get("meeting_date")),
        f"{code} board meeting",
        "Board decisions: financial approval, dividend declaration, or corporate action.",
    )

    spot_from = _parse_date(details.get("spot_from"))
    spot_to = _parse_date(details.get("spot_to"))
    if spot_from and spot_to and spot_to >= published_at and spot_from <= spot_to:
        drafts.append(
            CatalystDraft(
                market=market,
                code=code,
                event_type="spot_window",
                title=f"{code} spot-market window",
                timing_kind="window",
                window_start=spot_from,
                window_end=spot_to,
                confidence="official_confirmed",
                source_type="dse_announcement",
                source_ref=source_ref,
                source_url=source_url,
                known_at=known_at,
                expected_evidence="Settlement moves to spot terms; expect entitlement-driven flow.",
                details={"category": category, "headline": headline[:300]},
            )
        )
    return drafts


def us_report_window_from_filings(
    *,
    market: str,
    code: str,
    periodic_filings: Iterable[tuple[str, dt.date, str]],
    as_of: dt.date,
) -> CatalystDraft | None:
    """Infer the next periodic-report window from historical filing cadence.

    `periodic_filings` is (form, filing_date, accession_number) history. The inference requires at
    least three periodic filings, uses the median gap between consecutive filings, and always emits
    a window with `inferred_cadence` confidence — never a confirmed date.
    """
    rows = sorted(
        (row for row in periodic_filings if row[0].upper() in _US_PERIODIC_FORMS),
        key=lambda row: row[1],
    )
    if len(rows) < _MIN_CADENCE_FILINGS:
        return None
    dates = [row[1] for row in rows]
    gaps = [(later - earlier).days for earlier, later in itertools.pairwise(dates)]
    positive_gaps = [gap for gap in gaps if gap > 0]
    if not positive_gaps:
        return None
    cadence_days = int(median(positive_gaps))
    if not 30 <= cadence_days <= 400:
        return None

    last_form, last_date, last_accession = rows[-1]
    center = last_date + dt.timedelta(days=cadence_days)
    while center + dt.timedelta(days=US_REPORT_WINDOW_HALF_SPAN_DAYS) < as_of:
        center += dt.timedelta(days=cadence_days)
    half_span = dt.timedelta(days=US_REPORT_WINDOW_HALF_SPAN_DAYS)
    return CatalystDraft(
        market=market,
        code=code,
        event_type="periodic_report_window",
        title=f"{code} expected periodic report",
        timing_kind="window",
        window_start=center - half_span,
        window_end=center + half_span,
        confidence="inferred_cadence",
        source_type="sec_filing_cadence",
        source_ref=last_accession,
        known_at=dt.datetime.combine(as_of, dt.time(0, 0), tzinfo=dt.UTC),
        expected_evidence=(
            "Next 10-K/10-Q: revenue and margin trajectory, liquidity, share count, and any "
            "going-concern or control language changes versus the prior period."
        ),
        details={
            "cadence_days": cadence_days,
            "observed_filings": len(rows),
            "last_form": last_form,
            "last_filing_date": last_date.isoformat(),
        },
    )
