"""Out-of-band health monitor for Bulls of Wall Street EOD and SEC evidence."""

from __future__ import annotations

import asyncio
import datetime as dt
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
from ingestion.us_worker import most_recent_due_session

logging.basicConfig(level=logging.INFO, format="%(asctime)s sec-watchdog %(levelname)s %(message)s")
log = logging.getLogger("sec-watchdog")

MARKET = "US"
WORKER_UNIT = "bullsofwallst-sec-worker"
EOD_WORKER_UNIT = "bullsofwallst-worker"
COOLDOWN_SECONDS = 6 * 60 * 60
COOLDOWN_KEY = "watchdog:bullsofwallst:sec:alerted"
SEC_MAX_AGE = dt.timedelta(hours=36)
THIRTEEN_F_MAX_AGE = dt.timedelta(days=8)
FINRA_MAX_AGE = dt.timedelta(days=4)
TARGET_13F_QUARTERS = 8


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
) -> list[str]:
    problems = []
    if ready_symbols <= 0:
        return ["no retail-ready US symbols are configured"]

    sec = states.get("sec_edgar")
    if sec is None:
        problems.append("SEC EDGAR state is missing")
    else:
        age = now - sec.last_success_at
        if age > SEC_MAX_AGE:
            problems.append(f"SEC EDGAR refresh is {age.total_seconds() / 3600:.1f} hours old")
        if sec.symbols_covered / ready_symbols < 0.9:
            problems.append(f"SEC EDGAR covers {sec.symbols_covered}/{ready_symbols} ready symbols")
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
    return problems


def _eod_state_problems(
    due_session: dt.date,
    ready_symbols: int,
    latest_bar_date: dt.date | None,
    covered_symbols: int,
    analytics_date: dt.date | None,
    min_coverage: float,
) -> list[str]:
    if ready_symbols <= 0:
        return ["no retail-ready US symbols are configured"]
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
    return [
        *_state_problems(now, ready_symbols, {row.source: row for row in rows}),
        *_eod_state_problems(
            due_session,
            ready_symbols,
            latest_bar_date,
            covered_symbols,
            analytics_date,
            get_settings().us_eod_min_coverage,
        ),
    ]


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
    try:
        if not problems:
            await redis.delete(COOLDOWN_KEY)
            log.info("ok - EOD, SEC, API, history, freshness, and coverage are healthy")
            return 0
        should_email = bool(
            await redis.set(
                COOLDOWN_KEY,
                now.isoformat(),
                nx=True,
                ex=COOLDOWN_SECONDS,
            )
        )
    except Exception:
        log.warning("Redis cooldown unavailable; emailing", exc_info=True)
        should_email = True
    finally:
        await redis.aclose()

    log.error("PROBLEMS: %s | actions: %s | emailed=%s", problems, actions, should_email)
    if should_email:
        try:
            await _send_alert(problems, actions)
        except Exception:
            log.exception("alert email failed")
    return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
