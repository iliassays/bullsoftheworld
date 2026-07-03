"""Out-of-band health watchdog — runs as its OWN systemd timer (every 5 min), independent of the
arq worker, so a dead or crash-looping worker can't take its own monitor down with it.

It checks the three things that, if broken, make the site silently wrong:

  1. the worker unit is alive          (systemctl is-active bullsofdhaka-worker)
  2. quotes are fresh in trading hours  (max(quote_snapshots.as_of) not older than STALE_AFTER)
  3. the API answers /health            (HTTP 200)

On trouble it attempts a one-shot worker restart (for worker-down / stale-data faults) and emails
an alert via Resend. The email is rate-limited by a Redis cooldown key so a sustained outage pages
once per COOLDOWN, not every 5 minutes; a clean run clears the key so the next incident pages
immediately. Exit code is non-zero on problems (handy in the journal), but mail is the real signal.

    uv run python -m ingestion.watchdog
"""

from __future__ import annotations

import asyncio
import datetime as dt
import logging
import subprocess
import sys

import httpx
import redis.asyncio as aioredis
from sqlalchemy import text

from bulls.core.config import get_settings
from bulls.core.db import get_sessionmaker
from bulls.market_data.calendar import is_trading_day, is_trading_hours, to_market_tz

logging.basicConfig(level=logging.INFO, format="%(asctime)s watchdog %(levelname)s %(message)s")
log = logging.getLogger("watchdog")

WORKER_UNIT = "bullsofdhaka-worker"
STALE_AFTER = dt.timedelta(minutes=35)  # poll is every 15 min; 35 tolerates one missed cycle
# (a transient blip self-heals next poll) but still flags a truly dead worker, whose data only
# grows staler. Tight enough to catch real faults within ~2 poll cycles, loose enough not to page
# on a single hiccup or a deploy-restart landing on a poll boundary.
COOLDOWN_SECONDS = 60 * 60  # page at most once an hour for an ongoing incident
_COOLDOWN_KEY = "watchdog:alerted"
# The EOD chain runs 13:00-13:50 UTC. After it should be done, on a trading day, today's bars +
# trending must exist. Check window 14:00-17:59 UTC (20:00-23:59 Dhaka): after the chain completes,
# before the Dhaka date rolls. Catches a hung cron loop (the 2026-06-29 incident) that the intraday
# quote-freshness check can't see, because it's silent once the market is closed.
EOD_CHECK_FROM_UTC_HOUR = 14
EOD_CHECK_TO_UTC_HOUR = 18


def _unit_active(unit: str) -> bool:
    try:
        r = subprocess.run(
            ["systemctl", "is-active", unit], capture_output=True, text=True, timeout=10
        )
        return r.stdout.strip() == "active"
    except Exception:
        log.exception("systemctl is-active failed for %s", unit)
        return False


def _restart_unit(unit: str) -> str:
    """Best-effort restart; returns a short human outcome for the alert body."""
    try:
        r = subprocess.run(
            ["systemctl", "restart", unit], capture_output=True, text=True, timeout=30
        )
        if r.returncode == 0:
            return f"restart of {unit} issued"
        return f"restart of {unit} FAILED (rc={r.returncode}: {r.stderr.strip()[:120]})"
    except Exception as e:  # surfaced in the alert, never raises
        return f"restart of {unit} errored: {type(e).__name__}"


async def _quote_age() -> dt.timedelta | None:
    """Age of the newest DSE quote, or None if the table is empty / unreadable."""
    async with get_sessionmaker()() as session:
        row = await session.execute(
            text("select max(as_of) from quote_snapshots where market = 'DSE'")
        )
        latest = row.scalar_one_or_none()
    if latest is None:
        return None
    if latest.tzinfo is None:
        latest = latest.replace(tzinfo=dt.UTC)
    return dt.datetime.now(dt.UTC) - latest


async def _api_ok(base_url: str) -> bool:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(f"{base_url.rstrip('/')}/health")
        return r.status_code == 200
    except Exception:
        log.warning("API /health check failed", exc_info=True)
        return False


