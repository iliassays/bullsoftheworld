"""Idempotent pgvector reindex for an embedding-model rollout.

    uv run python -m bulls.ai.reindex --market DSE --tenant bullsofdhaka
"""

from __future__ import annotations

import argparse
import asyncio

from sqlalchemy import distinct, select

from bulls.ai.embeddings import embedding_model_name
from bulls.ai.retrieval import index_announcement, index_post, index_signal_event
from bulls.core.db import get_sessionmaker
from bulls.core.models import Announcement, Cashtag, Post, SignalEvent


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Re-embed retrieval evidence for one tenant/market")
    parser.add_argument("--market", required=True)
    parser.add_argument("--tenant", required=True)
    parser.add_argument("--batch-size", type=int, default=100)
    return parser.parse_args()


async def _run(market: str, tenant: str, batch_size: int) -> None:
    sm = get_sessionmaker()
    async with sm() as session:
        announcement_ids = list(
            await session.scalars(
                select(Announcement.id).where(Announcement.market == market)
            )
        )
        post_ids = list(
            await session.scalars(
                select(distinct(Post.id))
                .join(Cashtag, Cashtag.post_id == Post.id)
                .where(
                    Post.tenant_id == tenant,
                    Post.moderation_status == "published",
                    Cashtag.market == market,
                )
            )
        )
        signal_ids = list(
            await session.scalars(
                select(SignalEvent.id).where(
                    SignalEvent.tenant_id == tenant,
                    SignalEvent.market == market,
                )
            )
        )

        written = 0
        processed = 0
        for ids, indexer in (
            (announcement_ids, index_announcement),
            (post_ids, index_post),
            (signal_ids, index_signal_event),
        ):
            for source_id in ids:
                written += await indexer(session, source_id)
                processed += 1
                if processed % batch_size == 0:
                    await session.commit()
                    print(f"indexed {processed} sources / {written} chunks")
        await session.commit()
    print(
        f"reindex complete: model={embedding_model_name()} sources={processed} chunks={written}"
    )


def main() -> None:
    args = _parse_args()
    asyncio.run(_run(args.market.upper(), args.tenant, args.batch_size))


if __name__ == "__main__":
    main()
