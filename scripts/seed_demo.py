"""Seed demo users + posts so the feed has life. Idempotent: re-running replaces demo content.

    uv run python scripts/seed_demo.py

Only touches DEMO users (handles below) and their posts — your own UI-created posts are left alone.
All demo users share the password 'password123' so you can log in as them.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import re

from sqlalchemy import delete, select

from bulls.core.db import get_sessionmaker
from bulls.core.models import Cashtag, Post, Symbol, User, WatchlistItem
from bulls.core.security import hash_password

TENANT = "bullsofdhaka"
MARKET = "DSE"
PASSWORD = "password123"
CASHTAG_RE = re.compile(r"\$([A-Z0-9]{2,16})")

DEMO_USERS = [
    ("rafiq", "Rafiq Ahmed", "bn"),
    ("sadia", "Sadia Noor", "bn"),
    ("tanvir", "Tanvir Islam", "en"),
    ("nabila", "Nabila Karim", "bn"),
]

# (author_handle, body, sentiment) — newest last; we stagger timestamps.
DEMO_POSTS = [
    ("rafiq", "$GP breaking out on heavy volume — telecom looking strong into earnings. Watching the next level up. 🚀", "bull"),
    ("sadia", "$BEXIMCO আজ ভলিউম কমে যাচ্ছে, সাপোর্ট ভাঙলে আরও নামতে পারে। সাবধানে থাকুন। #DSE", "bear"),
    ("tanvir", "Crowd's turning bullish on $ROBI — the subscriber growth story is still intact.", "bull"),
    ("nabila", "$SQURPHARMA রিটেইল ইনভেস্টরদের পছন্দের শেয়ার, ডিভিডেন্ড রেকর্ড ভালো। লং টার্মে রাখার মতো।", "bull"),
    ("rafiq", "Took some profit on $WALTONHIL — momentum fading on the daily chart.", "bear"),
    ("tanvir", "Thin tape today. Watching $GP and $BRACBANK for direction before adding.", None),
    ("sadia", "$BATBC এখন আকর্ষণীয় দামে, ফান্ডামেন্টাল মজবুত। ধীরে ধীরে জমাচ্ছি।", "bull"),
    ("nabila", "$BRACBANK looks like it's basing out near support. Accumulating slowly.", "bull"),
    ("rafiq", "Sector rotation into pharma — $SQURPHARMA and $RENATA both catching a bid.", "bull"),
    ("tanvir", "$BEXIMCO bounce looks weak to me. Needs volume to confirm. Staying out.", "bear"),
]

DEMO_WATCHLIST = {"rafiq": ["GP", "BEXIMCO", "SQURPHARMA"]}


def parse_cashtags(body: str) -> list[str]:
    return list(dict.fromkeys(CASHTAG_RE.findall(body.upper())))


async def main() -> None:
    sm = get_sessionmaker()
    async with sm() as s:
        # upsert demo users
        users: dict[str, User] = {}
        for handle, name, locale in DEMO_USERS:
            user = await s.scalar(select(User).where(User.handle == handle))
            if user is None:
                user = User(
                    tenant_id=TENANT,
                    handle=handle,
                    name=name,
                    password_hash=hash_password(PASSWORD),
                    locale=locale,
                )
                s.add(user)
                await s.flush()
            users[handle] = user

        demo_ids = [u.id for u in users.values()]

        # clear previous demo content (posts, their cashtags, watchlists)
        old_posts = list(await s.scalars(select(Post.id).where(Post.author_id.in_(demo_ids))))
        if old_posts:
            await s.execute(delete(Cashtag).where(Cashtag.post_id.in_(old_posts)))
            await s.execute(delete(Post).where(Post.id.in_(old_posts)))
        await s.execute(delete(WatchlistItem).where(WatchlistItem.user_id.in_(demo_ids)))

        # which referenced symbols actually exist (so cashtags/watchlist link to real DSE codes)
        referenced = {c for _, body, _ in DEMO_POSTS for c in parse_cashtags(body)}
        referenced |= {c for codes in DEMO_WATCHLIST.values() for c in codes}
        valid = set(
            await s.scalars(
                select(Symbol.code).where(Symbol.market == MARKET, Symbol.code.in_(referenced))
            )
        )

        now = dt.datetime.now(dt.UTC)
        n_tags = 0
        for i, (handle, body, sentiment) in enumerate(DEMO_POSTS):
            created = now - dt.timedelta(minutes=7 * (len(DEMO_POSTS) - i))
            post = Post(
                tenant_id=TENANT,
                author_id=users[handle].id,
                body=body,
                sentiment=sentiment,
                created_at=created,
            )
            s.add(post)
            await s.flush()
            for code in parse_cashtags(body):
                if code in valid:
                    s.add(Cashtag(post_id=post.id, market=MARKET, code=code))
                    n_tags += 1

        for handle, codes in DEMO_WATCHLIST.items():
            for code in codes:
                if code in valid:
                    s.add(WatchlistItem(user_id=users[handle].id, market=MARKET, code=code))

        await s.commit()
        print(
            f"Seeded {len(DEMO_USERS)} users, {len(DEMO_POSTS)} posts, {n_tags} cashtags. "
            f"Login as any of: {', '.join(h for h, _, _ in DEMO_USERS)} / password '{PASSWORD}'"
        )


if __name__ == "__main__":
    asyncio.run(main())
