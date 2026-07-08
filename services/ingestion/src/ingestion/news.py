"""Onboard DSE news: classify each item, score its strength, keep the important, drop the noise.

Same date-range `collect(days)` shape as bars/market-summary — `backfill` pulls a long window once,
`daily` re-pulls a short window. Classification is deterministic keyword rules (no LLM): a controlled
category taxonomy + a 0-100 strength (materiality). Pure noise (spot notices, trading-code changes,
"no undisclosed info" clarifications) is dropped at onboarding; everything kept is tagged so the
agents and the News tab can filter and rank cheaply.

    uv run python -m ingestion.news backfill   # one-shot history
    uv run python -m ingestion.news daily       # re-pull the last few days
    uv run python -m ingestion.news retag       # re-apply rules to stored rows (no re-scrape)
"""

from __future__ import annotations

import asyncio
import datetime as dt
import hashlib
import logging
import sys

from arq import create_pool
from arq.connections import RedisSettings
from sqlalchemy.dialects.postgresql import insert as pg_insert

from bulls.core.config import get_settings
from bulls.core.db import get_sessionmaker
from bulls.core.models import Announcement
from bulls.market_data import get_provider
from ingestion.news_decode import decode

log = logging.getLogger(__name__)

BACKFILL_DAYS = 760
DAILY_LOOKBACK_DAYS = 3  # news is time-sensitive; a short re-pull catches late postings

# Known pure-noise phrases — dropped at onboarding.
_NOISE = (
    "spot ",
    "trading code",
    "category change",
    "no price sensitive",
    "no undisclosed",
    "clarification",
    "trade resumption",
    "block transaction",
    "odd lot",
    "renaming",
    "daily nav",  # mutual funds post a NAV every single day — routine, buries real news
    "weekly nav",  # ...and a weekly one — same routine noise as the daily NAV
    "update of information",  # vague administrative re-posts, no material content
    "awareness",  # "DSE/BSEC NEWS: Awareness Message for Investors" — regulator boilerplate
    "daily turnover",  # "DSE NEWS: Daily Turnover of Main Board" — routine market stat
    "greetings",  # "Greetings Message" / "Eid Greetings" — courtesy notices, not company news
    "authorized representative",  # withdrawal/appointment of a TREC holder's AR — administrative
    "ccam",  # "Lodging Investor Complaints through CCAM" — standing regulatory notice
)
# Ordered (first match wins). board_meeting before dividend/earnings so "board meeting to consider
# dividend" reads as a heads-up, not the declaration itself.
_RULES: list[tuple[tuple[str, ...], str]] = [
    (("board meeting", "board of directors"), "board_meeting"),
    (("credit rating", "rating of", "entity rating"), "rating"),
    # Director/sponsor dealing in their own shares — a smart-money signal worth surfacing.
    (("buy confirmation", "sale confirmation", "sell confirmation", "intention to"), "insider"),
    (("dividend",), "dividend"),
    (
        (
            "half yearly",
            "quarterly",
            "annual report",
            "eps",
            "financial statement",
            "financials",
            "un-audited",
            "unaudited",
            "audited accounts",
            "earnings",
            "net profit",
        ),
        "earnings",
    ),
    (("suspension", "resume", "halt", "trading suspend"), "halt"),
    (("agm", "egm", "record date", "book closure", "book close"), "corporate_action"),
    (("price sensitive", "psi"), "psi"),
]

_BASE_STRENGTH = {
    "halt": 75,
    "dividend": 70,
    "earnings": 65,
    "rating": 60,
    "insider": 55,
    "psi": 50,
    "board_meeting": 40,
    "corporate_action": 35,
    "other": 20,
}


def classify(headline: str) -> str:
    """Map a headline to a controlled category; 'noise' = drop, else keep + tag."""
    h = headline.lower()
    if any(n in h for n in _NOISE):
        return "noise"
    for subs, category in _RULES:
        if any(s in h for s in subs):
            return category
    return "other"


def strength(category: str, headline: str) -> int:
    """0-100 materiality. Base by category, nudged by magnitude cues in the headline."""
    h = headline.lower()
    s = _BASE_STRENGTH.get(category, 20)
    if category == "rating":
        s += 25 if "downgrade" in h else 10 if "upgrade" in h else 0
    if category == "earnings" and ("loss" in h or "default" in h):
        s += 15
    if category == "dividend" and ("interim" in h or "special" in h):
        s += 10
    return max(0, min(100, s))


def _key(code: str, day: dt.date, headline: str) -> str:
    return hashlib.sha1(f"{code}|{day}|{headline}".encode()).hexdigest()[:40]


async def _enqueue_embeddings(announcement_ids: list[int]) -> None:
    if not announcement_ids:
        return
    try:
        pool = await create_pool(RedisSettings.from_dsn(get_settings().redis_url))
        try:
            for announcement_id in announcement_ids:
                await pool.enqueue_job("embed_announcement", announcement_id)
        finally:
            await pool.aclose()
    except Exception as e:
        log.warning("announcement embedding enqueue failed for %s rows: %s", len(announcement_ids), e)


