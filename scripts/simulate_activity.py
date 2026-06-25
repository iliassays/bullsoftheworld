"""Simulate organic crowd activity to make the system feel live and verify it end-to-end.

Drives the REAL API (register → post → reply → react → watch), so it exercises the whole chain:
cashtag parsing, the sentiment worker, reactions/replies, watchers, the buzz snapshot, and the
digest/screener. Stock picks are biased toward today's movers/active names so the chatter feels
topical, with a random long tail. Everything is randomized so it reads like real users.

    uv run python scripts/simulate_activity.py                 # one-shot burst (default)
    uv run python scripts/simulate_activity.py --posts 80      # bigger burst
    uv run python scripts/simulate_activity.py --live          # keep trickling at random intervals
    uv run python scripts/simulate_activity.py --clean         # remove all sim_ users + their data

Local dev only. Every simulated user has a 'sim_' handle prefix so --clean can remove them safely.
"""

from __future__ import annotations

import argparse
import asyncio
import random
import time

import httpx

PASSWORD = "password123"
HANDLE_PREFIX = "sim_"

_FIRST = [
    "rafiq",
    "sadia",
    "tanvir",
    "nabila",
    "imran",
    "mou",
    "arif",
    "shuvo",
    "priya",
    "jahid",
    "ritu",
    "fahim",
    "neha",
    "sohel",
    "tania",
    "rana",
]
_LAST = ["Ahmed", "Noor", "Islam", "Karim", "Hossain", "Rahman", "Akter", "Chowdhury", "Das"]

# Composed content pools — combinatorial so posts feel varied, not templated.
_EN = {
    "bull": [
        "{t} breaking out on volume",
        "loading up on {t} here",
        "{t} looks strong into the close",
        "{t} reclaimed support, constructive",
        "momentum building on {t}",
        "accumulating {t} slowly",
        "{t} setup looks clean",
        "buyers stepping in on {t}",
    ],
    "bear": [
        "{t} losing steam",
        "took profit on {t}",
        "{t} volume drying up, careful",
        "{t} broke support — watch the next level",
        "staying out of {t}, weak tape",
        "{t} bounce looks weak to me",
    ],
    "none": [
        "watching {t} for direction",
        "{t} range-bound, waiting",
        "anyone following {t}? thoughts?",
        "thin tape on {t} today",
        "{t} at an interesting spot here",
    ],
}
_BN = {
    "bull": [
        "{t} ভালো ভলিউমে উঠছে",
        "{t} ধীরে ধীরে জমাচ্ছি",
        "{t} শক্ত দেখাচ্ছে",
        "{t} সাপোর্ট রিক্লেইম করেছে",
        "{t} মোমেন্টাম বাড়ছে",
        "{t} তে ক্রেতা ঢুকছে",
    ],
    "bear": [
        "{t} গতি হারাচ্ছে",
        "{t} থেকে কিছু প্রফিট নিলাম",
        "{t} ভলিউম কমছে, সাবধান",
        "{t} সাপোর্ট ভেঙেছে",
        "{t} বাউন্স দুর্বল মনে হচ্ছে",
    ],
    "none": [
        "{t} দেখছি, দিকনির্দেশনার অপেক্ষায়",
        "{t} রেঞ্জে আটকে আছে",
        "{t} নিয়ে কারো মতামত আছে?",
        "{t} এখন আকর্ষণীয় জায়গায়",
    ],
}
_TAILS_EN = ["", "", "", " 🚀", " 👀", " #DSE", " — patience.", " volume is the tell."]
_TAILS_BN = ["", "", "", " 🚀", " 👀", " #DSE", " ধৈর্য রাখুন।", " ভলিউমই আসল।"]
_REPLY_EN = [
    "Agreed.",
    "Watching this too.",
    "Volume looks weak though.",
    "Any target in mind?",
    "Booked partial here.",
    "Nice call.",
    "Disagree — looks toppy.",
    "Thanks for sharing.",
]
_REPLY_BN = [
    "একমত।",
    "আমিও দেখছি।",
    "ভলিউম দুর্বল মনে হচ্ছে।",
    "টার্গেট কত?",
    "ভালো বলেছেন।",
    "একমত নই, উপরে ভারী।",
    "ধন্যবাদ।",
]


