"""Daily Shortlist — the always-full daily research slate.

Replaces an empty screen with five names a researcher can actually start on. Scheme-3's four
boolean gates align on only 21.6% of DSE sessions, so the `quality_reversal_eod` board is blank
78% of the time; this ranks the eligible universe instead of demanding every gate pass, and is
therefore never empty when the market traded.

Descriptive only, and the response is built so it cannot be misread as a tip sheet:
``is_return_claim`` is always false, and the measured base rates travel with every payload — over
232 tested DSE sessions a return-seeking rank did 1.24pp *worse* than a random draw from the same
pool. See ``docs/research/dse-daily-slate-study-2026-07-25.md``.

Freshness is explicit per the platform rule: the slate carries the analytics session date, the
quote timestamp and ``is_delayed``, so the UI can never present a stale slate as live.

Past slates are served from the ``daily_shortlist_states`` archive so "what did you show me on
Tuesday" is answerable and outcomes can be measured; the live ranking is the fallback for a
market whose archive has not been scanned yet. Outcome figures are measured from the close the
row was RANKED on to the latest completed close, with the peak taken strictly after the ranking
session — so a slate can never take credit for the move that got it noticed.
"""

from __future__ import annotations

import datetime as dt
from collections import defaultdict
from dataclasses import dataclass

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, select

from api.deps import CurrentTenant, DbSession, enforce_market_feature
from bulls.analytics.daily_shortlist import (
    BASE_RATES,
    METHODOLOGY_VERSION,
    ShortlistCandidate,
    ShortlistFact,
    build_daily_shortlist,
    render_fact_en,
)
from bulls.core.models import (
    CompanyProfile,
    DailyBar,
    DailyShortlistState,
    Symbol,
    TickerAnalytics,
)

router = APIRouter(tags=["shortlist"])

MAX_SIZE = 10
OUTCOME_HORIZONS = (1, 3, 5, 10)


class ShortlistFactOut(BaseModel):
    """A localisable statement: the client renders ``kind`` in the reader's language."""

    kind: str
    value: float | None = None


class ShortlistHorizonOutcome(BaseModel):
    """Close-to-close result after a fixed number of later observed sessions."""

    sessions: int
    close_return_pct: float | None = None
    as_of: dt.date | None = None


class ShortlistRow(BaseModel):
    code: str
    # Both names are returned and the client picks, matching /browse — no server-side locale
    # branching, so a Bangla and an English reader get the same payload.
    name_en: str | None = None
    name_bn: str | None = None
    rank: int
    attention_score: float
    close: float
    change_pct: float | None = None
    sector: str | None = None
    pe: float | None = None
    # Structured for localisation; reasons/unknowns are the English renderings of the same facts,
    # kept so an English tenant and non-UI consumers do not have to re-implement the wording.
    facts: list[ShortlistFactOut]
    cautions: list[ShortlistFactOut]
    reasons: list[str]
    unknowns: list[str]
    # Outcome since the row was ranked. None on the newest slate — nothing has happened yet.
    return_since_pct: float | None = None
    # Highest the price traded AFTER the ranking session. An excursion, not a captured return.
    max_went_pct: float | None = None
    # Lowest the price traded AFTER the ranking session. Also an excursion, not realised P&L.
    min_went_pct: float | None = None
    latest_close: float | None = None
    sessions_since: int = 0
    outcome_as_of: dt.date | None = None
    horizon_returns: list[ShortlistHorizonOutcome] = Field(default_factory=list)
    # A shortlist row is an appearance, not a unique discovery. These fields make repeats explicit.
    appearance_number: int | None = None
    first_recorded_appearance_date: dt.date | None = None


class ShortlistResponse(BaseModel):
    market: str
    as_of: dt.date
    # Archived sessions the reader can step through, newest first. Empty until the scan runs.
    available_dates: list[dt.date] = Field(default_factory=list)
    latest_date: dt.date | None = None
    # "forward" = recorded on the session itself; "reconstructed" = replayed from stored bars;
    # "live" = computed now because no archive row exists for this market yet.
    evidence_mode: str = "live"
    quote_as_of: dt.datetime | None = None
    is_delayed: bool = True
    size: int
    rows: list[ShortlistRow]
    eligible_names: int
    excluded_illiquid: int
    excluded_short_history: int
    # Always false. The slate ranks attention, never expected return.
    is_return_claim: bool = False
    methodology_version: str = METHODOLOGY_VERSION
    base_rates: dict = Field(default_factory=lambda: dict(BASE_RATES))
    notes: list[str]
    source: str = "bulls_daily_shortlist_eod"


