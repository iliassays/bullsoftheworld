"""Publish EOD-only U.S. quote snapshots and market aggregates from persisted daily bars."""

from __future__ import annotations

import datetime as dt
from collections import defaultdict

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from bulls.core.db import get_sessionmaker
from bulls.core.markets import get_market_profile
from bulls.core.models import DailyBar, MarketSummary, QuoteSnapshot, Symbol

MARKET = "US"
BENCHMARK_CODE = "SPY"


def _as_of(date: dt.date) -> dt.datetime:
    profile = get_market_profile(MARKET)
    return dt.datetime.combine(date, profile.close_time, tzinfo=profile.tz).astimezone(dt.UTC)


async def publish_quotes() -> int:
    row_number = (
        func.row_number()
        .over(partition_by=DailyBar.code, order_by=DailyBar.date.desc())
        .label("row_number")
    )
    ranked = (
        select(
            DailyBar.code,
            DailyBar.date,
            DailyBar.open,
            DailyBar.high,
            DailyBar.low,
            DailyBar.close,
            DailyBar.volume,
            row_number,
        )
        .where(
            DailyBar.market == MARKET,
            DailyBar.code.in_(
                select(Symbol.code).where(
                    Symbol.market == MARKET,
                    Symbol.is_active.is_(True),
                    Symbol.is_hidden.is_(False),
                    Symbol.data_status == "ready",
                )
            ),
        )
        .subquery()
    )
    sm = get_sessionmaker()
    async with sm() as session:
        rows = (await session.execute(select(ranked).where(ranked.c.row_number <= 2))).all()
        grouped: dict[str, list] = defaultdict(list)
        for row in rows:
            grouped[row.code].append(row)
        quote_rows = []
        for code, bars in grouped.items():
            bars.sort(key=lambda row: row.date, reverse=True)
            latest = bars[0]
            previous = bars[1] if len(bars) > 1 else None
            prev_close = previous.close if previous else None
            change = latest.close - prev_close if prev_close is not None else 0.0
            change_pct = change / prev_close * 100 if prev_close else 0.0
            quote_rows.append(
                {
                    "market": MARKET,
                    "code": code,
                    "ltp": latest.close,
                    "change": change,
                    "change_pct": change_pct,
                    "open": latest.open,
                    "high": latest.high,
                    "low": latest.low,
                    "close": latest.close,
                    "prev_close": prev_close,
                    "volume": latest.volume,
                    "trades": 0,
                    "as_of": _as_of(latest.date),
                    "is_delayed": True,
                }
            )
        if quote_rows:
            stmt = pg_insert(QuoteSnapshot).values(quote_rows)
            updates = {
                key: getattr(stmt.excluded, key)
                for key in quote_rows[0]
                if key not in {"market", "code"}
            }
            await session.execute(
                stmt.on_conflict_do_update(index_elements=["market", "code"], set_=updates)
            )
        await session.commit()
    return len(quote_rows)


async def publish_market_summary(*, days: int = 400) -> int:
    cutoff = dt.datetime.now(dt.UTC).date() - dt.timedelta(days=days)
    sm = get_sessionmaker()
    async with sm() as session:
        bars = (
            await session.execute(
                select(DailyBar.date, DailyBar.code, DailyBar.close, DailyBar.volume)
                .where(
                    DailyBar.market == MARKET,
                    DailyBar.date >= cutoff,
                    DailyBar.code.in_(
                        select(Symbol.code).where(
                            Symbol.market == MARKET,
                            Symbol.is_active.is_(True),
                            Symbol.is_hidden.is_(False),
                            Symbol.data_status == "ready",
                        )
                    ),
                )
                .order_by(DailyBar.date, DailyBar.code)
            )
        ).all()
        by_date: dict[dt.date, list] = defaultdict(list)
        for bar in bars:
            by_date[bar.date].append(bar)
        summary_rows = []
        prior_benchmark: float | None = None
        for date, day_bars in sorted(by_date.items()):
            benchmark = next((row.close for row in day_bars if row.code == BENCHMARK_CODE), None)
            summary_rows.append(
                {
                    "market": MARKET,
                    "date": date,
                    "dsex": None,
                    "dsex_change": None,
                    "ds30": None,
                    "ds30_change": None,
                    "benchmark_code": BENCHMARK_CODE,
                    "benchmark_close": benchmark,
                    "benchmark_change": (
                        benchmark - prior_benchmark
                        if benchmark is not None and prior_benchmark is not None
                        else None
                    ),
                    "total_trade": None,
                    "total_value_mn": sum(row.close * row.volume for row in day_bars) / 1e6,
                    "total_volume": sum(row.volume for row in day_bars),
                    "total_market_cap_mn": None,
                }
            )
            if benchmark is not None:
                prior_benchmark = benchmark
        if summary_rows:
            stmt = pg_insert(MarketSummary).values(summary_rows)
            updates = {
                key: getattr(stmt.excluded, key)
                for key in summary_rows[0]
                if key not in {"market", "date"}
            }
            await session.execute(
                stmt.on_conflict_do_update(index_elements=["market", "date"], set_=updates)
            )
        await session.commit()
    return len(summary_rows)


async def collect() -> dict[str, int]:
    return {
        "quotes": await publish_quotes(),
        "market_summaries": await publish_market_summary(),
    }
