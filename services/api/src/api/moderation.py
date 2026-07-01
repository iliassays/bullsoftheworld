"""Write-path moderation glue (docs/specs/feed-moderation.md §5-6).

Bridges the pure `bulls.moderation` engine to the API: loads each tenant's policy once, builds the
`Context` the scorer needs from Postgres, runs the synchronous L0-L2 decision, and appends an immutable
`moderation_event`. Phase 1 is synchronous-only (no L3/L4) — clear violations are blocked at write, the
gray zone is saved `pending` for human review, and clean posts publish. No AI here.
"""

from __future__ import annotations

import datetime as dt
import hashlib
from functools import lru_cache
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bulls.core.models import (
    Cashtag,
    Follow,
    ModerationEvent,
    Post,
    Symbol,
    TickerAnalytics,
    User,
)
from bulls.moderation import Action, Context, Decision, decide, load_policy, normalize

# repo root is parents[4] of services/api/src/api/moderation.py (same as main.py's _TENANTS_DIR).
_TENANTS_DIR = Path(__file__).resolve().parents[4] / "tenants"

# Map a final Action to the persisted Post.moderation_status.
_STATUS = {
    Action.ALLOW: "published",
    Action.MASK: "published",
    Action.LABEL: "published",
    Action.HOLD: "pending",
    Action.BLOCK: "blocked",
}


@lru_cache(maxsize=8)
def _policy_for(tenant_name: str):
    """Compiled policy per tenant, cached. Config is data under tenants/<name>/moderation/."""
    return load_policy(_TENANTS_DIR / tenant_name / "moderation")


def normalized_hash(text: str) -> str:
    return hashlib.sha256(normalize(text).folded.encode("utf-8")).hexdigest()


async def _build_context(
    session: AsyncSession,
    *,
    user: User,
    market: str,
    cashtags: list[str],
    is_reply: bool,
    route_code: str | None,
) -> Context:
    age_days = None
    if user.created_at is not None:
        now = dt.datetime.now(dt.UTC)
        created = user.created_at
        if created.tzinfo is None:
            created = created.replace(tzinfo=dt.UTC)
        age_days = (now - created).total_seconds() / 86400

    followers = (
        await session.scalar(
            select(func.count()).select_from(Follow).where(Follow.followee_id == user.id)
        )
        or 0
    )

    # Market-risk context for the primary cashtag: thin liquidity / Z category.
    thin, z_cat = False, False
    if cashtags:
        code = cashtags[0]
        sym = await session.scalar(
            select(Symbol).where(Symbol.market == market, Symbol.code == code)
        )
        if sym is not None:
            z_cat = sym.category == "Z"
        ta = await session.scalar(
            select(TickerAnalytics).where(
                TickerAnalytics.market == market, TickerAnalytics.code == code
            )
        )
        if ta is not None and ta.avg_volume_20 and ta.last_close:
            thin = (ta.avg_volume_20 * ta.last_close / 1e6) < 5.0  # < 5mn Tk ADTV

    # Velocity: this author's posts on the same primary cashtag in the last 24h.
    velocity = 0
    if cashtags:
        since = dt.datetime.now(dt.UTC) - dt.timedelta(hours=24)
        velocity = (
            await session.scalar(
                select(func.count())
                .select_from(Post)
                .join(Cashtag, Cashtag.post_id == Post.id)
                .where(
                    Post.author_id == user.id,
                    Post.created_at >= since,
                    Cashtag.market == market,
                    Cashtag.code == cashtags[0],
                )
            )
            or 0
        )

    return Context(
        account_age_days=age_days,
        is_official=user.is_official,
        followers=followers or 0,
        thin_liquidity=thin,
        z_category=z_cat,
        cashtag_velocity=velocity,
        route_code=route_code,
        is_reply=is_reply,
    )


async def moderate_new_post(
    session: AsyncSession,
    *,
    body: str,
    user: User,
    tenant_name: str,
    market: str,
    cashtags: list[str],
    is_reply: bool,
    route_code: str | None = None,
) -> Decision:
    """Run the synchronous cascade for a post about to be created. Pure decision — the caller applies
    the status and (for MASK) the masked body; `record_event` writes the audit row after flush."""
    policy = _policy_for(tenant_name)
    ctx = await _build_context(
        session,
        user=user,
        market=market,
        cashtags=cashtags,
        is_reply=is_reply,
        route_code=route_code,
    )
    return decide(body, policy, ctx)


def status_for(decision: Decision) -> str:
    return _STATUS[decision.action]


async def record_event(
    session: AsyncSession,
    *,
    post_id: int,
    tenant_name: str,
    decision: Decision,
    actor: str = "system",
    note: str | None = None,
) -> None:
    session.add(
        ModerationEvent(
            post_id=post_id,
            tenant_id=tenant_name,
            decision=decision.action.value,
            layer=decision.layer,
            risk_score=decision.risk_score,
            categories=[c.value for c in decision.categories],
            rule_ids=decision.rule_ids,
            reason_code=decision.reason_code,
            actor=actor,
            note=note,
        )
    )
