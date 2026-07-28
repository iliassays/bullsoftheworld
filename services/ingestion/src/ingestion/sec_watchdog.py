"""Out-of-band health monitor for Bulls of Wall Street EOD and SEC evidence."""

from __future__ import annotations

import asyncio
import datetime as dt
import hashlib
import json
import logging
import math
import subprocess
import sys
from collections.abc import Mapping

import httpx
import redis.asyncio as aioredis
from sqlalchemy import func, select

from bulls.core.config import get_settings
from bulls.core.db import get_sessionmaker
from bulls.core.models import DailyBar, RegulatoryDataState, Symbol, TickerAnalytics
from bulls.market_data.calendar import is_trading_day, to_market_tz
from ingestion.sec import sec_target_symbol_count
from ingestion.us_worker import most_recent_due_session

logging.basicConfig(level=logging.INFO, format="%(asctime)s sec-watchdog %(levelname)s %(message)s")
log = logging.getLogger("sec-watchdog")

MARKET = "US"
WORKER_UNIT = "bullsofwallst-sec-worker"
EOD_WORKER_UNIT = "bullsofwallst-worker"
COOLDOWN_SECONDS = 6 * 60 * 60
COOLDOWN_KEY = "watchdog:bullsofwallst:sec:alerted"
STATUS_KEY = "watchdog:bullsofwallst:sec:last_status"
STATUS_FINGERPRINT_KEY = "watchdog:bullsofwallst:sec:last_fingerprint"
STATUS_HISTORY_KEY = "watchdog:bullsofwallst:sec:history"
STATUS_RETENTION_SECONDS = 30 * 24 * 60 * 60
STATUS_HISTORY_LIMIT = 200
SEC_MAX_AGE = dt.timedelta(hours=36)
THIRTEEN_F_MAX_AGE = dt.timedelta(days=8)
FINRA_MAX_AGE = dt.timedelta(days=4)
FINRA_MIN_MATCH_RATIO = 0.80
TARGET_13F_QUARTERS = 8
# most_recent_due_session() flips to "today" 90 minutes after close (see us_worker.py) — that
# delay is tuned so the primary EOD cron, fixed at 22:45 UTC, sees the due session already as
# today when IT runs. Reusing that same flip for "should the watchdog complain yet" was the
# 2026-07-15 false-positive bug: the due session flips at close+90min (21:30 UTC on a regular
# EDT day), a full ~75 minutes before the 22:45 UTC cron has even attempted the pull, so every
# watchdog run in that window reported 0 coverage on a fully healthy pipeline. Bumping the shared
# delay would fix the watchdog but break the cron (it would stop seeing today as due at its own
# 22:45 UTC runtime). Instead, gate the alert separately on whether the cron has actually had a
# chance to run for the due session.
_EOD_CRON_ATTEMPT_UTC = dt.time(22, 45)
_EOD_CRON_GRACE = dt.timedelta(minutes=10)