def _compose(lang: str, sentiment: str, codes: list[str]) -> str:
    pool = _BN if lang == "bn" else _EN
    tails = _TAILS_BN if lang == "bn" else _TAILS_EN
    tags = " ".join(f"${c}" for c in codes)
    body = random.choice(pool[sentiment]).format(t=f"${codes[0]}")
    # sometimes mention a second ticker inline
    if len(codes) > 1:
        body = body.replace(f"${codes[0]}", tags, 1)
    return body + random.choice(tails)


class Sim:
    def __init__(self, base: str):
        self.client = httpx.Client(base_url=base, timeout=15)
        self.users: list[dict] = []  # {handle, name, locale, token}
        self.posts: list[dict] = []  # {id, author, sentiment}

    # --- setup ---
    def ensure_users(self, n: int) -> None:
        for _ in range(n):
            first = random.choice(_FIRST)
            handle = f"{HANDLE_PREFIX}{first}{random.randint(100, 9999)}"
            name = f"{first.capitalize()} {random.choice(_LAST)}"
            locale = random.choice(["bn", "bn", "en"])  # Bangla-first community
            r = self.client.post(
                "/auth/register",
                json={"handle": handle, "name": name, "password": PASSWORD, "locale": locale},
            )
            if r.status_code != 201:
                r = self.client.post("/auth/login", json={"handle": handle, "password": PASSWORD})
                if r.status_code != 200:
                    continue
            self.users.append(
                {
                    "handle": handle,
                    "name": name,
                    "locale": locale,
                    "token": r.json()["access_token"],
                }
            )
        if not self.users:
            raise SystemExit(
                "could not create any sim users — is the API running on the given base?"
            )

    def _hdr(self, u: dict) -> dict:
        return {"Authorization": f"Bearer {u['token']}"}

    def candidate_pool(self) -> list[str]:
        """Weighted code pool: today's movers/active names heavier, a random long tail lighter."""
        all_codes = [s["code"] for s in self.client.get("/symbols?limit=500").json()]
        pool = list(all_codes)  # weight-1 tail
        try:
            quotes = self.client.get("/quotes").json()
            quotes.sort(key=lambda q: abs(q.get("change_pct") or 0), reverse=True)
            movers = [q["code"] for q in quotes[:25]]
            pool += movers * 5  # movers far more likely to be talked about
        except Exception:
            pass
        return pool or all_codes

    # --- actions ---
    def act_post(self, pool: list[str]) -> None:
        u = random.choice(self.users)
        codes = [random.choice(pool)]
        if random.random() < 0.2:
            codes.append(random.choice(pool))
        sentiment = random.choices(["bull", "bear", "none"], weights=[45, 30, 25])[0]
        body = _compose(u["locale"], sentiment, list(dict.fromkeys(codes)))
        payload = {"body": body}
        if sentiment != "none":
            payload["sentiment"] = sentiment
        r = self.client.post("/posts", json=payload, headers=self._hdr(u))
        if r.status_code == 201:
            p = r.json()
            self.posts.append({"id": p["id"], "author": u["handle"], "sentiment": sentiment})
            print(f"  post  @{u['handle']:18} {body[:60]}")

    def act_reply(self) -> None:
        if not self.posts:
            return self.act_post(self._pool)
        u = random.choice(self.users)
        parent = random.choice(self.posts[-20:])
        lang = u["locale"]
        body = random.choice(_REPLY_BN if lang == "bn" else _REPLY_EN)
        r = self.client.post(
            "/posts", json={"body": body, "parent_id": parent["id"]}, headers=self._hdr(u)
        )
        if r.status_code == 201:
            print(f"  reply @{u['handle']:18} ↳ #{parent['id']}: {body}")

    def act_react(self) -> None:
        if not self.posts:
            return self.act_post(self._pool)
        target = random.choice(self.posts[-25:])
        others = [u for u in self.users if u["handle"] != target["author"]]
        if not others:
            return
        u = random.choice(others)
        # agree more often than disagree, and lean with the post's stance
        kind = random.choices(["agree", "disagree"], weights=[72, 28])[0]
        r = self.client.post(
            f"/posts/{target['id']}/react", json={"kind": kind}, headers=self._hdr(u)
        )
        if r.status_code == 200:
            print(f"  react @{u['handle']:18} {kind} #{target['id']}")

    def act_watch(self, pool: list[str]) -> None:
        u = random.choice(self.users)
        code = random.choice(pool)
        self.client.post("/watchlist", json={"code": code}, headers=self._hdr(u))

    def tick(self) -> None:
        action = random.choices(["post", "reply", "react", "watch"], weights=[58, 16, 20, 6])[0]
        {
            "post": lambda: self.act_post(self._pool),
            "reply": self.act_reply,
            "react": self.act_react,
            "watch": lambda: self.act_watch(self._pool),
        }[action]()

    def run_burst(self, n: int) -> None:
        self._pool = self.candidate_pool()
        # front-load some posts so replies/reactions have something to land on
        for _ in range(min(8, n)):
            self.act_post(self._pool)
        for _ in range(n - min(8, n)):
            self.tick()
        print(f"\nburst done: {len(self.posts)} posts created by {len(self.users)} sim users")

    def run_live(self) -> None:
        self._pool = self.candidate_pool()
        print("live mode — Ctrl-C to stop")
        while True:
            self.tick()
            time.sleep(random.uniform(2, 18))


