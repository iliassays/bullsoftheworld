"""arq worker — async AI jobs off Redis.

The API ENQUEUES jobs and returns immediately; a slow/expensive Claude call NEVER blocks a web
request. Run with:

    uv run arq ai_worker.worker.WorkerSettings
"""

from __future__ import annotations

from typing import ClassVar

import redis.asyncio as aioredis
from arq.connections import RedisSettings

from bulls.ai.tasks.sentiment import classify_sentiment
from bulls.core.config import get_settings
from bulls.core.db import get_sessionmaker
from bulls.core.models import Post


async def tag_sentiment(ctx, post_id: int) -> str:
    """Classify a post and persist a bull/bear tag (neutral leaves it untagged)."""
    sm = get_sessionmaker()
    async with sm() as session:
        post = await session.get(Post, post_id)
        if post is None:
            return "post-gone"
        if post.sentiment is not None:
            return "already-tagged"  # user set it explicitly; don't override
        result = await classify_sentiment(post.body)
        if result.label in ("bull", "bear"):
            post.sentiment = result.label
            await session.commit()
        label = result.label

    # notify the feed so the UI can update the tag live
    redis: aioredis.Redis = ctx["redis_pub"]
    await redis.publish("post:tagged", f"{post_id}:{label}")
    return label


async def startup(ctx) -> None:
    ctx["redis_pub"] = aioredis.from_url(get_settings().redis_url)


async def shutdown(ctx) -> None:
    await ctx["redis_pub"].aclose()


class WorkerSettings:
    """arq entry point."""

    functions: ClassVar = [tag_sentiment]
    on_startup: ClassVar = startup
    on_shutdown: ClassVar = shutdown
    redis_settings: ClassVar = RedisSettings.from_dsn(get_settings().redis_url)
