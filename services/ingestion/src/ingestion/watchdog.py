"""Out-of-band health watchdog — runs as its OWN systemd timer (every 5 min), independent of the
arq worker, so a dead or crash-looping worker can't take its own monitor down with it.

It checks the things that, if broken, make the site silently wrong:

  1. the worker unit is alive          (systemctl is-active bullsofdhaka-worker)
  2. quotes are fresh in trading hours  (max(quote_snapshots.as_of) not older than STALE_AFTER)
  3. the API answers /health            (HTTP 200)
  4. today's EOD chain ran              (see _eod_problems)
  5. no impossible values got ingested  (see _data_quality_problems — OHLC/shareholding/
     dividend/index invariants; second line of defense behind the parser-level checks in
     packages/market_data, in case a future bug or a manual edit bypasses them)
  6. the agent model portfolios obey their invariants (see _agent_problems — no negative cash,
     no overdue settlements, holdings==lots, daily churn ceiling)
  7. today's scheduled agent posts/signals actually fired (see _publish_freshness_problems) —
     confirmed live (2026-07-06) that arq's cron loop can silently stall for ~30 min with the
     worker unit still reporting "active" and no error logged: pull_eod_summary/refresh_analytics
     ran fine at 13:05-13:15, then run_trending/run_signals(13:25)/pull_news(13:35)/
     run_factor_signals(13:40) never even logged a start, before run_market_signals(13:50) ran
     normally again. Checks #4 already covered "EOD bars/trending", missed here entirely.

On trouble it attempts a one-shot worker restart (for worker-down / stale-data / stalled-cron
faults — the last of which #7 exists specifically to catch, and is now actionable: every affected
job now runs on worker startup too, see worker.py, so a restart genuinely recovers a day's missed
posts instead of just being a no-op) and emails an alert via Resend. The email is rate-limited by
a Redis cooldown key so a sustained outage pages once per COOLDOWN, not every 5 minutes; a clean
run clears the key so the next incident pages immediately. Exit code is non-zero on problems
(handy in the journal), but mail is the real signal.

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
# Morning Watch is scheduled 03:30 UTC; check from 05:00 to give a slow start plenty of room
# before flagging it, but still well before the 04:00-08:30 UTC trading session ends.
MORNING_WATCH_CHECK_FROM_UTC_HOUR = 5


def _utc_check_start(market_date: dt.date, hour: int) -> dt.datetime:
    """UTC instant when a check for a given Dhaka market date may start.

    Near 18:00-23:59 UTC the Dhaka calendar has already rolled to tomorrow, but the jobs for that
    Dhaka date have not reached their UTC schedule yet. Checking by ``now.hour`` alone creates a
    false alert for tomorrow's Morning Watch before it is even due.
    """
    return dt.datetime.combine(market_date, dt.time(hour=hour, tzinfo=dt.UTC))


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
    url = f"{base_url.rstrip('/')}/health"
    for attempt in range(3):
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.get(url)
            if r.status_code == 200:
                return True
            log.warning("API /health returned %s on attempt %s", r.status_code, attempt + 1)
        except Exception:
            log.warning("API /health check failed on attempt %s", attempt + 1, exc_info=True)
        if attempt < 2:
            await asyncio.sleep(5)
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
        problems.append(
            f"EOD bars not updated for {today} (latest {bar}) — the worker's EOD chain didn't run"
        )
    if trend != today:
        problems.append(f"'Active today' not updated for {today} (latest {trend})")
    return problems


async def _publish_freshness_problems(now: dt.datetime) -> list[str]:
    """Catches a stalled arq cron loop that #_eod_problems can't see: bars/trending come from
    ONE early job each (pull_eod_bars, run_trending) so a loop that stalls right after those two
    complete still looks "caught up" to that check, while everything scheduled later in the same
    window (signal agents, FB posts) silently never fires. Confirmed live 2026-07-06: the loop
    stalled ~30 min with the worker unit still "active" and no error logged, dropping
    run_trending/run_signals/pull_news/run_factor_signals between two jobs that ran fine."""
    today = to_market_tz(now).date()
    if not is_trading_day(today):
        return []
    problems: list[str] = []

    if now >= _utc_check_start(today, MORNING_WATCH_CHECK_FROM_UTC_HOUR):
        try:
            r = aioredis.from_url(get_settings().redis_url)
            posted = await r.get(f"fb:posted:morning_watch:{today}")
            await r.aclose()
        except Exception:
            log.warning("could not check morning_watch post key", exc_info=True)
        else:
            if not posted:
                problems.append(
                    f"Morning Watch hasn't posted for {today} "
                    f"(past {MORNING_WATCH_CHECK_FROM_UTC_HOUR:02d}:00 UTC)"
                )

    if EOD_CHECK_FROM_UTC_HOUR <= now.hour < EOD_CHECK_TO_UTC_HOUR:
        async with get_sessionmaker()() as session:
            # Volume notes run on their own separate intraday schedule (04:00-08:30 UTC), so they
            # don't prove the EOD-window agents (Levels/Factor/Ownership) actually ran today.
            count = (
                await session.execute(
                    text(
                        "select count(*) from signal_events "
                        "where created_at::date = :today and agent not like '%Volume%'"
                    ),
                    {"today": today},
                )
            ).scalar_one()
        if count == 0:
            problems.append(
                f"No Levels/Factor/Ownership signal notes fired for {today} — across 300+ "
                "liquid stocks that's implausibly quiet; the cron tick likely never ran"
            )
    return problems


async def _data_quality_problems() -> list[str]:
    """Independent, second-line check of the invariants the parsers are supposed to enforce
    (packages/market_data/providers/dse_scrape.py, lankabd.py) — catches the case where a NEW
    bug, a manual DB edit, or a backfill script bypasses those parsers and writes something
    impossible straight into the tables. Confirmed real incidents (2026-07-03): SALVOCHEM got 7
    fake all-zero OHLCV bars from a suspended-stock '0.00' render; CNATEX/APOLOISPAT both got a
    0/0/0/0/0 shareholding disclosure. Both classes are hard invariants — any count here should
    always be 0; a nonzero count means the ingestion boundary has a hole, not that the market did
    something unusual."""
    problems: list[str] = []
    async with get_sessionmaker()() as session:
        bad_bars = (
            await session.execute(
                text(
                    "select code, date from daily_bars "
                    "where high < low or close <= 0 or open <= 0 or high <= 0 or low <= 0 "
                    "order by date desc limit 5"
                )
            )
        ).all()
        if bad_bars:
            n = (
                await session.execute(
                    text(
                        "select count(*) from daily_bars "
                        "where high < low or close <= 0 or open <= 0 or high <= 0 or low <= 0"
                    )
                )
            ).scalar_one()
            sample = ", ".join(f"{c}:{d}" for c, d in bad_bars)
            problems.append(f"{n} impossible OHLC bar(s) in daily_bars — e.g. {sample}")

        bad_sh = (
            await session.execute(
                text(
                    "select code, as_of_date from shareholding_snapshots "
                    "where sponsor_director + coalesce(govt,0) + institute + foreign_pct + public "
                    "not between 90 and 110 "
                    "order by as_of_date desc limit 5"
                )
            )
        ).all()
        if bad_sh:
            sample = ", ".join(f"{c}:{d}" for c, d in bad_sh)
            problems.append(
                f"{len(bad_sh)}+ shareholding disclosure(s) not summing to ~100% — e.g. {sample}"
            )

        bad_div = (
            await session.execute(
                text("select count(*) from company_dividends where cash_pct < 0 or bonus_pct < 0")
            )
        ).scalar_one()
        if bad_div:
            problems.append(f"{bad_div} dividend record(s) with a negative percentage")

        bad_idx = (
            await session.execute(
                text("select count(*) from market_summary where dsex <= 0 or dsex > 20000")
            )
        ).scalar_one()
        if bad_idx:
            problems.append(f"{bad_idx} market_summary row(s) with an implausible DSEX level")

        # Soft signal, not a hard invariant: DSE's circuit bands cap a legitimate single-day
        # move well under 40%, but a corporate action (bonus/rights adjustment) can occasionally
        # produce a large gap our bars don't split-adjust for. Worth a human's eye, not a restart.
        big_moves = (
            await session.execute(
                text(
                    "select code, date, close, prev_close from ("
                    "  select code, date, close,"
                    "    lag(close) over (partition by code order by date) as prev_close"
                    "  from daily_bars where date >= current_date - interval '3 days'"
                    ") t where prev_close > 0 and abs(close / prev_close - 1) > 0.4 "
                    "limit 5"
                )
            )
        ).all()
        if big_moves:
            sample = ", ".join(f"{c} {p:.1f}->{cl:.1f}" for c, _d, cl, p in big_moves)
            problems.append(
                f"{len(big_moves)} stock(s) moved >40% day-over-day in the last 3 days "
                f"(check for a scrape error vs a real corporate action): {sample}"
            )
    return problems


async def _agent_problems(now: dt.datetime) -> list[str]:
    """Invariants of the agent model portfolios (services/ingestion/agent_trader.py). Every one
    of these is impossible if the engine is correct — a hit means an engine bug or a manual edit,
    so alert-only: a worker bounce can't fix wrong money numbers."""
    problems: list[str] = []
    today = to_market_tz(now).date()
    async with get_sessionmaker()() as session:
        # 1. Settled cash can never go negative: buys are capped by the budget check.
        neg = (
            await session.execute(
                text(
                    "select u.handle, a.cash_settled from agent_portfolios a "
                    "join users u on u.id = a.user_id where a.cash_settled < -0.01"
                )
            )
        ).all()
        for handle, cash in neg:
            problems.append(f"agent @{handle} has NEGATIVE settled cash ({cash:.2f})")

        # 2. A sell's proceeds must be credited the first engine tick on/after settles_on. Overdue
        #    means the engine skipped a full trading day (worker fault) or lost the trade.
        overdue = (
            await session.execute(
                text(
                    "select u.handle, t.code, t.settles_on from agent_trades t "
                    "join users u on u.id = t.user_id "
                    "where t.settled = false and t.settles_on < :today "
                    "order by t.settles_on limit 5"
                ),
                {"today": today},
            )
        ).all()
        if overdue:
            sample = ", ".join(f"@{h} {c} (due {d})" for h, c, d in overdue)
            problems.append(
                f"{len(overdue)}+ agent trade(s) past settlement but uncredited: {sample}"
            )

        # 3. The two books must agree: holding quantity == sum of open lot quantity, per code.
        drift = (
            await session.execute(
                text(
                    "select u.handle, coalesce(h.code, l.code) as code, "
                    "  coalesce(h.quantity, 0) as held, coalesce(l.left_qty, 0) as lots "
                    "from (select user_id, market, code, sum(quantity_left) as left_qty "
                    "      from agent_lots group by user_id, market, code) l "
                    "full outer join portfolio_holdings h "
                    "  on h.user_id = l.user_id and h.market = l.market and h.code = l.code "
                    "join agent_portfolios a on a.user_id = coalesce(h.user_id, l.user_id) "
                    "join users u on u.id = a.user_id "
                    "where coalesce(h.quantity, 0) <> coalesce(l.left_qty, 0) limit 5"
                )
            )
        ).all()
        if drift:
            sample = ", ".join(f"@{h} {c} holding={q} lots={lq}" for h, c, q, lq in drift)
            problems.append(f"agent holdings/lots books disagree: {sample}")

        # 4. Churn guard: 6 position slots mean ≤6 buys + ≤6 sells is the legitimate daily
        #    ceiling. More = the engine is trading every tick (rule hysteresis broken).
        churn = (
            await session.execute(
                text(
                    "select u.handle, count(*) from agent_trades t "
                    "join users u on u.id = t.user_id where t.trade_date = :today "
                    "group by u.handle having count(*) > 12"
                ),
                {"today": today},
            )
        ).all()
        for handle, n in churn:
            problems.append(f"agent @{handle} made {n} trades today — churn guard tripped")
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

    # EOD staleness: restart the worker. EOD jobs are run_at_startup and guarded by their own
    # "after close" checks, so this now recovers a missed chain instead of requiring a manual rerun.
    eod_problems = await _eod_problems(now)
    if eod_problems:
        problems += eod_problems
        worker_fault = True

    # Publish freshness: DO restart — unlike the EOD/bars check above, every job this covers
    # (Morning Watch, Levels/Factor/Ownership signals) now runs on worker startup too (see
    # worker.py), so a restart genuinely recovers the day's missed posts instead of being a
    # no-op. Same accepted tradeoff as the quote-staleness check above: if the cause turns out
    # not to be a stalled loop, this could restart every 5 min until fixed — the existing email
    # cooldown still pages only once an hour, so a stuck case is loud, not silent.
    try:
        freshness_problems = await _publish_freshness_problems(now)
    except Exception:
        freshness_problems = []
        log.exception("publish-freshness check failed")
    if freshness_problems:
        problems += freshness_problems
        worker_fault = True

    # Data-quality: alert only, never restart — a corrupted row isn't fixed by a worker bounce,
    # it needs the parser fixed and the bad row deleted (see docs on the 2026-07-03 incident).
    try:
        problems += await _data_quality_problems()
    except Exception:
        log.exception("data-quality check failed")

    # Agent portfolios: alert only — wrong money numbers need a human + a fix, not a restart.
    try:
        problems += await _agent_problems(now)
    except Exception:
        log.exception("agent-portfolio check failed")

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
        should_email = bool(
            await r.set(_COOLDOWN_KEY, now.isoformat(), nx=True, ex=COOLDOWN_SECONDS)
        )
        await r.aclose()
    except Exception:
        log.warning("redis cooldown unavailable — emailing anyway", exc_info=True)

    log.error("PROBLEMS: %s | actions: %s | emailed=%s", problems, actions, should_email)
    if should_email:
        await _send_alert(problems, actions)
    return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