async def _ingest(market: str, items: list) -> int:
    """Classify + score + decode a batch of raw NewsItems, drop noise, upsert. Returns rows kept."""
    # DSE splits long announcements across rows that repeat the same title ("(Cont. news of X)").
    # They share an identity key, so group them and decode the bodies together — otherwise a
    # continuation fragment overwrites the real declaration and the numbers/dates are lost.
    groups: dict[str, dict] = {}
    for it in items:
        category = classify(it.headline)
        if category == "noise":
            continue
        k = _key(it.code, it.published_at, it.headline)
        g = groups.setdefault(k, {"item": it, "category": category, "bodies": []})
        if it.body:
            g["bodies"].append(it.body)

    kept = 0
    announcement_ids: list[int] = []
    async with get_sessionmaker()() as session:
        for k, g in groups.items():
            it, category = g["item"], g["category"]
            # main fragment (not a "(Cont." part) first, so the merged text reads in order
            ordered = sorted(
                g["bodies"], key=lambda b: b.strip().lower().startswith(("(cont", "(continuation"))
            )
            body = "\n".join(ordered)
            row = {
                "market": market,
                "code": it.code,
                "published_at": it.published_at,
                "category": category,
                "strength": strength(category, it.headline),
                "headline": it.headline,
                "body": body or None,
                "details": decode(category, it.headline, body) or None,
                "key": k,
            }
            # On re-run, refresh the derived columns so improved classification / decoding flows to
            # rows we already have (identity is the content hash, so this is idempotent).
            stmt = (
                pg_insert(Announcement)
                .values(row)
                .returning(Announcement.id)
                .on_conflict_do_update(
                    index_elements=["key"],
                    set_={
                        "category": row["category"],
                        "strength": row["strength"],
                        "body": row["body"],
                        "details": row["details"],
                    },
                )
            )
            result = await session.execute(stmt)
            announcement_id = result.scalar_one_or_none()
            if announcement_id is not None:
                announcement_ids.append(announcement_id)
            kept += result.rowcount or 0
        await session.commit()
    await _enqueue_embeddings(announcement_ids)
    return kept


async def collect(market: str, *, days: int) -> dict[str, int]:
    """Pull `days` of *recent* news (load-news.php), classify + score, drop noise, upsert."""
    provider = get_provider(market)
    end = dt.datetime.now(dt.UTC).date()
    start = end - dt.timedelta(days=days)
    items = await provider.get_news(start, end)
    kept = await _ingest(market, items)
    return {"fetched": len(items), "kept": kept}


def _month_windows(start: dt.date, end: dt.date):
    """Yield (window_start, window_end) covering [start, end], one calendar month at a time."""
    cur = start
    while cur <= end:
        nxt = (cur.replace(day=1) + dt.timedelta(days=32)).replace(day=1)
        yield cur, min(end, nxt - dt.timedelta(days=1))
        cur = nxt


async def backfill_range(market: str, *, days: int) -> dict[str, int]:
    """One-shot history from the archive (old_news.php), chunked by month so no single request is
    huge. Upserts per month, so a mid-run failure still keeps the months already pulled."""
    provider = get_provider(market)
    get_archive = getattr(provider, "get_news_archive", provider.get_news)
    end = dt.datetime.now(dt.UTC).date()
    start = end - dt.timedelta(days=days)
    total_fetched = total_kept = 0
    for w_start, w_end in _month_windows(start, end):
        items = await get_archive(w_start, w_end)
        kept = await _ingest(market, items)
        total_fetched += len(items)
        total_kept += kept
        print(f"[news]   {w_start}..{w_end}: fetched {len(items)}, kept {kept}", flush=True)
    return {"fetched": total_fetched, "kept": total_kept}


async def retag(market: str) -> dict[str, int]:
    """Re-classify + re-decode every stored announcement from its saved headline/body — applies
    improved rules without re-scraping DSE. Rows that are now noise are dropped."""
    from sqlalchemy import select

    updated = dropped = 0
    async with get_sessionmaker()() as session:
        rows = (
            await session.scalars(select(Announcement).where(Announcement.market == market))
        ).all()
        for a in rows:
            category = classify(a.headline)
            if category == "noise":
                await session.delete(a)
                dropped += 1
                continue
            a.category = category
            a.strength = strength(category, a.headline)
            a.details = decode(category, a.headline, a.body or "") or None
            updated += 1
        await session.commit()
    return {"updated": updated, "dropped": dropped}


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "daily"
    if mode == "backfill":
        print(f"[news] backfill: pulling ~{BACKFILL_DAYS}d of DSE news from the archive (monthly)")
        stats = asyncio.run(backfill_range("DSE", days=BACKFILL_DAYS))
    elif mode == "retag":
        print("[news] retag: re-classifying + re-decoding stored announcements (no re-scrape)")
        stats = asyncio.run(retag("DSE"))
    else:
        print(f"[news] daily: pulling ~{DAILY_LOOKBACK_DAYS}d of recent DSE news")
        stats = asyncio.run(collect("DSE", days=DAILY_LOOKBACK_DAYS))
    print(f"[news] done: {stats}")


if __name__ == "__main__":
    main()