def _range_position_pct(row: TickerAnalytics) -> float | None:
    """Where the close sits in the 52-week range, 0 = at the low, 100 = at the high."""
    if row.week52_high is None or row.week52_low is None:
        return None
    span = row.week52_high - row.week52_low
    if span <= 0:
        return None
    return (row.last_close - row.week52_low) / span * 100.0


def _fact_outputs(values: list | None) -> tuple[list[ShortlistFactOut], list[str]]:
    """Validate archived JSON and produce the English fallback from the same structured facts."""
    outputs: list[ShortlistFactOut] = []
    rendered: list[str] = []
    for value in values or []:
        fact = ShortlistFactOut.model_validate(value)
        outputs.append(fact)
        rendered.append(render_fact_en(ShortlistFact(kind=fact.kind, value=fact.value)))
    return outputs, rendered


@dataclass(frozen=True)
class _MeasuredOutcome:
    return_since_pct: float | None
    max_went_pct: float | None
    min_went_pct: float | None
    latest_close: float | None
    sessions_since: int
    outcome_as_of: dt.date | None
    horizon_returns: list[ShortlistHorizonOutcome]


def _measure_outcome(reference_close: float, bars: list[DailyBar]) -> _MeasuredOutcome:
    """Measure later observed closes only; never count the attention session as performance."""
    pending_horizons = [
        ShortlistHorizonOutcome(sessions=horizon) for horizon in OUTCOME_HORIZONS
    ]
    if reference_close <= 0 or not bars:
        return _MeasuredOutcome(
            return_since_pct=None,
            max_went_pct=None,
            min_went_pct=None,
            latest_close=None,
            sessions_since=0,
            outcome_as_of=None,
            horizon_returns=pending_horizons,
        )

    ordered = sorted(bars, key=lambda bar: bar.date)
    latest = ordered[-1]
    return_since = (latest.close / reference_close - 1.0) * 100.0
    highest = max(bar.high for bar in ordered)
    lowest = min(bar.low for bar in ordered)
    max_went = (highest / reference_close - 1.0) * 100.0
    min_went = (lowest / reference_close - 1.0) * 100.0
    horizons = [
        ShortlistHorizonOutcome(
            sessions=horizon,
            close_return_pct=(
                (ordered[horizon - 1].close / reference_close - 1.0) * 100.0
                if len(ordered) >= horizon
                else None
            ),
            as_of=ordered[horizon - 1].date if len(ordered) >= horizon else None,
        )
        for horizon in OUTCOME_HORIZONS
    ]
    return _MeasuredOutcome(
        return_since_pct=return_since,
        max_went_pct=max_went,
        min_went_pct=min_went,
        latest_close=latest.close,
        sessions_since=len(ordered),
        outcome_as_of=latest.date,
        horizon_returns=horizons,
    )


def _outcome(
    reference_close: float, bars: list[DailyBar]
) -> tuple[float | None, float | None, int, dt.date | None]:
    """Backward-compatible compact outcome used by existing API consumers and tests."""
    measured = _measure_outcome(reference_close, bars)
    return (
        measured.return_since_pct,
        measured.max_went_pct,
        measured.sessions_since,
        measured.outcome_as_of,
    )


def _select_archive_date(
    available_dates: list[dt.date], requested_date: dt.date | None
) -> dt.date | None:
    """Resolve to the newest archived session not later than the requested calendar date."""
    return next(
        (
            value
            for value in available_dates
            if requested_date is None or value <= requested_date
        ),
        None,
    )