def _unit_active(unit: str) -> bool:
    try:
        result = subprocess.run(
            ["systemctl", "is-active", unit],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.stdout.strip() == "active"
    except Exception:
        log.exception("systemctl is-active failed for %s", unit)
        return False


def _restart_unit(unit: str) -> str:
    try:
        result = subprocess.run(
            ["systemctl", "restart", unit],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return (
            f"restart of {unit} issued"
            if result.returncode == 0
            else (f"restart of {unit} failed (rc={result.returncode})")
        )
    except Exception as error:
        return f"restart of {unit} errored: {type(error).__name__}"


def _state_problems(
    now: dt.datetime,
    ready_symbols: int,
    states: Mapping[str, RegulatoryDataState],
    *,
    sec_target_symbols: int | None = None,
) -> list[str]:
    problems = []
    if ready_symbols <= 0:
        return ["no retail-ready US symbols are configured"]

    sec = states.get("sec_edgar")
    if sec is None:
        problems.append("SEC EDGAR state is missing")
    else:
        sec_targets = ready_symbols if sec_target_symbols is None else sec_target_symbols
        age = now - sec.last_success_at
        if age > SEC_MAX_AGE:
            problems.append(f"SEC EDGAR refresh is {age.total_seconds() / 3600:.1f} hours old")
        if sec_targets > 0 and sec.symbols_covered / sec_targets < 0.9:
            problems.append(
                "SEC EDGAR covers "
                f"{sec.symbols_covered}/{sec_targets} SEC-targetable symbols"
            )
        details = sec.details or {}
        requested = int(details.get("symbols_requested") or 0)
        failed = int(details.get("symbols_failed") or 0)
        if requested and failed / requested > 0.1:
            problems.append(f"SEC EDGAR refresh failed for {failed}/{requested} symbols")

    holdings = states.get("sec_13f")
    if holdings is None:
        problems.append("SEC 13F state is missing")
    else:
        age = now - holdings.last_success_at
        if age > THIRTEEN_F_MAX_AGE:
            problems.append(f"SEC 13F refresh is {age.days} days old")
        details = holdings.details or {}
        history = int(details.get("history_quarters_loaded") or 1)
        if history < TARGET_13F_QUARTERS:
            problems.append(f"SEC 13F history has {history}/{TARGET_13F_QUARTERS} quarters")
        if holdings.symbols_covered / ready_symbols < 0.8:
            problems.append(
                f"SEC 13F maps {holdings.symbols_covered}/{ready_symbols} ready symbols"
            )

    finra = states.get("finra_short_volume")
    if finra is None:
        problems.append("FINRA short-volume state is missing")
    else:
        age = now - finra.last_success_at
        if age > FINRA_MAX_AGE:
            problems.append(f"FINRA short-volume refresh is {age.days} days old")
        local_now = to_market_tz(now, market=MARKET)
        if (
            is_trading_day(local_now.date(), market=MARKET)
            and local_now.time() >= dt.time(20, 30)
            and (finra.as_of_date is None or finra.as_of_date < local_now.date())
        ):
            problems.append(
                f"FINRA short-volume latest {finra.as_of_date}; expected {local_now.date()}"
            )
        if finra.records <= 0 or finra.symbols_covered <= 0:
            problems.append("FINRA short-volume checkpoint contains no matched symbol records")
        details = finra.details or {}
        source_rows = int(details.get("latest_source_rows") or 0)
        stored_rows = int(details.get("latest_stored_rows") or 0)
        if source_rows and stored_rows / source_rows < FINRA_MIN_MATCH_RATIO:
            problems.append(
                "FINRA short-volume symbol match coverage fell to "
                f"{stored_rows}/{source_rows} ({stored_rows / source_rows:.1%})"
            )
    return problems


def _eod_cron_has_run(now: dt.datetime, due_session: dt.date) -> bool:
    """True once the primary EOD cron has had a chance to complete for `due_session`.

    A prior calendar day has had the 22:45/23:30/01:30/13:30 UTC cycles to fill in; only "is
    due_session still today" needs the explicit clock check.
    """
    local_today = to_market_tz(now, market=MARKET).date()
    if due_session < local_today:
        return True
    attempt = (
        dt.datetime.combine(due_session, _EOD_CRON_ATTEMPT_UTC, tzinfo=dt.UTC) + _EOD_CRON_GRACE
    )
    return now >= attempt


def _eod_state_problems(
    now: dt.datetime,
    due_session: dt.date,
    ready_symbols: int,
    latest_bar_date: dt.date | None,
    covered_symbols: int,
    analytics_date: dt.date | None,
    min_coverage: float,
) -> list[str]:
    if ready_symbols <= 0:
        return ["no retail-ready US symbols are configured"]
    if not _eod_cron_has_run(now, due_session):
        return []
    required = math.ceil(ready_symbols * min_coverage)
    problems = []
    if latest_bar_date is None or latest_bar_date < due_session:
        problems.append(f"US EOD bars latest {latest_bar_date}; expected {due_session}")
    elif covered_symbols < required:
        problems.append(
            f"US EOD bars cover {covered_symbols}/{ready_symbols} symbols for {due_session}; "
            f"required {required}"
        )
    if analytics_date is None or analytics_date < due_session:
        problems.append(f"US analytics latest {analytics_date}; expected {due_session}")
    return problems


async def _api_ready(base_url: str) -> bool:
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(f"{base_url.rstrip('/')}/ready")
        return response.status_code == 200
    except Exception:
        log.warning("Wall Street API readiness check failed", exc_info=True)
        return False


async def _database_problems(now: dt.datetime) -> list[str]:
    sec_target_symbols = await sec_target_symbol_count()
    sm = get_sessionmaker()
    async with sm() as session:
        ready_symbols = int(
            await session.scalar(
                select(func.count())
                .select_from(Symbol)
                .where(
                    Symbol.market == MARKET,
                    Symbol.is_active.is_(True),
                    Symbol.is_hidden.is_(False),
                    Symbol.data_status == "ready",
                )
            )
            or 0
        )
        rows = list(
            await session.scalars(
                select(RegulatoryDataState).where(RegulatoryDataState.market == MARKET)
            )
        )
        due_session = most_recent_due_session(now)
        latest_bar_date = await session.scalar(
            select(func.max(DailyBar.date)).where(DailyBar.market == MARKET)
        )
        covered_symbols = int(
            await session.scalar(
                select(func.count(func.distinct(DailyBar.code))).where(
                    DailyBar.market == MARKET,
                    DailyBar.date == due_session,
                    DailyBar.code.in_(
                        select(Symbol.code).where(
                            Symbol.market == MARKET,
                            Symbol.is_active.is_(True),
                            Symbol.is_hidden.is_(False),
                            Symbol.data_status == "ready",
                        )
                    ),
                )
            )
            or 0
        )
        analytics_date = await session.scalar(
            select(func.max(TickerAnalytics.as_of_date)).where(TickerAnalytics.market == MARKET)
        )
    states = {row.source: row for row in rows}
    sec_covered = states.get("sec_edgar")
    log.info(
        "coverage scope ready=%s sec_targetable=%s sec_covered=%s",
        ready_symbols,
        sec_target_symbols,
        sec_covered.symbols_covered if sec_covered is not None else None,
    )
    return [
        *_state_problems(
            now,
            ready_symbols,
            states,
            sec_target_symbols=sec_target_symbols,
        ),
        *_eod_state_problems(
            now,
            due_session,
            ready_symbols,
            latest_bar_date,
            covered_symbols,
            analytics_date,
            get_settings().us_eod_min_coverage,
        ),
    ]


def _status_event(
    now: dt.datetime,
    problems: list[str],
    actions: list[str],
    *,
    email_scheduled: bool,
) -> tuple[str, str]:
    """Return a stable incident fingerprint and a structured operational event."""

    status = "degraded" if problems else "healthy"
    fingerprint_payload = {"status": status, "problems": sorted(problems)}
    fingerprint = hashlib.sha256(
        json.dumps(fingerprint_payload, sort_keys=True).encode()
    ).hexdigest()
    payload = json.dumps(
        {
            "checked_at": now.isoformat(),
            "status": status,
            "problems": problems,
            "actions": actions,
            "email_scheduled": email_scheduled,
        },
        sort_keys=True,
    )
    return fingerprint, payload


async def _record_status_transition(
    redis,
    now: dt.datetime,
    problems: list[str],
    actions: list[str],
    *,
    email_scheduled: bool,
) -> None:
    """Persist the latest status and a capped history of incident/recovery transitions."""

    fingerprint, payload = _status_event(
        now,
        problems,
        actions,
        email_scheduled=email_scheduled,
    )
    previous = await redis.get(STATUS_FINGERPRINT_KEY)
    if isinstance(previous, bytes):
        previous = previous.decode()
    pipeline = redis.pipeline(transaction=True)
    pipeline.set(STATUS_KEY, payload, ex=STATUS_RETENTION_SECONDS)
    pipeline.set(
        STATUS_FINGERPRINT_KEY,
        fingerprint,
        ex=STATUS_RETENTION_SECONDS,
    )
    if previous != fingerprint:
        pipeline.lpush(STATUS_HISTORY_KEY, payload)
        pipeline.ltrim(STATUS_HISTORY_KEY, 0, STATUS_HISTORY_LIMIT - 1)
        pipeline.expire(STATUS_HISTORY_KEY, STATUS_RETENTION_SECONDS)
    await pipeline.execute()


async def _send_alert(problems: list[str], actions: list[str]) -> None:
    settings = get_settings()
    recipients = [
        value.strip()
        for value in (
            settings.wallst_alert_email or settings.alert_email or settings.support_email
        ).split(",")
        if value.strip()
    ]
    if not settings.resend_api_key or not recipients:
        log.error("ALERT (email not configured): %s", "; ".join(problems))
        return
    lines = [
        f"Bulls of Wall Street data health check failed at {dt.datetime.now(dt.UTC):%Y-%m-%d %H:%M UTC}:",
        "",
        *(f"- {problem}" for problem in problems),
    ]
    if actions:
        lines += ["", "Actions taken:", *(f"- {action}" for action in actions)]
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {settings.resend_api_key}"},
            json={
                "from": settings.email_from,
                "to": recipients,
                "subject": "Bulls of Wall Street - data health alert",
                "text": "\n".join(lines),
            },
        )
    if response.status_code >= 300:
        log.error("alert email failed %s: %s", response.status_code, response.text)


async def main() -> int:
    settings = get_settings()
    now = dt.datetime.now(dt.UTC)
    problems = []
    actions = []
    if not _unit_active(WORKER_UNIT):
        problems.append(f"{WORKER_UNIT} is not active")
        actions.append(_restart_unit(WORKER_UNIT))
    if not _unit_active(EOD_WORKER_UNIT):
        problems.append(f"{EOD_WORKER_UNIT} is not active")
        actions.append(_restart_unit(EOD_WORKER_UNIT))
    if not await _api_ready(settings.wallst_api_public_url):
        problems.append(f"API readiness failed ({settings.wallst_api_public_url}/ready)")
    try:
        problems.extend(await _database_problems(now))
    except Exception:
        log.exception("regulatory-state check failed")
        problems.append("regulatory-state query failed")

    redis = aioredis.from_url(settings.redis_url)
    should_email = False
    try:
        if not problems:
            await redis.delete(COOLDOWN_KEY)
        else:
            should_email = bool(
                await redis.set(
                    COOLDOWN_KEY,
                    now.isoformat(),
                    nx=True,
                    ex=COOLDOWN_SECONDS,
                )
            )
        await _record_status_transition(
            redis,
            now,
            problems,
            actions,
            email_scheduled=should_email,
        )
    except Exception:
        if problems:
            log.warning("Redis watchdog state unavailable; emailing", exc_info=True)
            should_email = True
        else:
            log.warning("Redis watchdog state unavailable", exc_info=True)
    finally:
        await redis.aclose()

    if not problems:
        log.info("ok - EOD, SEC, API, history, freshness, and coverage are healthy")
        return 0

    log.error("PROBLEMS: %s | actions: %s | emailed=%s", problems, actions, should_email)
    if should_email:
        try:
            await _send_alert(problems, actions)
        except Exception:
            log.exception("alert email failed")
    return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