async def clean() -> None:
    """Remove every sim_ user and all data they produced (FK-safe order)."""
    from sqlalchemy import delete, select

    from bulls.core.db import get_sessionmaker
    from bulls.core.models import Cashtag, Post, PostReaction, User, WatchlistItem

    sm = get_sessionmaker()
    async with sm() as s:
        ids = list(await s.scalars(select(User.id).where(User.handle.like(f"{HANDLE_PREFIX}%"))))
        if not ids:
            print("no sim_ users to clean")
            return
        post_ids = list(await s.scalars(select(Post.id).where(Post.author_id.in_(ids))))
        # reactions: by sim users OR on sim posts
        await s.execute(delete(PostReaction).where(PostReaction.user_id.in_(ids)))
        if post_ids:
            await s.execute(delete(PostReaction).where(PostReaction.post_id.in_(post_ids)))
            await s.execute(delete(Cashtag).where(Cashtag.post_id.in_(post_ids)))
        await s.execute(delete(WatchlistItem).where(WatchlistItem.user_id.in_(ids)))
        # replies before roots (self-referential parent_id FK)
        await s.execute(delete(Post).where(Post.author_id.in_(ids), Post.parent_id.isnot(None)))
        await s.execute(delete(Post).where(Post.author_id.in_(ids)))
        await s.execute(delete(User).where(User.id.in_(ids)))
        await s.commit()
        print(f"cleaned {len(ids)} sim users and their posts/reactions/watchlist")


def main() -> None:
    ap = argparse.ArgumentParser(description="Simulate organic crowd activity via the API.")
    ap.add_argument("--api", default="http://localhost:8090", help="API base URL")
    ap.add_argument("--users", type=int, default=10)
    ap.add_argument("--posts", type=int, default=45, help="actions in a burst")
    ap.add_argument("--live", action="store_true", help="keep trickling instead of one burst")
    ap.add_argument(
        "--clean", action="store_true", help="remove sim_ users + their data, then exit"
    )
    args = ap.parse_args()

    if args.clean:
        asyncio.run(clean())
        return

    sim = Sim(args.api)
    sim.ensure_users(args.users)
    print(f"{len(sim.users)} sim users ready\n")
    if args.live:
        sim.run_live()
    else:
        sim.run_burst(args.posts)


if __name__ == "__main__":
    main()