async def _archived_response(
    session: DbSession,
    *,
    market: str,
    requested_date: dt.date | None,
    size: int,
) -> ShortlistResponse | None:
    available_dates = list(
        await session.scalars(
            select(DailyShortlistState.as_of_date)
            .where(DailyShortlistState.market == market)
            .distinct()
            .order_by(DailyShortlistState.as_of_date.desc())
            .limit(260)
        )
    )
    if not available_dates:
        return None

    selected_date = _select_archive_date(available_dates, requested_date)
    if selected_date is None:
        raise HTTPException(status_code=404, detail="No archived shortlist on or before this date")
    archived = list(
        await session.scalars(
            select(DailyShortlistState)
            .where(
                DailyShortlistState.market == market,
                DailyShortlistState.as_of_date == selected_date,
            )
            .order_by(DailyShortlistState.rank)
            .limit(size)
        )
    )
    if not archived:
        raise HTTPException(status_code=404, detail="Archived shortlist is empty")

    codes = [row.code for row in archived]
    names = {
        code: (name_en, name_bn)
        for code, name_en, name_bn in (
            await session.execute(
                select(Symbol.code, Symbol.name_en, Symbol.name_bn).where(
                    Symbol.market == market,
                    Symbol.code.in_(codes),
                )
            )
        )
    }
    outcome_bars = list(
        await session.scalars(
            select(DailyBar)
            .where(
                DailyBar.market == market,
                DailyBar.code.in_(codes),
                DailyBar.date > selected_date,
            )
            .order_by(DailyBar.code, DailyBar.date)
        )
    )
    bars_by_code: dict[str, list[DailyBar]] = defaultdict(list)
    for bar in outcome_bars:
        bars_by_code[bar.code].append(bar)

    appearance_stats = {
        code: (first_date, int(appearance_count))
        for code, first_date, appearance_count in (
            await session.execute(
                select(
                    DailyShortlistState.code,
                    func.min(DailyShortlistState.as_of_date),
                    func.count(),
                )
                .where(
                    DailyShortlistState.market == market,
                    DailyShortlistState.code.in_(codes),
                    DailyShortlistState.as_of_date <= selected_date,
                )
                .group_by(DailyShortlistState.code)
            )
        )
    }

    response_rows: list[ShortlistRow] = []
    for row in archived:
        facts, reasons = _fact_outputs(row.facts)
        cautions, unknowns = _fact_outputs(row.cautions)
        outcome = _measure_outcome(row.close, bars_by_code.get(row.code, []))
        name_en, name_bn = names.get(row.code, (None, None))
        first_appearance, appearance_number = appearance_stats.get(row.code, (None, None))
        response_rows.append(
            ShortlistRow(
                code=row.code,
                name_en=name_en,
                name_bn=name_bn,
                rank=row.rank,
                attention_score=row.attention_score,
                close=row.close,
                change_pct=row.change_pct,
                sector=row.sector,
                pe=row.pe,
                facts=facts,
                cautions=cautions,
                reasons=reasons,
                unknowns=unknowns,
                return_since_pct=outcome.return_since_pct,
                max_went_pct=outcome.max_went_pct,
                min_went_pct=outcome.min_went_pct,
                latest_close=outcome.latest_close,
                sessions_since=outcome.sessions_since,
                outcome_as_of=outcome.outcome_as_of,
                horizon_returns=outcome.horizon_returns,
                appearance_number=appearance_number,
                first_recorded_appearance_date=first_appearance,
            )
        )

    first = archived[0]
    return ShortlistResponse(
        market=market,
        as_of=selected_date,
        available_dates=available_dates,
        latest_date=available_dates[0],
        evidence_mode=first.evidence_mode,
        quote_as_of=None,
        is_delayed=True,
        size=size,
        rows=response_rows,
        eligible_names=first.eligible_names,
        excluded_illiquid=first.excluded_illiquid,
        excluded_short_history=first.excluded_short_history,
        methodology_version=first.methodology_version,
        base_rates=dict(first.base_rates or BASE_RATES),
        notes=list(first.notes or []),
    )