async def _eod_problems(now: dt.datetime) -> list[str]:
    """In the post-EOD window on a trading day, today's bars + trending must be present."""
    if not (EOD_CHECK_FROM_UTC_HOUR <= now.hour < EOD_CHECK_TO_UTC_HOUR):
        return []
    today = to_market_tz(now).date()
    if not is_trading_day(today):
        return []
    async with get_sessionmaker()() as session:
        bar = (
            await session.execute(text("select max(date) from daily_bars where market = 'DSE'"))
        ).scalar_one_or_none()
        trend = (
            await session.execute(
                text("select max(as_of_date) from trending_scores where market = 'DSE'")
            )
        ).scalar_one_or_none()
    problems: list[str] = []
    if bar != today:
        problems.append(f"EOD bars not updated for {today} (latest {bar}) — the worker's EOD chain didn't run")
    if trend != today:
        problems.append(f"'Active today' not updated for {today} (latest {trend})")
    return problems


async def _send_alert(problems: list[str], actions: list[str]) -> None:
    s = get_settings()
    recipients = [a.strip() for a in (s.alert_email or s.support_email).split(",") if a.strip()]
    if not s.resend_api_key or not recipients:
        log.error("ALERT (email not configured): %s", "; ".join(problems))
        return
    now = to_market_tz(dt.datetime.now(dt.UTC)).strftime("%Y-%m-%d %H:%M Dhaka")
    lines = [f"Bulls of Dhaka health check failed at {now}:", "", *(f"• {p}" for p in problems)]
    if actions:
        lines += ["", "Actions taken:", *(f"• {a}" for a in actions)]
    lines += ["", "You'll get at most one of these per hour while it persists."]
    body = "\n".join(lines)
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {s.resend_api_key}"},
                json={
                    "from": s.email_from,
                    "to": recipients,
                    "subject": "⚠️ Bulls of Dhaka — health alert",
                    "text": body,
                },
            )
        if resp.status_code >= 300:
            log.error("alert email failed %s: %s", resp.status_code, resp.text)
    except Exception:
        log.exception("alert email error")


async def main() -> int:
    s = get_settings()
    now = dt.datetime.now(dt.UTC)
    problems: list[str] = []
    actions: list[str] = []
    worker_fault = False

    if not _unit_active(WORKER_UNIT):
        problems.append(f"{WORKER_UNIT} is not active")
        worker_fault = True

    if is_trading_hours(now):
        age = await _quote_age()
        if age is None:
            problems.append("no DSE quotes in the database during trading hours")
            worker_fault = True
        elif age > STALE_AFTER:
            mins = int(age.total_seconds() // 60)
            problems.append(f"DSE quotes are stale ({mins} min old) during trading hours")
            worker_fault = True

    if not await _api_ok(s.api_public_url):
        problems.append(f"API health check failed ({s.api_public_url}/health)")

    # EOD staleness: alert only — don't restart. The missed jobs are already past (a restart won't
    # re-run them), and restarting every 5 min through the window would be a restart storm. The
    # email is the signal to manually re-run the EOD chain.
    problems += await _eod_problems(now)

    if not problems:
        log.info("ok — worker active, quotes fresh, API healthy")
        # clear cooldown so the next genuine incident pages immediately
        try:
            r = aioredis.from_url(s.redis_url)
            await r.delete(_COOLDOWN_KEY)
            await r.aclose()
        except Exception:
            log.warning("could not clear cooldown key", exc_info=True)
        return 0

    if worker_fault:
        actions.append(_restart_unit(WORKER_UNIT))

    # Cooldown: only one of us should send within COOLDOWN. SET NX wins the race atomically.
    should_email = True
    try:
        r = aioredis.from_url(s.redis_url)
        should_email = bool(await r.set(_COOLDOWN_KEY, now.isoformat(), nx=True, ex=COOLDOWN_SECONDS))
        await r.aclose()
    except Exception:
        log.warning("redis cooldown unavailable — emailing anyway", exc_info=True)

    log.error("PROBLEMS: %s | actions: %s | emailed=%s", problems, actions, should_email)
    if should_email:
        await _send_alert(problems, actions)
    return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
