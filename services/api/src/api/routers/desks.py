"""Official desk profiles — the StockTwits-style page for an automated agent account.

A "desk" is one of the system agent accounts (handle `<tenant>-<beat>-agent`) that post the
descriptive data notes. This exposes its public profile — name, bio, joined date, post count — so
users can visit it, read what it does, and (Phase 3) follow it. Its posts come from the existing
`GET /posts?author=<handle>` filter. Descriptive, verified, never advice.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from api.deps import CurrentLocale, CurrentTenant, CurrentUser, DbSession, OptionalUser
from bulls.core.models import Follow, Post, User

router = APIRouter(tags=["desks"])

# beat token (handle stripped of the tenant prefix and the "-agent" suffix) -> (EN bio, BN bio).
_DESK_BIOS: dict[str, tuple[str, str]] = {
    "levels": (
        "Confirmed price-structure events — 52-week highs and lows, breakouts, moving-average crosses.",
        "নিশ্চিত মূল্য-কাঠামোর ঘটনা — ৫২-সপ্তাহের উচ্চ/নিম্ন, ব্রেকআউট, মুভিং-এভারেজ ক্রস।",
    ),
    "volume": (
        "Flags stocks trading at unusual volume versus their normal pace.",
        "স্বাভাবিকের তুলনায় অস্বাভাবিক ভলিউমে লেনদেন হওয়া শেয়ার চিহ্নিত করে।",
    ),
    "foreign": (
        "Tracks material changes in foreign investors' stakes at each disclosure.",
        "প্রতি প্রকাশে বিদেশি বিনিয়োগকারীদের অংশে উল্লেখযোগ্য পরিবর্তন ট্র্যাক করে।",
    ),
    "institution": (
        "Tracks material changes in institutional holdings at each disclosure.",
        "প্রতি প্রকাশে প্রাতিষ্ঠানিক অংশে উল্লেখযোগ্য পরিবর্তন ট্র্যাক করে।",
    ),
    "sponsor": (
        "Tracks sponsor and director (insider) stake changes.",
        "স্পনসর ও পরিচালক (অভ্যন্তরীণ) অংশের পরিবর্তন ট্র্যাক করে।",
    ),
    "dividend": (
        "Posts dividend declarations as they are disclosed.",
        "লভ্যাংশ ঘোষণা প্রকাশের সাথে সাথে পোস্ট করে।",
    ),
    "earnings": (
        "Posts quarterly and annual results as they land.",
        "ত্রৈমাসিক ও বার্ষিক ফলাফল প্রকাশের সাথে পোস্ট করে।",
    ),
    "rating": (
        "Posts credit-rating changes.",
        "ক্রেডিট রেটিং পরিবর্তন পোস্ট করে।",
    ),
    "market-update": (
        "The daily market close — index, breadth and turnover.",
        "দৈনিক বাজার ক্লোজ — সূচক, ব্রেডথ ও টার্নওভার।",
    ),
    "momentum": (
        "Highlights the market's strongest 12-month price trends.",
        "বাজারের সবচেয়ে শক্তিশালী ১২-মাসের মূল্য-প্রবণতা তুলে ধরে।",
    ),
    "strength": (
        "Flags stocks rising while the market falls — relative strength.",
        "বাজার পড়লেও যেসব শেয়ার বাড়ছে — আপেক্ষিক শক্তি — চিহ্নিত করে।",
    ),
    "quality": (
        "Highlights profitable companies trading below their sector's valuation.",
        "খাতের গড়ের নিচে লেনদেন হওয়া লাভজনক কোম্পানি তুলে ধরে।",
    ),
    "smartmoney": (
        "Flags broad institutional and foreign accumulation.",
        "প্রতিষ্ঠান ও বিদেশি বিনিয়োগকারীদের বিস্তৃত সঞ্চয় চিহ্নিত করে।",
    ),
    "accumulation": (
        "Spots quiet accumulation — money flowing in while price stays flat.",
        "নীরব সঞ্চয় শনাক্ত করে — দাম স্থির থাকতেই অর্থপ্রবাহ আসছে।",
    ),
    "circuit": (
        "Flags stocks that hit the daily price limit (circuit).",
        "দৈনিক দামসীমা (সার্কিট) ছোঁয়া শেয়ার চিহ্নিত করে।",
    ),
    "breakout": (
        "Flags stocks pushing to new 52-week highs.",
        "নতুন ৫২-সপ্তাহের সর্বোচ্চে ওঠা শেয়ার চিহ্নিত করে।",
    ),
}
_FALLBACK_BIO = (
    "An automated official desk. Facts only, never advice.",
    "একটি স্বয়ংক্রিয় অফিসিয়াল ডেস্ক। শুধুই তথ্য, কোনো পরামর্শ নয়।",
)


def _is_desk(handle: str) -> bool:
    return handle.endswith("-agent")


def _beat_token(handle: str, tenant_id: str) -> str:
    return handle.removeprefix(f"{tenant_id}-").removesuffix("-agent")


class DeskOut(BaseModel):
    handle: str
    name: str
    bio: str
    joined: str  # "Jan 2025"
    posts: int
    followers: int
    following: bool  # does the signed-in viewer follow this desk?
    verified: bool = True


async def _resolve_desk(session, tenant, handle: str) -> User:
    if not _is_desk(handle):
        raise HTTPException(status_code=404, detail=f"Unknown desk {handle!r}")
    u = await session.scalar(
        select(User).where(User.tenant_id == tenant.name, User.handle == handle)
    )
    if u is None:
        raise HTTPException(status_code=404, detail=f"Unknown desk {handle!r}")
    return u


@router.get("/desks/{handle}")
async def desk(
    handle: str,
    tenant: CurrentTenant,
    session: DbSession,
    locale: CurrentLocale,
    viewer: OptionalUser,
) -> DeskOut:
    u = await _resolve_desk(session, tenant, handle)
    posts = await session.scalar(
        select(func.count(Post.id)).where(Post.author_id == u.id, Post.parent_id.is_(None))
    )
    followers = await session.scalar(
        select(func.count()).select_from(Follow).where(Follow.followee_id == u.id)
    )
    following = False
    if viewer is not None:
        following = (
            await session.scalar(
                select(Follow.follower_id).where(
                    Follow.follower_id == viewer.id, Follow.followee_id == u.id
                )
            )
        ) is not None
    bio_en, bio_bn = _DESK_BIOS.get(_beat_token(handle, tenant.name), _FALLBACK_BIO)
    return DeskOut(
        handle=handle,
        name=u.name,
        bio=bio_bn if locale == "bn" else bio_en,
        joined=u.created_at.strftime("%b %Y"),
        posts=int(posts or 0),
        followers=int(followers or 0),
        following=following,
    )


@router.post("/desks/{handle}/follow")
async def follow_desk(
    handle: str, tenant: CurrentTenant, session: DbSession, user: CurrentUser
) -> dict:
    u = await _resolve_desk(session, tenant, handle)
    # Idempotent — following twice is a no-op, not an error.
    await session.execute(
        pg_insert(Follow)
        .values(follower_id=user.id, followee_id=u.id)
        .on_conflict_do_nothing()
    )
    await session.commit()
    return {"status": "following"}


@router.delete("/desks/{handle}/follow")
async def unfollow_desk(
    handle: str, tenant: CurrentTenant, session: DbSession, user: CurrentUser
) -> dict:
    u = await _resolve_desk(session, tenant, handle)
    await session.execute(
        delete(Follow).where(Follow.follower_id == user.id, Follow.followee_id == u.id)
    )
    await session.commit()
    return {"status": "not_following"}
