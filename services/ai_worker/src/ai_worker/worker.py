"""arq worker (build step 4).

Pulls jobs off Redis and runs AI tasks (sentiment, summaries, embeddings, fraud-scoring). The api
ENQUEUES jobs and returns immediately — a slow/expensive Claude call NEVER blocks a web request.

STATUS: STUB.
"""

from __future__ import annotations

from typing import ClassVar

from bulls.core.config import get_settings


async def tag_sentiment(ctx, post_id: int) -> None:
    # step 4: load post, await classify_sentiment(body), persist label, publish update
    raise NotImplementedError("step 4: sentiment job")


class WorkerSettings:
    """arq entry point: `uv run arq ai_worker.worker.WorkerSettings`."""

    functions: ClassVar = [tag_sentiment]
    redis_settings: ClassVar = get_settings().redis_url
