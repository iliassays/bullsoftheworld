"""Daily shortlist archive writer — the only writer of ``daily_shortlist_states``.

Two modes, mirroring the squeeze archive's contract:

``forward`` (default)
    Ranks the current ``ticker_analytics`` session and records what a reader saw today.

``--backfill N``
    Reconstructs the last N sessions from stored daily bars. Defensible here in a way replay
    usually is not: every ranking axis (move, relative volume, level proximity, range extremity)
    is computed from the bars of that session and the ones before it, so the *ranking* carries no
    look-ahead. Two limits are recorded on every reconstructed row and shown in the UI — only
    currently-listed symbols exist in the store, so a since-delisted name can never appear; and
    P/E uses the latest reported annual EPS rather than the figure published at the time. P/E is
    display only and never enters the score.

Forward snapshots are immutable: a retry cannot rewrite what readers actually saw. Reconstructed
snapshots are idempotent and may be regenerated until a real forward run replaces that date.

    uv run python -m ingestion.daily_shortlist_scan DSE
    uv run python -m ingestion.daily_shortlist_scan DSE --backfill 120
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import logging
from bisect import bisect_right
from collections.abc import Collection
from dataclasses import asdict

from sqlalchemy import and_, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from bulls.analytics.daily_shortlist import (
    DEFAULT_SIZE,
    METHODOLOGY_VERSION,
    MIN_BARS,
    ShortlistCandidate,
    build_daily_shortlist,
)
from bulls.core.db import get_sessionmaker
from bulls.core.models import (
    CompanyProfile,
    DailyBar,
    DailyShortlistState,
    Symbol,
    TickerAnalytics,
)

log = logging.getLogger(__name__)

# Bars needed behind a session to compute its 52-week window and 200-day average.
_LOOKBACK_BARS = 260
_SUPPORTED_MARKETS = {"DSE"}


def _validated_market(market: str) -> str:
    normalized = market.strip().upper()
    if normalized not in _SUPPORTED_MARKETS:
        raise ValueError(
            f"Daily Shortlist is validated only for {sorted(_SUPPORTED_MARKETS)}; got {market!r}"
        )
    return normalized


def _range_position_pct(close: float, high: float | None, low: float | None) -> float | None:
    if high is None or low is None:
        return None
    span = high - low
    return None if span <= 0 else (close - low) / span * 100.0


async def _clean_codes(session, market: str) -> set[str]:
    """Visible, active, non-Z symbols — the same universe the scanner boards use."""
    rows = await session.scalars(
        select(Symbol.code).where(
            Symbol.market == market,
            Symbol.is_active.is_(True),
            Symbol.is_hidden.is_(False),
            Symbol.data_status == "ready",
            (Symbol.category.is_(None)) | (Symbol.category != "Z"),
        )
    )
    return set(rows)


async def _profiles(
    session, market: str
) -> dict[str, tuple[str | None, float | None, float | None]]:
    rows = await session.execute(
        select(
            CompanyProfile.code,
            CompanyProfile.sector,
            CompanyProfile.eps,
            CompanyProfile.nav_per_share,
        ).where(CompanyProfile.market == market)
    )
    return {code: (sector, eps, nav) for code, sector, eps, nav in rows}


async def _history_counts(
    session,
    market: str,
    as_of: dt.date,
    *,
    codes: Collection[str],
) -> dict[str, int]:
    """Count completed bars through ``as_of`` for the exact forward-scan universe."""

    if not codes:
        return {}
    rows = (
        await session.execute(
            select(DailyBar.code, func.count(DailyBar.date))
            .where(
                DailyBar.market == market,
                DailyBar.date <= as_of,
                DailyBar.code.in_(sorted(codes)),
            )
            .group_by(DailyBar.code)
        )
    ).all()
    return {code: int(count) for code, count in rows}


async def _persist(session, market: str, slate, *, as_of: dt.date, mode: str) -> int:
    if not slate.entries:
        return 0
    existing_modes = set(
        await session.scalars(
            select(DailyShortlistState.evidence_mode).where(
                DailyShortlistState.market == market,
                DailyShortlistState.as_of_date == as_of,
            )
        )
    )
    # A forward row records what users actually saw. Replays and later code changes must never
    # rewrite it. A real forward run may, however, replace a reconstructed placeholder.
    if "forward" in existing_modes:
        return 0
    if mode == "forward" and existing_modes:
        await session.execute(
            DailyShortlistState.__table__.delete().where(
                DailyShortlistState.market == market,
                DailyShortlistState.as_of_date == as_of,
            )
        )

    values = [
        {
            "market": market,
            "as_of_date": as_of,
            "code": entry.code,
            "rank": entry.rank,
            "attention_score": entry.attention_score,
            "close": entry.close,
            "change_pct": entry.change_pct,
            "sector": entry.sector,
            "pe": entry.pe,
            "facts": [asdict(fact) for fact in entry.facts],
            "cautions": [asdict(caution) for caution in entry.cautions],
            "eligible_names": slate.eligible_names,
            "excluded_illiquid": slate.excluded_illiquid,
            "excluded_short_history": slate.excluded_short_history,
            "slate_size": slate.size,
            "notes": slate.notes,
            "base_rates": slate.base_rates,
            "evidence_mode": mode,
            "methodology_version": slate.methodology_version,
        }
        for entry in slate.entries
    ]
    statement = pg_insert(DailyShortlistState).values(values)
    await session.execute(
        statement.on_conflict_do_update(
            index_elements=["market", "as_of_date", "code"],
            set_={
                column: getattr(statement.excluded, column)
                for column in (
                    "rank",
                    "attention_score",
                    "close",
                    "change_pct",
                    "sector",
                    "pe",
                    "facts",
                    "cautions",
                    "eligible_names",
                    "excluded_illiquid",
                    "excluded_short_history",
                    "slate_size",
                    "notes",
                    "base_rates",
                    "evidence_mode",
                    "methodology_version",
                )
            },
        )
    )
    # A slate that shrank must not leave yesterday's longer tail behind on the same date.
    await session.execute(
        DailyShortlistState.__table__.delete().where(
            and_(
                DailyShortlistState.market == market,
                DailyShortlistState.as_of_date == as_of,
                DailyShortlistState.code.notin_([entry.code for entry in slate.entries]),
            )
        )
    )
    return len(values)


async def run_forward(
    market: str,
    *,
    size: int = DEFAULT_SIZE,
    expected_as_of: dt.date | None = None,
) -> dict[str, int]:
    """Rank the freshest analytics session and archive it as what a reader saw."""
    market = _validated_market(market)
    sm = get_sessionmaker()
    async with sm() as session:
        latest = (
            select(func.max(TickerAnalytics.as_of_date))
            .where(TickerAnalytics.market == market)
            .scalar_subquery()
        )
        rows = (
            await session.execute(
                select(TickerAnalytics)
                .where(
                    TickerAnalytics.market == market,
                    TickerAnalytics.as_of_date == latest,
                    TickerAnalytics.last_close > 0,
                    TickerAnalytics.sma_200.is_not(None),
                    TickerAnalytics.week52_high.is_not(None),
                )
            )
        ).scalars().all()
        if not rows:
            log.info("daily_shortlist_scan market=%s no analytics rows", market)
            return {"archived": 0}

        as_of = rows[0].as_of_date
        if expected_as_of is not None and as_of != expected_as_of:
            log.warning(
                "daily_shortlist_scan market=%s skipped stale analytics as_of=%s expected=%s",
                market,
                as_of,
                expected_as_of,
            )
            return {"archived": 0}

        clean = await _clean_codes(session, market)
        profiles = await _profiles(session, market)
        candidate_codes = {row.code for row in rows if row.code in clean}
        history_counts = await _history_counts(
            session,
            market,
            as_of,
            codes=candidate_codes,
        )
        session_dates = list(
            await session.scalars(
                select(DailyBar.date)
                .where(DailyBar.market == market, DailyBar.date <= as_of)
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
        bars_by_code: dict[str, list[DailyBar]] = {}
        for bar in session_bars:
            bars_by_code.setdefault(bar.code, []).append(bar)
        for code_bars in bars_by_code.values():
            code_bars.sort(key=lambda bar: bar.date)

        candidates = [
            ShortlistCandidate(
                code=analytics.code,
                close=(today := bars_by_code[analytics.code][-1]).close,
                avg_volume_20=analytics.avg_volume_20,
                bars_seen=history_counts.get(analytics.code, 0),
                change_pct=(
                    (today.close / previous.close - 1) * 100
                    if len(bars_by_code[analytics.code]) > 1
                    and (previous := bars_by_code[analytics.code][-2]).close > 0
                    else None
                ),
                volume=today.volume,
                pct_from_52w_high=analytics.pct_from_52w_high,
                range_position_pct=_range_position_pct(
                    analytics.last_close, analytics.week52_high, analytics.week52_low
                ),
                sma_200=analytics.sma_200,
                eps=profiles.get(analytics.code, (None, None, None))[1],
                nav_per_share=profiles.get(analytics.code, (None, None, None))[2],
                pe=analytics.pe_ratio,
                sector=profiles.get(analytics.code, (None, None, None))[0],
            )
            for analytics in rows
            if analytics.code in clean
            and analytics.code in bars_by_code
            and bars_by_code[analytics.code][-1].date == as_of
        ]
        slate = build_daily_shortlist(candidates, market=market, as_of=as_of, size=size)
        archived = await _persist(session, market, slate, as_of=as_of, mode="forward")
        await session.commit()
    log.info("daily_shortlist_scan market=%s as_of=%s archived=%s", market, as_of, archived)
    return {"archived": archived}


async def run_backfill(market: str, sessions: int, *, size: int = DEFAULT_SIZE) -> dict[str, int]:
    """Reconstruct the last ``sessions`` slates from stored bars. See the module docstring."""
    market = _validated_market(market)
    if sessions < 1:
        raise ValueError("sessions must be at least 1")
    sm = get_sessionmaker()
    async with sm() as session:
        clean = await _clean_codes(session, market)
        profiles = await _profiles(session, market)
        bars = (
            await session.execute(
                select(DailyBar)
                .where(DailyBar.market == market)
                .order_by(DailyBar.code, DailyBar.date)
            )
        ).scalars()

        by_code: dict[str, list[DailyBar]] = {}
        for bar in bars:
            if bar.code in clean:
                by_code.setdefault(bar.code, []).append(bar)

        all_dates = sorted({bar.date for series in by_code.values() for bar in series})
        targets = all_dates[-sessions:] if sessions < len(all_dates) else all_dates
        dates_by_code = {
            code: [bar.date for bar in series]
            for code, series in by_code.items()
        }
        archived = 0

        for as_of in targets:
            candidates: list[ShortlistCandidate] = []
            for code, series in by_code.items():
                end = bisect_right(dates_by_code[code], as_of)
                window = series[max(0, end - _LOOKBACK_BARS) : end]
                if len(window) < MIN_BARS:
                    continue
                today = window[-1]
                if not today.close or today.close <= 0 or today.date != as_of:
                    continue
                year = window[-252:]
                highs = [bar.high for bar in year if bar.high is not None]
                lows = [bar.low for bar in year if bar.low is not None]
                closes = [bar.close for bar in window[-200:] if bar.close is not None]
                volumes = [bar.volume for bar in window[-20:] if bar.volume is not None]
                avg_volume = sum(volumes) / len(volumes) if volumes else None
                high_52 = max(highs) if highs else None
                low_52 = min(lows) if lows else None
                prior = window[-2].close if len(window) > 1 else None
                candidates.append(
                    ShortlistCandidate(
                        code=code,
                        close=today.close,
                        avg_volume_20=avg_volume,
                        bars_seen=end,
                        change_pct=(
                            (today.close / prior - 1) * 100 if prior and prior > 0 else None
                        ),
                        volume=today.volume,
                        pct_from_52w_high=(
                            (today.close / high_52 - 1) * 100 if high_52 else None
                        ),
                        range_position_pct=_range_position_pct(today.close, high_52, low_52),
                        sma_200=(sum(closes) / len(closes) if len(closes) >= 200 else None),
                        # Fundamentals are deliberately omitted from reconstructed rows: the
                        # figure published on that session is unknown, and showing today's P/E
                        # on a months-old slate would be a quiet look-ahead in the copy.
                        eps=None,
                        nav_per_share=None,
                        pe=None,
                        sector=profiles.get(code, (None, None, None))[0],
                    )
                )
            slate = build_daily_shortlist(candidates, market=market, as_of=as_of, size=size)
            archived += await _persist(
                session, market, slate, as_of=as_of, mode="reconstructed"
            )
        await session.commit()
    log.info(
        "daily_shortlist_backfill market=%s sessions=%s archived=%s", market, len(targets), archived
    )
    return {"archived": archived, "sessions": len(targets)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Archive the daily research shortlist")
    parser.add_argument("market", nargs="?", default="DSE", choices=sorted(_SUPPORTED_MARKETS))
    parser.add_argument("--size", type=int, default=DEFAULT_SIZE)
    parser.add_argument(
        "--backfill",
        type=int,
        default=0,
        help="reconstruct this many recent sessions from stored bars instead of scanning today",
    )
    args = parser.parse_args()
    if args.backfill:
        counts = asyncio.run(run_backfill(args.market, args.backfill, size=args.size))
        print(
            f"[shortlist] {args.market}: reconstructed {counts['sessions']} sessions, "
            f"{counts['archived']} rows ({METHODOLOGY_VERSION})"
        )
        return
    counts = asyncio.run(run_forward(args.market, size=args.size))
    print(f"[shortlist] {args.market}: archived {counts['archived']} rows ({METHODOLOGY_VERSION})")


if __name__ == "__main__":
    main()
