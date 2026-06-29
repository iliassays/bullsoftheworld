"""Onboard DSE news: classify each item, score its strength, keep the important, drop the noise.

Same date-range `collect(days)` shape as bars/market-summary — `backfill` pulls a long window once,
`daily` re-pulls a short window. Classification is deterministic keyword rules (no LLM): a controlled
category taxonomy + a 0-100 strength (materiality). Pure noise (spot notices, trading-code changes,
"no undisclosed info" clarifications) is dropped at onboarding; everything kept is tagged so the
agents and the News tab can filter and rank cheaply.

    uv run python -m ingestion.news backfill   # one-shot history
    uv run python -m ingestion.news daily       # re-pull the last few days
"""

from __future__ import annotations

import asyncio
import datetime as dt
import hashlib
import sys

from sqlalchemy.dialects.postgresql import insert as pg_insert

from bulls.core.db import get_sessionmaker
from bulls.core.models import Announcement
from bulls.market_data import get_provider

from ingestion.news_decode import decode

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
    "update of information",  # vague administrative re-posts, no material content
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


async def collect(market: str, *, days: int) -> dict[str, int]:
    """Pull `days` of news, classify + score, drop noise, upsert. Returns run stats."""
    provider = get_provider(market)
    end = dt.datetime.now(dt.UTC).date()
    start = end - dt.timedelta(days=days)
    items = await provider.get_news(start, end)

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
    async with get_sessionmaker()() as session:
        for k, g in groups.items():
            it, category = g["item"], g["category"]
            # main fragment (not a "(Cont." part) first, so the merged text reads in order
            ordered = sorted(g["bodies"], key=lambda b: b.strip().lower().startswith(("(cont", "(continuation")))
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
            stmt = pg_insert(Announcement).values(row).on_conflict_do_update(
                index_elements=["key"],
                set_={
                    "category": row["category"],
                    "strength": row["strength"],
                    "body": row["body"],
                    "details": row["details"],
                },
            )
            result = await session.execute(stmt)
            kept += result.rowcount or 0
        await session.commit()
    return {"fetched": len(items), "kept": kept}


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "daily"
    days = BACKFILL_DAYS if mode == "backfill" else DAILY_LOOKBACK_DAYS
    print(f"[news] {mode}: pulling ~{days}d of DSE news")
    stats = asyncio.run(collect("DSE", days=days))
    print(f"[news] done: {stats}")


if __name__ == "__main__":
    main()