@router.get("/shortlist/daily")
async def daily_shortlist(
    tenant: CurrentTenant,
    session: DbSession,
    size: int = Query(5, ge=1, le=MAX_SIZE),
    as_of: dt.date | None = None,
) -> ShortlistResponse:
    enforce_market_feature(tenant, "interpreted_analytics")
    market = tenant.market
    # The methodology and disclosed base rates were validated on DSE data. Reusing them for US
    # names would be a market-boundary error, not graceful generalisation.
    if market != "DSE":
        raise HTTPException(status_code=404, detail="Daily Shortlist is not validated for this market")

    archived = await _archived_response(
        session,
        market=market,
        requested_date=as_of,
        size=size,
    )
    if archived is not None:
        return archived
    if as_of is not None:
        raise HTTPException(status_code=404, detail="No archived shortlist is available")

    latest_date = (
        select(func.max(TickerAnalytics.as_of_date))
        .where(TickerAnalytics.market == market)
        .scalar_subquery()
    )
    # Visible, active, non-Z symbols on the freshest analytics session — the same cleanliness
    # rule the scanner boards use, so the two surfaces cannot disagree about the universe.
    stmt = (
        select(
            TickerAnalytics,
            Symbol.name_en,
            Symbol.name_bn,
            CompanyProfile.sector,
            CompanyProfile.eps,
            CompanyProfile.nav_per_share,
        )
        .join(
            Symbol,
            and_(Symbol.market == TickerAnalytics.market, Symbol.code == TickerAnalytics.code),
        )
        .join(
            CompanyProfile,
            and_(
                CompanyProfile.market == TickerAnalytics.market,
                CompanyProfile.code == TickerAnalytics.code,
            ),
            isouter=True,
        )
        .where(
            TickerAnalytics.market == market,
            TickerAnalytics.as_of_date == latest_date,
            Symbol.is_active.is_(True),
            Symbol.is_hidden.is_(False),
            Symbol.data_status == "ready",
            (Symbol.category.is_(None)) | (Symbol.category != "Z"),
            TickerAnalytics.last_close > 0,
            # Seasoning proxy: both require a long history, so their presence stands in for the
            # module's bar count, which ticker_analytics does not store.
            TickerAnalytics.sma_200.is_not(None),
            TickerAnalytics.week52_high.is_not(None),
        )
    )

    rows = (await session.execute(stmt)).all()
    names: dict[str, tuple[str | None, str | None]] = {}
    candidates: list[ShortlistCandidate] = []
    selected_date = rows[0][0].as_of_date if rows else dt.date.today()
    session_dates = list(
        await session.scalars(
            select(DailyBar.date)
            .where(DailyBar.market == market, DailyBar.date <= selected_date)
            .distinct()
            .order_by(DailyBar.date.desc())
            .limit(2)
        )
    )
    session_bars = list(
        await session.scalars(
            select(DailyBar).where(
                DailyBar.market == market,
                DailyBar.date.in_(session_dates),
            )
        )
    )
    bars_by_code: dict[str, list[DailyBar]] = defaultdict(list)
    for bar in session_bars:
        bars_by_code[bar.code].append(bar)
    for code_bars in bars_by_code.values():
        code_bars.sort(key=lambda bar: bar.date)

    for analytics, name_en, name_bn, sector, eps, nav_per_share in rows:
        code_bars = bars_by_code.get(analytics.code, [])
        if not code_bars or code_bars[-1].date != selected_date:
            continue
        today = code_bars[-1]
        previous = code_bars[-2] if len(code_bars) > 1 else None
        names[analytics.code] = (name_en, name_bn)
        candidates.append(
            ShortlistCandidate(
                code=analytics.code,
                close=today.close,
                avg_volume_20=analytics.avg_volume_20,
                # None: the SQL seasoning gate above already enforced history.
                bars_seen=None,
                change_pct=(
                    (today.close / previous.close - 1.0) * 100.0
                    if previous is not None and previous.close > 0
                    else None
                ),
                volume=today.volume,
                pct_from_52w_high=analytics.pct_from_52w_high,
                range_position_pct=_range_position_pct(analytics),
                sma_200=analytics.sma_200,
                eps=eps,
                nav_per_share=nav_per_share,
                pe=analytics.pe_ratio,
                sector=sector,
            )
        )

    slate = build_daily_shortlist(candidates, market=market, as_of=selected_date, size=size)
    return ShortlistResponse(
        market=slate.market,
        as_of=slate.as_of,
        available_dates=[],
        latest_date=slate.as_of,
        evidence_mode="live",
        quote_as_of=None,
        is_delayed=True,
        size=slate.size,
        rows=[
            ShortlistRow(
                code=entry.code,
                name_en=names.get(entry.code, (None, None))[0],
                name_bn=names.get(entry.code, (None, None))[1],
                rank=entry.rank,
                attention_score=entry.attention_score,
                close=entry.close,
                change_pct=entry.change_pct,
                sector=entry.sector,
                pe=entry.pe,
                facts=[ShortlistFactOut(kind=f.kind, value=f.value) for f in entry.facts],
                cautions=[ShortlistFactOut(kind=c.kind, value=c.value) for c in entry.cautions],
                reasons=entry.reasons,
                unknowns=entry.unknowns,
                horizon_returns=_measure_outcome(entry.close, []).horizon_returns,
            )
            for entry in slate.entries
        ],
        eligible_names=slate.eligible_names,
        excluded_illiquid=slate.excluded_illiquid,
        excluded_short_history=slate.excluded_short_history,
        is_return_claim=slate.is_return_claim,
        methodology_version=slate.methodology_version,
        base_rates=slate.base_rates,
        notes=slate.notes,
    )
