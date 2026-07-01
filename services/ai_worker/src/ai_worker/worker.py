"""arq worker — async AI jobs off Redis.

The API ENQUEUES jobs and returns immediately; a slow/expensive Claude call NEVER blocks a web
request. Run with:

    uv run arq ai_worker.worker.WorkerSettings
"""

from __future__ import annotations

from typing import ClassVar

import redis.asyncio as aioredis
from arq.connections import RedisSettings

from bulls.ai.tasks.moderation import screen_post
from bulls.ai.tasks.sentiment import classify_sentiment
from bulls.core.config import get_settings
from bulls.core.db import get_sessionmaker
from bulls.core.models import ModerationEvent, Post

# Confidence floor before an L4 flag is acted on — keeps marginal calls from crowding the queue.
_SAFETY_MIN_CONFIDENCE = 0.6
# Safety-category -> the taxonomy category value stored on the event (see feed-moderation spec §3).
_SAFETY_CATEGORY = {
    "hate": "C6",
    "sexual": "C6",
    "harassment": "C6",
    "threat": "C6",
    "spam": "C9",
    "off_topic": "C9",
}


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


async def screen_post_safety(ctx, post_id: int) -> str:
    """L4 safety + relevance screen. Runs only on published user posts; a confident flag routes the
    post to the human review queue (status 'held'). It NEVER auto-deletes — over-flagging is the fear,
    so a reviewer confirms. When enforcement is off (shadow), the verdict is logged but status is left
    published. Every flag is audited in moderation_events (layer 4)."""
    sm = get_sessionmaker()
    s = get_settings()
    async with sm() as session:
        post = await session.get(Post, post_id)
        if post is None:
            return "post-gone"
        if post.kind != "user" or post.moderation_status != "published":
            return "skip"  # agent notes and already-actioned posts are out of scope

        result = await screen_post(post.body)
        if result.verdict == "ok" or result.confidence < _SAFETY_MIN_CONFIDENCE:
            return "ok"

        category = _SAFETY_CATEGORY.get(result.category, "C9")
        reason = (
            "off_topic" if result.verdict == "off_topic" else (result.category or "inappropriate")
        )
        model = s.ollama_model if s.ai_provider == "ollama" else s.anthropic_model

        session.add(
            ModerationEvent(
                post_id=post.id,
                tenant_id=post.tenant_id,
                decision="hold",
                layer=4,
                risk_score=round(result.confidence, 3),
                categories=[category],
                reason_code=reason,
                model=model,
                note=result.reason,
                actor="system",
            )
        )
        # Only actually hold the post when enforcement is on; shadow mode just logs the verdict.
        if s.moderation_enforce:
            post.moderation_status = "held"
            post.moderation_reason = reason
        await session.commit()
        return f"flagged:{result.verdict}"


async def startup(ctx) -> None:
    ctx["redis_pub"] = aioredis.from_url(get_settings().redis_url)


async def shutdown(ctx) -> None:
    await ctx["redis_pub"].aclose()


class WorkerSettings:
    """arq entry point."""

    functions: ClassVar = [tag_sentiment, screen_post_safety]
    on_startup: ClassVar = startup
    on_shutdown: ClassVar = shutdown
    redis_settings: ClassVar = RedisSettings.from_dsn(get_settings().redis_url)
