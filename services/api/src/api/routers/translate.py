"""On-demand post translation into the tenant's language. Cached by text hash."""

from __future__ import annotations

import hashlib

import redis.asyncio as aioredis
from fastapi import APIRouter
from pydantic import BaseModel, Field

from api.deps import CurrentTenant
from api.i18n import language_for
from bulls.ai.tasks.translate import translate
from bulls.core.config import get_settings

router = APIRouter(tags=["translate"])

CACHE_TTL = 7 * 24 * 3600  # translations of a fixed post don't change


class TranslateIn(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


class TranslateResp(BaseModel):
    text: str
    language: str


@router.post("/translate")
async def translate_post(body: TranslateIn, tenant: CurrentTenant) -> TranslateResp:
    language = language_for(tenant.locale)
    digest = hashlib.md5(body.text.encode()).hexdigest()
    cache_key = f"tr:{tenant.locale}:{digest}"
    redis = aioredis.from_url(get_settings().redis_url)
    try:
        cached = await redis.get(cache_key)
        if cached:
            return TranslateResp(text=cached.decode(), language=language)
        out = await translate(body.text, language=language)
        await redis.set(cache_key, out, ex=CACHE_TTL)
        return TranslateResp(text=out, language=language)
    finally:
        await redis.aclose()
