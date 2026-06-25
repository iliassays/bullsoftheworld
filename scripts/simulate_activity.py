"""Simulate organic crowd activity to make the system feel live and verify it end-to-end.

Drives the REAL API (register → post → reply → react → watch), so it exercises the whole chain:
cashtag parsing, the sentiment worker, reactions/replies, watchers, the buzz snapshot, and the
digest/screener.

This is modelled on how a real community behaves, not flat randomness:
  - Personas: a few heavy posters + many lurkers (power-law); each has a fixed language, a couple
    of favourite tickers, and a bull/bear temperament — so they keep posting about THEIR stocks in
    THEIR voice.
  - Price-coherent: sentiment tracks the stock's real move (bullish on gainers), posts reference
    the actual % change, and movers attract disproportionately more chatter.
  - Market rhythm (live mode): bursts around the open/close, slow midday, near-silent overnight
    and weekends — on the Dhaka clock.
  - Coherent threads: replies answer the parent's stance; reactions pile onto posts that already
    have traction (rich-get-richer).

    uv run python scripts/simulate_activity.py                 # one-shot burst (default)
    uv run python scripts/simulate_activity.py --posts 80      # bigger burst
    uv run python scripts/simulate_activity.py --live          # keep trickling on the market clock
    uv run python scripts/simulate_activity.py --clean         # remove all sim_ users + their data

Local dev only. Every simulated user has a 'sim_' handle prefix so --clean can remove them safely.
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import random
import time

import httpx

from bulls.market_data.calendar import Session, session_phase

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
    "asif",
    "lima",
    "kabir",
    "mita",
]
_LAST = ["Ahmed", "Noor", "Islam", "Karim", "Hossain", "Rahman", "Akter", "Chowdhury", "Das"]

_EN = {
    "bull": [
        "{t} breaking out on volume",
        "loading up on {t}",
        "{t} looks strong here",
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
        "{t} broke support, watch the next level",
        "staying out of {t}, weak tape",
        "{t} bounce looks weak to me",
    ],
    "none": [
        "watching {t} for direction",
        "{t} range-bound, waiting",
        "anyone following {t}? thoughts?",
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
    "none": ["{t} দেখছি, দিকনির্দেশনার অপেক্ষায়", "{t} রেঞ্জে আটকে আছে", "{t} নিয়ে কারো মতামত আছে?"],
}
_EXTRA_EN = [
    "fundamentals still intact",
    "watching the daily close",
    "not financial advice ofc",
    "long-term hold for me",
    "let's see if it holds",
]
_EXTRA_BN = ["ফান্ডামেন্টাল এখনো মজবুত", "দিন শেষের ক্লোজ দেখছি", "লং টার্মে রাখছি", "দেখা যাক টেকে কিনা"]
_TAILS = ["", "", "", "", " 🚀", " 👀", " #DSE", " 📈"]
_AGREE_EN = [
    "Agreed.",
    "Same view here.",
    "Watching this too.",
    "Nice call.",
    "On my list as well.",
]
_AGREE_BN = ["একমত।", "আমিও দেখছি।", "ভালো বলেছেন।", "আমার লিস্টেও আছে।"]
_COUNTER_EN = [
    "Not so sure — volume looks weak.",
    "Disagree, looks toppy.",
    "Any target?",
    "I'd wait for a daily close above.",
    "Careful here.",
]
_COUNTER_BN = ["একমত নই, উপরে ভারী।", "ভলিউম দুর্বল মনে হচ্ছে।", "টার্গেট কত?", "সাবধানে থাকুন।"]

# Live cadence by market phase (base seconds between actions; jittered + clustered).
_PHASE_SECS = {Session.OPEN: 9, Session.PRE_OPEN: 25, Session.POST_CLOSE: 40, Session.WEEKEND: 200}


def _move_phrase(lang: str, chg: float) -> str:
    if lang == "bn":
        return f"আজ {abs(chg):.1f}% {'উপরে' if chg >= 0 else 'নিচে'}"
    return f"{'up' if chg >= 0 else 'down'} {abs(chg):.1f}% today"


def _sentiment_for(chg: float | None, lean: float) -> str:
    score = lean + (chg or 0) / 3  # +ve leans bullish
    if score > 0.6:
        weights = {"bull": 70, "none": 20, "bear": 10}
    elif score < -0.6:
        weights = {"bull": 10, "none": 20, "bear": 70}
    else:
        weights = {"bull": 40, "bear": 30, "none": 30}
    return random.choices(list(weights), weights=list(weights.values()))[0]


class Sim:
    def __init__(self, base: str):
        self.client = httpx.Client(base_url=base, timeout=15)
        self.users: list[dict] = []
        self.posts: list[dict] = []  # {id, author, sentiment, score}
        self.mkt: dict[str, float] = {}  # code -> change_pct
        self.movers: list[str] = []
        self.fav_pool: list[str] = []

    # --- market context ---
    def load_market(self) -> None:
        codes = [s["code"] for s in self.client.get("/symbols?limit=500").json()]
        try:
            quotes = self.client.get("/quotes").json()
            self.mkt = {q["code"]: (q.get("change_pct") or 0.0) for q in quotes}
            self.movers = sorted(self.mkt, key=lambda c: abs(self.mkt[c]), reverse=True)
        except Exception:
            self.movers = []
        active = self.movers[:60] or codes
        self.fav_pool = active + random.sample(codes, min(40, len(codes)))

    # --- personas ---
    def ensure_users(self, n: int) -> None:
        for _ in range(n):
            first = random.choice(_FIRST)
            handle = f"{HANDLE_PREFIX}{first}{random.randint(100, 9999)}"
            locale = random.choice(["bn", "bn", "bn", "en"])  # Bangla-first
            r = self.client.post(
                "/auth/register",
                json={
                    "handle": handle,
                    "name": f"{first.capitalize()} {random.choice(_LAST)}",
                    "password": PASSWORD,
                    "locale": locale,
                },
            )
            if r.status_code != 201:
                r = self.client.post("/auth/login", json={"handle": handle, "password": PASSWORD})
                if r.status_code != 200:
                    continue
            self.users.append(
                {
                    "handle": handle,
                    "locale": locale,
                    "token": r.json()["access_token"],
                    "weight": round(random.paretovariate(1.3), 2),  # power-law: a few heavy posters
                    "favorites": random.sample(
                        self.fav_pool, k=min(random.randint(1, 3), len(self.fav_pool))
                    ),
                    "lean": round(random.uniform(-0.5, 0.8), 2),  # retail skews mildly bullish
                    "verbose": random.random() < 0.3,
                }
            )
        if not self.users:
            raise SystemExit("could not create sim users — is the API running on the given base?")

    def _hdr(self, u: dict) -> dict:
        return {"Authorization": f"Bearer {u['token']}"}

    def _actor(self) -> dict:
        return random.choices(self.users, weights=[u["weight"] for u in self.users])[0]

    def _pick_stock(self, u: dict) -> str:
        if u["favorites"] and random.random() < 0.7:
            return random.choice(u["favorites"])
        if self.movers and random.random() < 0.8:
            top = self.movers[:40]
            return random.choices(top, weights=[abs(self.mkt[c]) + 0.1 for c in top])[0]
        return random.choice(self.fav_pool)

    # --- actions ---
    def _compose(self, u: dict, code: str, sentiment: str) -> str:
        lang = u["locale"]
        pools = _BN if lang == "bn" else _EN
        body = random.choice(pools[sentiment]).format(t=f"${code}")
        chg = self.mkt.get(code)
        if chg is not None and abs(chg) >= 0.3 and random.random() < 0.5:
            body += f" — {_move_phrase(lang, chg)}"
        if u["verbose"] and random.random() < 0.6:
            body += ("। " if lang == "bn" else ". ") + random.choice(
                _EXTRA_BN if lang == "bn" else _EXTRA_EN
            )

        return body + random.choice(_TAILS)

    def act_post(self) -> None:
        u = self._actor()
        code = self._pick_stock(u)
        sentiment = _sentiment_for(self.mkt.get(code), u["lean"])
        payload = {"body": self._compose(u, code, sentiment)}
        if sentiment != "none":
            payload["sentiment"] = sentiment
        r = self.client.post("/posts", json=payload, headers=self._hdr(u))
        if r.status_code == 201:
            self.posts.append(
                {"id": r.json()["id"], "author": u["handle"], "sentiment": sentiment, "score": 0}
            )
            print(f"  post  @{u['handle']:18} {payload['body'][:60]}")

    def act_reply(self) -> None:
        if not self.posts:
            return self.act_post()
        u = self._actor()
        # prefer recent posts with some traction (a real thread draws more replies)
        pool = self.posts[-25:]
        parent = random.choices(pool, weights=[p["score"] + 1 for p in pool])[0]
        aligned = (u["lean"] >= 0) == (parent["sentiment"] != "bear")
        bank = (
            (_AGREE_BN if u["locale"] == "bn" else _AGREE_EN)
            if aligned
            else (_COUNTER_BN if u["locale"] == "bn" else _COUNTER_EN)
        )
        r = self.client.post(
            "/posts",
            json={"body": random.choice(bank), "parent_id": parent["id"]},
            headers=self._hdr(u),
        )
        if r.status_code == 201:
            parent["score"] += 1
            print(f"  reply @{u['handle']:18} ↳ #{parent['id']}")

    def act_react(self) -> None:
        if not self.posts:
            return self.act_post()
        pool = [p for p in self.posts[-30:]]
        # rich-get-richer: posts with traction attract more reactions
        target = random.choices(pool, weights=[p["score"] + 1 for p in pool])[0]
        others = [u for u in self.users if u["handle"] != target["author"]]
        if not others:
            return
        u = self._actor() if random.random() < 0.7 else random.choice(others)
        if u["handle"] == target["author"]:
            return
        aligned = (u["lean"] >= 0) == (target["sentiment"] != "bear")
        kind = "agree" if (aligned or random.random() < 0.5) else "disagree"
        r = self.client.post(
            f"/posts/{target['id']}/react", json={"kind": kind}, headers=self._hdr(u)
        )
        if r.status_code == 200:
            target["score"] += 1
            print(f"  react @{u['handle']:18} {kind} #{target['id']}")

    def act_watch(self) -> None:
        u = self._actor()
        code = random.choice(u["favorites"]) if u["favorites"] else self._pick_stock(u)
        self.client.post("/watchlist", json={"code": code}, headers=self._hdr(u))

    def tick(self) -> None:
        action = random.choices(["post", "reply", "react", "watch"], weights=[52, 18, 24, 6])[0]
        {
            "post": self.act_post,
            "reply": self.act_reply,
            "react": self.act_react,
            "watch": self.act_watch,
        }[action]()

    def run_burst(self, n: int) -> None:
        for _ in range(min(8, n)):
            self.act_post()
        for _ in range(max(0, n - 8)):
            self.tick()
        print(f"\nburst done: {len(self.posts)} posts by {len(self.users)} sim users")

    def run_live(self) -> None:
        print("live mode (market-clock paced) — Ctrl-C to stop")
        acted = 0
        while True:
            self.tick()
            acted += 1
            if acted % 30 == 0:
                self.load_market()  # refresh moves periodically
            base = _PHASE_SECS.get(session_phase(dt.datetime.now(dt.UTC)), 60)
            # cluster: sometimes a quick flurry, otherwise a phase-appropriate gap
            gap = (
                random.uniform(1, 3)
                if random.random() < 0.3
                else random.uniform(base * 0.5, base * 1.7)
            )
            time.sleep(gap)


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
        await s.execute(delete(PostReaction).where(PostReaction.user_id.in_(ids)))
        if post_ids:
            await s.execute(delete(PostReaction).where(PostReaction.post_id.in_(post_ids)))
            await s.execute(delete(Cashtag).where(Cashtag.post_id.in_(post_ids)))
        await s.execute(delete(WatchlistItem).where(WatchlistItem.user_id.in_(ids)))
        await s.execute(delete(Post).where(Post.author_id.in_(ids), Post.parent_id.isnot(None)))
        await s.execute(delete(Post).where(Post.author_id.in_(ids)))
        await s.execute(delete(User).where(User.id.in_(ids)))
        await s.commit()
        print(f"cleaned {len(ids)} sim users and their posts/reactions/watchlist")


def main() -> None:
    ap = argparse.ArgumentParser(description="Simulate realistic crowd activity via the API.")
    ap.add_argument("--api", default="http://localhost:8090")
    ap.add_argument("--users", type=int, default=14)
    ap.add_argument("--posts", type=int, default=45, help="actions in a burst")
    ap.add_argument("--live", action="store_true", help="keep trickling on the market clock")
    ap.add_argument("--clean", action="store_true", help="remove sim_ users + data, then exit")
    args = ap.parse_args()

    if args.clean:
        asyncio.run(clean())
        return

    sim = Sim(args.api)
    sim.load_market()
    sim.ensure_users(args.users)
    print(f"{len(sim.users)} sim personas ready\n")
    sim.run_live() if args.live else sim.run_burst(args.posts)


if __name__ == "__main__":
    main()
