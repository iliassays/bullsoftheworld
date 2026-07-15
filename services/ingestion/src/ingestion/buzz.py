"""Snapshot each symbol's daily social attention (posts / reactions / replies / watchers).

Runs after the EOD close (in the worker), building the history the /buzz endpoint reads to compute
trends. Counts cover the trailing 24h at run time and are stamped with the current Dhaka date.
Only symbols with activity OR watchers get a row, so the table stays lean.

One-shot (cron-friendly / backfill now):
    uv run python -m ingestion.buzz DSE
"""

from __future__ import annotations

import asyncio
import datetime as dt
import sys

from sqlalchemy import String, cast, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from bulls.core.db import bind_tenant_context, get_sessionmaker
from bulls.core.models import (
    Cashtag,
    PageViewEvent,
    Post,
    PostReaction,
    TickerBuzzDaily,
    User,
    WatchlistItem,
)
from bulls.market_data.calendar import to_market_tz

WINDOW = dt.timedelta(hours=24)


async def snapshot_all(market: str, *, tenant_id: str) -> dict[str, int]:
    """Compute + upsert today's buzz row for every symbol with activity or watchers."""
    now = dt.datetime.now(dt.UTC)
    since = now - WINDOW
    day = to_market_tz(now, market=market).date()
    sm = get_sessionmaker()

    async with sm() as session:
        await bind_tenant_context(session, tenant_id)
        # posts tagging each code in the window (roots + tagged replies)
        posts = dict(
            (
                await session.execute(
                    select(Cashtag.code, func.count(func.distinct(Post.id)))
                    .join(Post, Cashtag.post_id == Post.id)
                    .where(
                        Cashtag.market == market,
                        Post.tenant_id == tenant_id,
                        Post.created_at >= since,
                        Post.moderation_status == "published",
                    )
                    .group_by(Cashtag.code)
                )
            ).all()
        )
        reactions = dict(
            (
                await session.execute(
                    select(Cashtag.code, func.count())
                    .join(PostReaction, Cashtag.post_id == PostReaction.post_id)
                    .join(Post, Post.id == PostReaction.post_id)
                    .where(
                        Cashtag.market == market,
                        Post.tenant_id == tenant_id,
                        PostReaction.created_at >= since,
                        Post.moderation_status == "published",
                    )
                    .group_by(Cashtag.code)
                )
            ).all()
        )
        replies = dict(
            (
                await session.execute(
                    select(Cashtag.code, func.count(func.distinct(Post.id)))
                    .join(Post, Cashtag.post_id == Post.id)
                    .where(
                        Cashtag.market == market,
                        Post.tenant_id == tenant_id,
                        Post.parent_id.is_not(None),
                        Post.created_at >= since,
                    )
                    .group_by(Cashtag.code)
                )
            ).all()
        )
        watchers = dict(
            (
                await session.execute(
                    select(WatchlistItem.code, func.count())
                    .join(User, User.id == WatchlistItem.user_id)
                    .where(
                        WatchlistItem.market == market,
                        User.tenant_id == tenant_id,
                    )
                    .group_by(WatchlistItem.code)
                )
            ).all()
        )
        # unique viewers in the window — distinct logged-in user or anon session (internal only)
        viewer_key = func.coalesce(cast(PageViewEvent.user_id, String), PageViewEvent.session_hash)
        viewers = dict(
            (
                await session.execute(
                    select(PageViewEvent.code, func.count(func.distinct(viewer_key)))
                    .where(
                        PageViewEvent.tenant_id == tenant_id,
                        PageViewEvent.market == market,
                        PageViewEvent.created_at >= since,
                    )
                    .group_by(PageViewEvent.code)
                )
            ).all()
        )

        codes = set(posts) | set(reactions) | set(replies) | set(watchers) | set(viewers)
        for code in codes:
            row = {
                "tenant_id": tenant_id,
                "market": market,
                "code": code,
                "date": day,
                "posts_24h": posts.get(code, 0),
                "reactions_24h": reactions.get(code, 0),
                "replies_24h": replies.get(code, 0),
                "watchers_total": watchers.get(code, 0),
                "unique_viewers_24h": viewers.get(code, 0),
            }
            stmt = pg_insert(TickerBuzzDaily).values(row)
            update_cols = {
                c: getattr(stmt.excluded, c) for c in row if c not in ("market", "code", "date")
            }
            stmt = stmt.on_conflict_do_update(
                index_elements=["tenant_id", "market", "code", "date"], set_=update_cols
            )
            await session.execute(stmt)
        await session.commit()

    return {"symbols": len(codes)}


async def _run(market: str, tenant_id: str) -> None:
    counts = await snapshot_all(market, tenant_id=tenant_id)
    print(f"[buzz] {market}: snapshotted {counts['symbols']} symbols")


def main() -> None:
    market = sys.argv[1] if len(sys.argv) > 1 else "DSE"
    tenant_id = sys.argv[2] if len(sys.argv) > 2 else "bullsofdhaka"
    asyncio.run(_run(market, tenant_id))


if __name__ == "__main__":
    main()
