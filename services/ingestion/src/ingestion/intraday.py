"""Persist delayed DSE quote history and sampled 15-minute research bars.

The public DSE source publishes cumulative delayed snapshots. These writers preserve the raw
knowledge-time observations first, then derive explicitly labelled sampled bars. They do not
manufacture exchange timestamps, trade-level OHLC, or a real-time feed.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy import case, func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from bulls.core.markets import get_market_profile
from bulls.core.models import (
    IntradayBar,
    IntradayCaptureSession,
    IntradayQuoteObservation,
    QuoteSnapshot,
)
from bulls.market_data import Quote
from bulls.market_data.calendar import is_trading_day, market_close_on, to_market_tz
from ingestion.lineage import persist_source_snapshot

INTRADAY_NORMALIZATION_VERSION = "dse-delayed-intraday-v1"
CAPTURE_INTERVAL_MINUTES = 15
SOURCE_NAME = "dse_latest_delayed"
OBSERVATION_BATCH_SIZE = 500
ObservationKey = tuple[str, str, dt.date, dt.datetime]


@dataclass(frozen=True)
class IntradayCaptureRows:
    observations: list[dict[str, Any]]
    bars: list[dict[str, Any]]
    session_date: dt.date
    capture_slot: dt.datetime
    regression_count: int


def _capture_slot(value: dt.datetime) -> dt.datetime:
    local = to_market_tz(value, market="DSE")
    minute = local.minute - local.minute % CAPTURE_INTERVAL_MINUTES
    return local.replace(minute=minute, second=0, microsecond=0)


def expected_capture_slots(session_date: dt.date) -> int:
    """Scheduled delayed captures from the open through close plus the final delayed read."""

    profile = get_market_profile("DSE")
    opened = dt.datetime.combine(session_date, profile.open_time, tzinfo=profile.tz)
    final_capture = dt.datetime.combine(
        session_date,
        market_close_on(session_date, "DSE"),
        tzinfo=profile.tz,
    ) + dt.timedelta(minutes=CAPTURE_INTERVAL_MINUTES)
    return int((final_capture - opened).total_seconds() // 60 // CAPTURE_INTERVAL_MINUTES) + 1


def is_expected_capture_time(value: dt.datetime) -> bool:
    local = to_market_tz(value, market="DSE")
    if not is_trading_day(local.date(), market="DSE"):
        return False
    profile = get_market_profile("DSE")
    opened = dt.datetime.combine(local.date(), profile.open_time, tzinfo=profile.tz)
    final_capture = dt.datetime.combine(
        local.date(),
        market_close_on(local.date(), "DSE"),
        tzinfo=profile.tz,
    ) + dt.timedelta(minutes=CAPTURE_INTERVAL_MINUTES)
    return opened <= local <= final_capture + dt.timedelta(minutes=5)


def _session_vwap(*, volume: int, turnover_mn: float | None) -> float | None:
    if volume <= 0 or turnover_mn is None or turnover_mn < 0:
        return None
    value = turnover_mn * 1_000_000 / volume
    return round(value, 6) if value > 0 else None


def _counter_delta(current: int, previous: int | None) -> int | None:
    if previous is None or current < previous:
        return None
    return current - previous


def _turnover_delta(current: float | None, previous: float | None) -> float | None:
    if current is None or previous is None or current + 1e-9 < previous:
        return None
    return max(0.0, current - previous)


def derive_capture_rows(
    quotes: Sequence[Quote],
    previous: Mapping[str, QuoteSnapshot],
    *,
    source_snapshot_id: Any,
) -> IntradayCaptureRows:
    """Build deterministic observation/bar rows without hiding cumulative-counter failures."""

    if not quotes:
        raise ValueError("intraday capture requires at least one quote")
    if any(quote.market != "DSE" for quote in quotes):
        raise ValueError("DSE intraday capture cannot accept another market")
    observed_dates = {to_market_tz(quote.as_of, market="DSE").date() for quote in quotes}
    slots = {_capture_slot(quote.as_of) for quote in quotes}
    if len(observed_dates) != 1 or len(slots) != 1:
        raise ValueError("one intraday delivery must share one DSE capture slot")
    session_date = observed_dates.pop()
    capture_slot = slots.pop()
    observations: list[dict[str, Any]] = []
    bars: list[dict[str, Any]] = []
    regression_count = 0
    for quote in sorted(quotes, key=lambda item: item.code):
        prior = previous.get(quote.code)
        prior_same_session = (
            prior is not None
            and to_market_tz(prior.as_of, market="DSE").date() == session_date
            and prior.as_of < quote.as_of
        )
        prior_volume = prior.volume if prior_same_session else None
        prior_trades = prior.trades if prior_same_session else None
        prior_turnover = prior.turnover_mn if prior_same_session else None
        regressed = bool(
            prior_same_session
            and (
                quote.volume < int(prior_volume or 0)
                or quote.trades < int(prior_trades or 0)
                or (
                    quote.turnover_mn is not None
                    and prior_turnover is not None
                    and quote.turnover_mn + 1e-9 < prior_turnover
                )
            )
        )
        unchanged = bool(
            prior_same_session
            and not regressed
            and quote.volume == prior_volume
            and quote.trades == prior_trades
            and quote.turnover_mn == prior_turnover
            and quote.ltp == prior.ltp
        )
        sequence_status = (
            "regressed"
            if regressed
            else "unchanged"
            if unchanged
            else "advanced"
            if prior_same_session
            else "baseline"
        )
        if regressed:
            regression_count += 1
        volume_delta = None if regressed else _counter_delta(quote.volume, prior_volume)
        trades_delta = None if regressed else _counter_delta(quote.trades, prior_trades)
        turnover_delta = None if regressed else _turnover_delta(quote.turnover_mn, prior_turnover)
        interval_vwap = _session_vwap(
            volume=volume_delta or 0,
            turnover_mn=turnover_delta,
        )
        session_vwap = _session_vwap(volume=quote.volume, turnover_mn=quote.turnover_mn)
        data_quality = (
            "counter_regression"
            if regressed
            else "baseline"
            if not prior_same_session
            else "missing_turnover"
            if turnover_delta is None or turnover_delta <= 0 or (volume_delta or 0) <= 0
            else "complete_delta"
        )
        observations.append(
            {
                "market": quote.market,
                "code": quote.code,
                "session_date": session_date,
                "observed_at": quote.as_of,
                "source_snapshot_id": source_snapshot_id,
                "capture_slot": capture_slot,
                "ltp": quote.ltp,
                "open": quote.open,
                "high": quote.high,
                "low": quote.low,
                "close": quote.close,
                "prev_close": quote.prev_close,
                "volume": quote.volume,
                "trades": quote.trades,
                "turnover_mn": quote.turnover_mn,
                "session_vwap": session_vwap,
                "is_delayed": quote.is_delayed,
                "sequence_status": sequence_status,
                "time_quality": "ingestion_upper_bound",
                "source": SOURCE_NAME,
            }
        )
        bars.append(
            {
                "market": quote.market,
                "code": quote.code,
                "session_date": session_date,
                "interval_start": capture_slot,
                "interval_minutes": CAPTURE_INTERVAL_MINUTES,
                "open": quote.ltp,
                "high": quote.ltp,
                "low": quote.ltp,
                "close": quote.ltp,
                "volume_delta": volume_delta,
                "trades_delta": trades_delta,
                "turnover_delta_mn": turnover_delta,
                "interval_vwap": interval_vwap,
                "cumulative_volume": quote.volume,
                "cumulative_trades": quote.trades,
                "cumulative_turnover_mn": quote.turnover_mn,
                "session_vwap": session_vwap,
                "observation_count": 1,
                "data_quality": data_quality,
                "time_quality": "ingestion_upper_bound",
                "source": SOURCE_NAME,
                "last_source_snapshot_id": source_snapshot_id,
                "known_at": quote.as_of,
            }
        )
    return IntradayCaptureRows(
        observations=observations,
        bars=bars,
        session_date=session_date,
        capture_slot=capture_slot,
        regression_count=regression_count,
    )


def _observation_key(row: Mapping[str, Any]) -> ObservationKey:
    return (
        str(row["market"]),
        str(row["code"]),
        row["session_date"],
        row.get("observed_at", row.get("known_at")),
    )


def _bars_for_inserted_observations(
    rows: list[dict[str, Any]], inserted: set[ObservationKey]
) -> list[dict[str, Any]]:
    return [row for row in rows if _observation_key(row) in inserted]


async def _insert_observations(
    session, rows: list[dict[str, Any]]
) -> set[ObservationKey]:
    inserted: set[ObservationKey] = set()
    for start in range(0, len(rows), OBSERVATION_BATCH_SIZE):
        batch = rows[start : start + OBSERVATION_BATCH_SIZE]
        result = await session.execute(
            pg_insert(IntradayQuoteObservation)
            .values(batch)
            .on_conflict_do_nothing(
                index_elements=["market", "code", "session_date", "observed_at"]
            )
            .returning(
                IntradayQuoteObservation.market,
                IntradayQuoteObservation.code,
                IntradayQuoteObservation.session_date,
                IntradayQuoteObservation.observed_at,
            )
        )
        inserted.update(
            (str(market), str(code), session_date, observed_at)
            for market, code, session_date, observed_at in result.all()
        )
    return inserted


async def _upsert_bars(session, rows: list[dict[str, Any]]) -> None:
    for start in range(0, len(rows), OBSERVATION_BATCH_SIZE):
        batch = rows[start : start + OBSERVATION_BATCH_SIZE]
        statement = pg_insert(IntradayBar).values(batch)
        has_regression = or_(
            IntradayBar.data_quality == "counter_regression",
            statement.excluded.data_quality == "counter_regression",
        )
        has_missing_turnover = or_(
            IntradayBar.data_quality == "missing_turnover",
            statement.excluded.data_quality == "missing_turnover",
        )
        has_complete_delta = or_(
            IntradayBar.data_quality == "complete_delta",
            statement.excluded.data_quality == "complete_delta",
        )
        combined_volume = func.coalesce(IntradayBar.volume_delta, 0) + func.coalesce(
            statement.excluded.volume_delta, 0
        )
        combined_trades = func.coalesce(IntradayBar.trades_delta, 0) + func.coalesce(
            statement.excluded.trades_delta, 0
        )
        combined_turnover = func.coalesce(
            IntradayBar.turnover_delta_mn, 0.0
        ) + func.coalesce(statement.excluded.turnover_delta_mn, 0.0)
        combined_quality = case(
            (has_regression, "counter_regression"),
            (has_missing_turnover, "missing_turnover"),
            (has_complete_delta, "complete_delta"),
            else_="baseline",
        )
        statement = statement.on_conflict_do_update(
            index_elements=["market", "code", "session_date", "interval_start"],
            set_={
                "high": func.greatest(IntradayBar.high, statement.excluded.close),
                "low": func.least(IntradayBar.low, statement.excluded.close),
                "close": statement.excluded.close,
                "volume_delta": case((has_regression, None), else_=combined_volume),
                "trades_delta": case((has_regression, None), else_=combined_trades),
                "turnover_delta_mn": case(
                    (or_(has_regression, has_missing_turnover), None),
                    else_=combined_turnover,
                ),
                "interval_vwap": case(
                    (
                        or_(has_regression, has_missing_turnover, combined_volume <= 0),
                        None,
                    ),
                    else_=combined_turnover * 1_000_000 / combined_volume,
                ),
                "cumulative_volume": statement.excluded.cumulative_volume,
                "cumulative_trades": statement.excluded.cumulative_trades,
                "cumulative_turnover_mn": statement.excluded.cumulative_turnover_mn,
                "session_vwap": statement.excluded.session_vwap,
                "observation_count": IntradayBar.observation_count + 1,
                "data_quality": combined_quality,
                "last_source_snapshot_id": statement.excluded.last_source_snapshot_id,
                "known_at": func.greatest(IntradayBar.known_at, statement.excluded.known_at),
                "updated_at": func.now(),
            },
        )
        await session.execute(statement)


def _capture_blockers(
    *,
    after_final_capture: bool,
    slot_pct: float,
    symbol_pct: float,
    vwap_pct: float,
    regressions: int,
) -> list[str]:
    blockers: list[str] = []
    if not after_final_capture:
        blockers.append("The delayed capture window has not completed.")
    if slot_pct < 90:
        blockers.append("Fewer than 90% of scheduled capture slots were retained.")
    if symbol_pct < 90:
        blockers.append("Fewer than 90% of the observed DSE universe was retained.")
    if vwap_pct < 80:
        blockers.append("Session VWAP is unavailable for more than 20% of sampled bars.")
    if regressions:
        blockers.append("Cumulative provider counters regressed within the session.")
    return blockers


async def _refresh_capture_session(
    session,
    *,
    session_date: dt.date,
    expected_symbol_count: int,
    captured_at: dt.datetime,
) -> IntradayCaptureSession:
    observation_count, observed_symbols, first_observed, latest_observed, regressions = (
        await session.execute(
            select(
                func.count(),
                func.count(func.distinct(IntradayQuoteObservation.code)),
                func.min(IntradayQuoteObservation.observed_at),
                func.max(IntradayQuoteObservation.observed_at),
                func.count().filter(IntradayQuoteObservation.sequence_status == "regressed"),
            ).where(
                IntradayQuoteObservation.market == "DSE",
                IntradayQuoteObservation.session_date == session_date,
            )
        )
    ).one()
    bar_count, observed_slots, vwap_bars = (
        await session.execute(
            select(
                func.count(),
                func.count(func.distinct(IntradayBar.interval_start)),
                func.count().filter(IntradayBar.session_vwap.isnot(None)),
            ).where(
                IntradayBar.market == "DSE",
                IntradayBar.session_date == session_date,
            )
        )
    ).one()
    expected_slots = expected_capture_slots(session_date)
    slot_pct = min(100.0, float(observed_slots or 0) / expected_slots * 100)
    symbol_pct = (
        min(100.0, float(observed_symbols or 0) / expected_symbol_count * 100)
        if expected_symbol_count
        else 0.0
    )
    vwap_pct = float(vwap_bars or 0) / float(bar_count or 1) * 100
    profile = get_market_profile("DSE")
    final_capture = dt.datetime.combine(
        session_date,
        market_close_on(session_date, "DSE"),
        tzinfo=profile.tz,
    ) + dt.timedelta(minutes=CAPTURE_INTERVAL_MINUTES)
    local_capture = to_market_tz(captured_at, market="DSE")
    after_final = local_capture >= final_capture
    blockers = _capture_blockers(
        after_final_capture=after_final,
        slot_pct=slot_pct,
        symbol_pct=symbol_pct,
        vwap_pct=vwap_pct,
        regressions=int(regressions or 0),
    )
    status = "collecting" if not after_final else "complete" if not blockers else "incomplete"
    lag = max(0.0, (dt.datetime.now(dt.UTC) - captured_at.astimezone(dt.UTC)).total_seconds())
    values = {
        "market": "DSE",
        "session_date": session_date,
        "status": status,
        "expected_slot_count": expected_slots,
        "observed_slot_count": int(observed_slots or 0),
        "expected_symbol_count": expected_symbol_count,
        "observed_symbol_count": int(observed_symbols or 0),
        "observation_count": int(observation_count or 0),
        "bar_count": int(bar_count or 0),
        "vwap_bar_count": int(vwap_bars or 0),
        "counter_regression_count": int(regressions or 0),
        "slot_completeness_pct": round(slot_pct, 3),
        "symbol_completeness_pct": round(symbol_pct, 3),
        "vwap_coverage_pct": round(vwap_pct, 3),
        "first_observed_at": first_observed,
        "latest_observed_at": latest_observed,
        "maximum_capture_lag_seconds": round(lag, 3),
        "research_eligible": status == "complete",
        "blockers": blockers,
        "metrics": {
            "source": SOURCE_NAME,
            "interval_minutes": CAPTURE_INTERVAL_MINUTES,
            "declared_source_delay_minutes": 15,
            "source_timestamp_available": False,
            "time_quality": "ingestion_upper_bound",
            "price_bar_kind": "sampled_ltp",
            "session_vwap_kind": "cumulative_turnover_over_volume",
        },
    }
    statement = pg_insert(IntradayCaptureSession).values(values)
    update_values = {
        key: getattr(statement.excluded, key)
        for key in values
        if key not in {"market", "session_date"}
    }
    update_values["maximum_capture_lag_seconds"] = func.greatest(
        IntradayCaptureSession.maximum_capture_lag_seconds,
        statement.excluded.maximum_capture_lag_seconds,
    )
    statement = statement.on_conflict_do_update(
        index_elements=["market", "session_date"],
        set_=update_values,
    )
    await session.execute(statement)
    return IntradayCaptureSession(**values)


async def persist_intraday_capture(
    session,
    quotes: Sequence[Quote],
    *,
    expected_symbol_count: int,
) -> IntradayCaptureSession | None:
    """Persist one DSE delivery before the mutable latest-quote projection is overwritten."""

    if not quotes:
        return None
    dse_quotes = [quote for quote in quotes if quote.market == "DSE"]
    if not dse_quotes:
        return None
    codes = [quote.code for quote in dse_quotes]
    previous = {
        item.code: item
        for item in await session.scalars(
            select(QuoteSnapshot).where(
                QuoteSnapshot.market == "DSE",
                QuoteSnapshot.code.in_(codes),
            )
        )
    }
    normalized = [
        quote.model_dump(mode="json") for quote in sorted(dse_quotes, key=lambda item: item.code)
    ]
    captured_at = max(quote.as_of for quote in dse_quotes)
    if not is_expected_capture_time(captured_at):
        return None
    slot = _capture_slot(captured_at)
    session_date = slot.date()
    snapshot_id = await persist_source_snapshot(
        session,
        market="DSE",
        dataset_key="intraday_delayed_quotes",
        provider="dsebd.org",
        scope_key=f"{session_date.isoformat()}:{slot.isoformat()}",
        normalized_records=normalized,
        normalization_version=INTRADAY_NORMALIZATION_VERSION,
        known_at=captured_at,
        quality_report={
            "quote_count": len(dse_quotes),
            "expected_symbol_count": expected_symbol_count,
            "is_delayed": True,
            "source_timestamp_available": False,
        },
        source_metadata={
            "raw_delivery_retained": False,
            "time_quality": "ingestion_upper_bound",
            "capture_interval_minutes": CAPTURE_INTERVAL_MINUTES,
        },
    )
    rows = derive_capture_rows(dse_quotes, previous, source_snapshot_id=snapshot_id)
    inserted_observations = await _insert_observations(session, rows.observations)
    new_bar_rows = _bars_for_inserted_observations(rows.bars, inserted_observations)
    await _upsert_bars(session, new_bar_rows)
    await session.flush()
    return await _refresh_capture_session(
        session,
        session_date=rows.session_date,
        expected_symbol_count=expected_symbol_count,
        captured_at=captured_at,
    )
