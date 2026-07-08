"""Backfill pgvector knowledge chunks for existing research sources.

Usage:
    uv run python scripts/backfill_knowledge.py --market DSE --limit 500

This is intentionally resumable: each source upserts by stable source identity. Run small batches on
limited servers, or leave AI_EMBEDDING_PROVIDER=hash for no external service dependency.
"""

from __future__ import annotations

import argparse
import asyncio

from sqlalchemy import select

from bulls.ai.retrieval import index_announcement, index_post, index_signal_event
from bulls.core.db import get_sessionmaker
from bulls.core.models import Announcement, Cashtag, Post, SignalEvent


async def backfill(market: str, *, limit: int, include_posts: bool, include_signals: bool) -> None:
    sm = get_sessionmaker()
    total = 0
    async with sm() as session:
        announcement_ids = list(
            await session.scalars(
                select(Announcement.id)
                .where(Announcement.market == market)
                .order_by(Announcement.published_at.desc(), Announcement.id.desc())
                .limit(limit)
            )
        )
        for announcement_id in announcement_ids:
            total += await index_announcement(session, announcement_id)

        if include_posts:
            post_ids = list(
                await session.scalars(
                    select(Post.id)
                    .join(Cashtag, Cashtag.post_id == Post.id)
                    .where(
                        Cashtag.market == market,
                        Post.moderation_status == "published",
                        Post.kind == "user",
                    )
                    .order_by(Post.created_at.desc())
                    .limit(limit)
                )
            )
            for post_id in post_ids:
                total += await index_post(session, post_id)

        if include_signals:
            signal_ids = list(
                await session.scalars(
                    select(SignalEvent.id)
                    .where(SignalEvent.market == market)
                    .order_by(SignalEvent.created_at.desc())
                    .limit(limit)
                )
            )
            for signal_id in signal_ids:
                total += await index_signal_event(session, signal_id)

        await session.commit()
    print(f"indexed {total} chunks for {market}")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--market", default="DSE")
    p.add_argument("--limit", type=int, default=500)
    p.add_argument("--no-posts", action="store_true")
    p.add_argument("--no-signals", action="store_true")
    args = p.parse_args()
    asyncio.run(
        backfill(
            args.market,
            limit=args.limit,
            include_posts=not args.no_posts,
            include_signals=not args.no_signals,
        )
    )


if __name__ == "__main__":
    main()
