"""Official desk profiles — the StockTwits-style page for an automated agent account.

A "desk" is one of the system agent accounts (verified official accounts, e.g. @BullsOfDhakaVolume)
that post the descriptive data notes. This exposes its public profile — name, bio, joined, posts — so
users can visit it, read what it does, and (Phase 3) follow it. Its posts come from the existing
`GET /posts?author=<handle>` filter. Descriptive, verified, never advice.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import case, delete, func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from api.deps import (
    CurrentLocale,
    CurrentTenant,
    CurrentUser,
    DbSession,
    OptionalUser,
    enforce_market_feature,
)
from bulls.core.markets import get_market_profile
from bulls.core.models import Follow, Post, User
from bulls.core.scheduling import analysis_schedule

router = APIRouter(tags=["desks"])

# desk handle -> (EN bio, BN bio).
_DESK_BIOS: dict[str, tuple[str, str]] = {
    "BullsOfDhakaLevels": (
        "Confirmed price-structure events — 52-week highs and lows, breakouts, moving-average crosses.",
        "নিশ্চিত মূল্য-কাঠামোর ঘটনা — ৫২-সপ্তাহের উচ্চ/নিম্ন, ব্রেকআউট, মুভিং-এভারেজ ক্রস।",
    ),
    "BullsOfDhakaVolume": (
        "Flags stocks trading at unusual volume versus their normal pace.",
        "স্বাভাবিকের তুলনায় অস্বাভাবিক ভলিউমে লেনদেন হওয়া শেয়ার চিহ্নিত করে।",
    ),
    "BullsOfDhakaForeign": (
        "Tracks material changes in foreign investors' stakes at each disclosure.",
        "প্রতি প্রকাশে বিদেশি বিনিয়োগকারীদের অংশে উল্লেখযোগ্য পরিবর্তন ট্র্যাক করে।",
    ),
    "BullsOfDhakaInstitution": (
        "Tracks material changes in institutional holdings at each disclosure.",
        "প্রতি প্রকাশে প্রাতিষ্ঠানিক অংশে উল্লেখযোগ্য পরিবর্তন ট্র্যাক করে।",
    ),
    "BullsOfDhakaSponsor": (
        "Tracks sponsor and director (insider) stake changes.",
        "স্পনসর ও পরিচালক (অভ্যন্তরীণ) অংশের পরিবর্তন ট্র্যাক করে।",
    ),
    "BullsOfDhakaDividend": (
        "Posts dividend declarations as they are disclosed.",
        "লভ্যাংশ ঘোষণা প্রকাশের সাথে সাথে পোস্ট করে।",
    ),
    "BullsOfDhakaEarnings": (
        "Posts quarterly and annual results as they land.",
        "ত্রৈমাসিক ও বার্ষিক ফলাফল প্রকাশের সাথে পোস্ট করে।",
    ),
    "BullsOfDhakaRating": (
        "Posts credit-rating changes.",
        "ক্রেডিট রেটিং পরিবর্তন পোস্ট করে।",
    ),
    "BullsOfDhakaMarket": (
        "The daily market close — index, breadth and turnover.",
        "দৈনিক বাজার ক্লোজ — সূচক, ব্রেডথ ও টার্নওভার।",
    ),
    "BullsOfDhakaMomentum": (
        "Highlights the market's strongest 12-month price trends.",
        "বাজারের সবচেয়ে শক্তিশালী ১২-মাসের মূল্য-প্রবণতা তুলে ধরে।",
    ),
    "BullsOfDhakaStrength": (
        "Flags stocks rising while the market falls — relative strength.",
        "বাজার পড়লেও যেসব শেয়ার বাড়ছে — আপেক্ষিক শক্তি — চিহ্নিত করে।",
    ),
    "BullsOfDhakaQuality": (
        "Highlights profitable companies trading below their sector's valuation.",
        "খাতের গড়ের নিচে লেনদেন হওয়া লাভজনক কোম্পানি তুলে ধরে।",
    ),
    "BullsOfDhakaSmartMoney": (
        "Flags broad institutional and foreign accumulation.",
        "প্রতিষ্ঠান ও বিদেশি বিনিয়োগকারীদের বিস্তৃত সঞ্চয় চিহ্নিত করে।",
    ),
    "BullsOfDhakaAccumulation": (
        "Spots quiet accumulation — money flowing in while price stays flat.",
        "নীরব সঞ্চয় শনাক্ত করে — দাম স্থির থাকতেই অর্থপ্রবাহ আসছে।",
    ),
    "BullsOfDhakaCircuit": (
        "Flags stocks that hit the daily price limit (circuit).",
        "দৈনিক দামসীমা (সার্কিট) ছোঁয়া শেয়ার চিহ্নিত করে।",
    ),
    "BullsOfDhakaBreakout": (
        "Flags stocks pushing to new 52-week highs.",
        "নতুন ৫২-সপ্তাহের সর্বোচ্চে ওঠা শেয়ার চিহ্নিত করে।",
    ),
}
_FALLBACK_BIO = (
    "An automated official desk. Facts only, never advice.",
    "একটি স্বয়ংক্রিয় অফিসিয়াল ডেস্ক। শুধুই তথ্য, কোনো পরামর্শ নয়।",
)


def _desk_bio(handle: str) -> tuple[str, str]:
    if handle == "BullsOfWallStShorts":
        return (
            "Flags statistically unusual FINRA-reported short-sale activity without treating it as short interest or a directional call.",
            "FINRA-তে রিপোর্ট হওয়া অস্বাভাবিক short-sale কার্যকলাপ চিহ্নিত করে; এটিকে short interest বা দিকনির্দেশক সংকেত ধরে না।",
        )
    if handle == "BullsOfWallStFilings":
        return (
            "Surfaces material official SEC filings with a direct source link.",
            "সরাসরি উৎস লিংকসহ গুরুত্বপূর্ণ অফিসিয়াল SEC ফাইলিং তুলে ধরে।",
        )
    if handle.startswith("BullsOfWallSt"):
        equivalent = handle.replace("BullsOfWallSt", "BullsOfDhaka", 1)
        if equivalent in _DESK_BIOS:
            return _DESK_BIOS[equivalent]
    return _DESK_BIOS.get(handle, _FALLBACK_BIO)


@dataclass(frozen=True)
class DeskPolicy:
    cadence: tuple[str, str]
    methodology: tuple[str, str]
    post_rule: tuple[str, str]
    source_note: tuple[str, str]
    schedule: str


_POLICIES = {
    "volume": DeskPolicy(
        (
            "Checked around 11:45, 12:45 and 13:45 BDT during each DSE session.",
            "প্রতি DSE সেশনে প্রায় ১১:৪৫, ১২:৪৫ ও ১৩:৪৫ BDT-তে পরীক্ষা করা হয়।",
        ),
        (
            "Compares volume so far with the volume normally expected by that point, using the prior 20 sessions. Requires at least 2.5x expected pace and a 50,000-share average-volume floor.",
            "আগের ২০ সেশনের ভিত্তিতে দিনের ওই সময় পর্যন্ত প্রত্যাশিত ভলিউমের সঙ্গে বর্তমান ভলিউম তুলনা করে। অন্তত ২.৫ গুণ গতি এবং ৫০,০০০ শেয়ারের গড়-ভলিউম দরকার।",
        ),
        (
            "A scheduled check does not guarantee a post. It posts once per stock per session only when the threshold is crossed on a fresh quote.",
            "নির্ধারিত পরীক্ষা মানেই পোস্ট নয়। নতুন কোটে সীমা পার হলেই প্রতি শেয়ারে প্রতি সেশনে একবার পোস্ট হয়।",
        ),
        (
            "Intraday, 15-minute-delayed DSE quotes. Price direction describes the same delayed snapshot; it is not verified order flow.",
            "DSE-এর ১৫ মিনিট বিলম্বিত ইন্ট্রাডে কোট। দামের দিক একই বিলম্বিত স্ন্যাপশট বর্ণনা করে; এটি যাচাই করা অর্ডার-ফ্লো নয়।",
        ),
        "volume",
    ),
    "ownership": DeskPolicy(
        (
            "DSE ownership is generally disclosed monthly; we refresh the universe and evaluate changes every Friday around 20:10 BDT.",
            "DSE মালিকানা সাধারণত মাসে একবার প্রকাশিত হয়; আমরা প্রতি শুক্রবার প্রায় ২০:১০ BDT-তে পুরো বাজার রিফ্রেশ ও পরীক্ষা করি।",
        ),
        (
            "Compares the two latest valid DSE ownership disclosures. Institutional changes require 2.0 percentage points; foreign and sponsor/director changes require 1.0 point.",
            "সর্বশেষ দুটি বৈধ DSE মালিকানা প্রকাশ তুলনা করে। প্রতিষ্ঠানের পরিবর্তন অন্তত ২.০ শতাংশ-পয়েন্ট; বিদেশি ও উদ্যোক্তা/পরিচালকের পরিবর্তন অন্তত ১.০ পয়েন্ট হতে হয়।",
        ),
        (
            "It posts only a new material disclosure change. No post means no new qualifying change was found, not that the scheduled check failed.",
            "শুধু নতুন ও উল্লেখযোগ্য প্রকাশিত পরিবর্তনে পোস্ট হয়। পোস্ট না হওয়া মানে যোগ্য নতুন পরিবর্তন পাওয়া যায়নি; পরীক্ষা ব্যর্থ হয়েছে এমন নয়।",
        ),
        (
            "Month-end reported holdings, not live fund flow. The disclosure does not reveal trade date, execution price, transfer, reclassification or motive.",
            "মাসশেষের প্রকাশিত মালিকানা, লাইভ ফান্ড-ফ্লো নয়। এতে লেনদেনের তারিখ, দাম, হস্তান্তর, শ্রেণি পরিবর্তন বা উদ্দেশ্য জানা যায় না।",
        ),
        "ownership",
    ),
    "disclosure": DeskPolicy(
        (
            "DSE announcements are checked before the session and after the close on trading days.",
            "ট্রেডিং দিনে সেশন শুরুর আগে এবং বাজার বন্ধের পরে DSE ঘোষণা পরীক্ষা করা হয়।",
        ),
        (
            "Classifies new official announcements into earnings, dividend and rating events, then publishes the relevant factual fields.",
            "নতুন অফিসিয়াল ঘোষণাকে আয়, লভ্যাংশ ও রেটিং ইভেন্টে শ্রেণিবদ্ধ করে প্রাসঙ্গিক তথ্য প্রকাশ করে।",
        ),
        (
            "It posts only when a new qualifying official announcement is found.",
            "শুধু নতুন ও যোগ্য অফিসিয়াল ঘোষণা পাওয়া গেলে পোস্ট হয়।",
        ),
        ("Official DSE announcements.", "অফিসিয়াল DSE ঘোষণা।"),
        "disclosure",
    ),
    "levels": DeskPolicy(
        (
            "Evaluated once after each completed DSE session, around 19:25 BDT.",
            "প্রতি সম্পূর্ণ DSE সেশনের পরে প্রায় ১৯:২৫ BDT-তে পরীক্ষা করা হয়।",
        ),
        (
            "Recalculates confirmed daily-bar events such as moving-average crosses, breakouts and 52-week extremes.",
            "দৈনিক বারের ভিত্তিতে মুভিং-এভারেজ ক্রস, ব্রেকআউট ও ৫২-সপ্তাহের চরম অবস্থার মতো নিশ্চিত ইভেন্ট আবার হিসাব করে।",
        ),
        (
            "It posts only a newly confirmed event and suppresses repetitive events during the cooldown window.",
            "শুধু নতুন নিশ্চিত ইভেন্টে পোস্ট হয় এবং কুলডাউন সময়ে পুনরাবৃত্তি বন্ধ থাকে।",
        ),
        ("Completed-session daily bars.", "সম্পূর্ণ সেশনের দৈনিক বার।"),
        "levels",
    ),
    "factor": DeskPolicy(
        (
            "Evaluated after analytics refresh on every DSE trading day, around 19:40 BDT.",
            "প্রতি DSE ট্রেডিং দিনে অ্যানালিটিক্স রিফ্রেশের পরে প্রায় ১৯:৪০ BDT-তে পরীক্ষা করা হয়।",
        ),
        (
            "Applies a published deterministic threshold to end-of-day price, volume, valuation, profitability or disclosed ownership factors.",
            "দিনশেষের দাম, ভলিউম, মূল্যায়ন, লাভজনকতা বা প্রকাশিত মালিকানায় নির্ধারিত নিয়মভিত্তিক সীমা প্রয়োগ করে।",
        ),
        (
            "It posts only when a factor first qualifies; most factor events are suppressed for about 20 days to avoid repetitive noise.",
            "ফ্যাক্টর প্রথমবার যোগ্য হলে পোস্ট হয়; পুনরাবৃত্তি কমাতে বেশিরভাগ ফ্যাক্টর প্রায় ২০ দিন বন্ধ রাখা হয়।",
        ),
        (
            "Completed-session analytics and official disclosures where applicable.",
            "সম্পূর্ণ সেশনের অ্যানালিটিক্স এবং প্রযোজ্য ক্ষেত্রে অফিসিয়াল প্রকাশ।",
        ),
        "factor",
    ),
    "market": DeskPolicy(
        (
            "Published once after each completed DSE session, around 19:50 BDT.",
            "প্রতি সম্পূর্ণ DSE সেশনের পরে প্রায় ১৯:৫০ BDT-তে প্রকাশ করা হয়।",
        ),
        (
            "Summarises the official close, index move, breadth and turnover after the EOD pipeline completes.",
            "দিনশেষের পাইপলাইন শেষ হলে অফিসিয়াল ক্লোজ, সূচকের পরিবর্তন, ব্রেডথ ও টার্নওভার সারসংক্ষেপ করে।",
        ),
        ("One market wrap per completed session.", "প্রতি সম্পূর্ণ সেশনে একটি মার্কেট সারসংক্ষেপ।"),
        ("DSE end-of-day market summary.", "DSE দিনশেষের বাজার সারসংক্ষেপ।"),
        "market",
    ),
}

_US_POLICY_OVERRIDES = {
    "volume": DeskPolicy(
        (
            "Evaluated after each completed U.S. session when EOD data is published.",
            "প্রতি সম্পূর্ণ মার্কিন সেশনের EOD ডেটা প্রকাশের পরে পরীক্ষা করা হয়।",
        ),
        (
            "Compares the completed session's volume with the prior 20-session average.",
            "সম্পূর্ণ সেশনের ভলিউম আগের ২০ সেশনের গড়ের সঙ্গে তুলনা করে।",
        ),
        (
            "It posts only when a new completed-session event crosses the threshold.",
            "সম্পূর্ণ সেশনের নতুন ইভেন্ট সীমা পার হলেই পোস্ট হয়।",
        ),
        ("End-of-day market data, not an intraday feed.", "দিনশেষের বাজার ডেটা, ইন্ট্রাডে ফিড নয়।"),
        "volume",
    ),
    "ownership": DeskPolicy(
        (
            "SEC institutional data is refreshed weekly; Form 13F holdings are generally quarterly and can arrive up to 45 days after quarter-end.",
            "SEC প্রাতিষ্ঠানিক ডেটা সাপ্তাহিক রিফ্রেশ হয়; Form 13F সাধারণত ত্রৈমাসিক এবং ত্রৈমাসিক শেষের ৪৫ দিন পর পর্যন্ত আসতে পারে।",
        ),
        (
            "Compares aggregate reported 13F shares between the two latest reporting quarters.",
            "সর্বশেষ দুই রিপোর্টিং ত্রৈমাসিকের মোট প্রকাশিত 13F শেয়ার তুলনা করে।",
        ),
        (
            "A refresh does not guarantee a post; only a new qualifying filing change is published.",
            "রিফ্রেশ মানেই পোস্ট নয়; শুধু নতুন যোগ্য ফাইলিং পরিবর্তন প্রকাশিত হয়।",
        ),
        (
            "Delayed reported long holdings; no short positions, trade dates, execution prices or manager intent.",
            "বিলম্বিত প্রকাশিত লং হোল্ডিং; শর্ট পজিশন, লেনদেনের তারিখ, দাম বা ম্যানেজারের উদ্দেশ্য নেই।",
        ),
        "ownership",
    ),
    "disclosure": DeskPolicy(
        ("SEC company filings are checked daily.", "SEC কোম্পানি ফাইলিং প্রতিদিন পরীক্ষা করা হয়।"),
        (
            "Classifies new EDGAR filings and publishes qualifying official evidence.",
            "নতুন EDGAR ফাইলিং শ্রেণিবদ্ধ করে যোগ্য অফিসিয়াল প্রমাণ প্রকাশ করে।",
        ),
        (
            "It posts only when a new qualifying filing is found.",
            "শুধু নতুন যোগ্য ফাইলিং পাওয়া গেলে পোস্ট হয়।",
        ),
        ("Official SEC EDGAR filings.", "অফিসিয়াল SEC EDGAR ফাইলিং।"),
        "disclosure",
    ),
    "filings": DeskPolicy(
        ("SEC EDGAR is checked daily at 02:15 ET.", "SEC EDGAR প্রতিদিন ০২:১৫ ET-তে পরীক্ষা করা হয়।"),
        (
            "Publishes recent material company filings such as earnings reports, acquisitions, leadership changes and beneficial-ownership filings.",
            "আয়, অধিগ্রহণ, নেতৃত্ব পরিবর্তন ও উল্লেখযোগ্য মালিকানা সম্পর্কিত সাম্প্রতিক গুরুত্বপূর্ণ কোম্পানি ফাইলিং প্রকাশ করে।",
        ),
        (
            "Only a newly discovered qualifying filing is posted; historical onboarding data is never replayed into the feed.",
            "শুধু নতুন যোগ্য ফাইলিং পোস্ট হয়; অনবোর্ডিংয়ের পুরোনো ইতিহাস ফিডে পুনরায় প্রকাশ করা হয় না।",
        ),
        (
            "Official SEC EDGAR metadata with a direct filing link.",
            "সরাসরি ফাইলিং লিংকসহ অফিসিয়াল SEC EDGAR মেটাডেটা।",
        ),
        "filings",
    ),
    "shorts": DeskPolicy(
        (
            "Evaluated nightly after FINRA publishes the completed-session file, around 19:55 ET.",
            "FINRA সম্পূর্ণ সেশনের ফাইল প্রকাশের পর রাতে, প্রায় ১৯:৫৫ ET-তে মূল্যায়ন করা হয়।",
        ),
        (
            "Compares each ticker's short-marked share with its own 20-session norm, requiring a liquidity floor, a 12-point deviation and statistical confirmation.",
            "প্রতিটি টিকারের short-marked অংশ তার নিজস্ব ২০-সেশনের স্বাভাবিক মানের সঙ্গে তুলনা করে; ন্যূনতম লিকুইডিটি, ১২-পয়েন্ট পার্থক্য ও পরিসংখ্যানগত নিশ্চিতকরণ লাগে।",
        ),
        (
            "At most five largest anomalies are posted per session. Every ticker still has its own history on the stock page.",
            "প্রতি সেশনে সর্বোচ্চ পাঁচটি বড় অস্বাভাবিকতা পোস্ট হয়। প্রতিটি টিকারের নিজস্ব ইতিহাস স্টক পাতায় থাকে।",
        ),
        (
            "FINRA-facility short-sale volume, not whole-market volume or short interest; market-making and hedging are included.",
            "FINRA-facility short-sale volume; এটি পুরো বাজারের ভলিউম বা short interest নয় এবং market-making ও hedging অন্তর্ভুক্ত।",
        ),
        "shorts",
    ),
}

_BEAT_BY_SUFFIX = {
    "Volume": "volume",
    "Institution": "ownership",
    "Foreign": "ownership",
    "Sponsor": "ownership",
    "Dividend": "disclosure",
    "Earnings": "disclosure",
    "Rating": "disclosure",
    "Levels": "levels",
    "Market": "market",
    "Momentum": "factor",
    "Strength": "factor",
    "Quality": "factor",
    "SmartMoney": "factor",
    "Accumulation": "factor",
    "Circuit": "factor",
    "Breakout": "factor",
    "Shorts": "shorts",
    "Filings": "filings",
}


def _policy_for(handle: str, market: str = "DSE") -> DeskPolicy:
    kind = next((kind for suffix, kind in _BEAT_BY_SUFFIX.items() if handle.endswith(suffix)), None)
    if market == "US" and kind in _US_POLICY_OVERRIDES:
        return _US_POLICY_OVERRIDES[kind]
    if market == "US" and kind in {"levels", "factor", "market"}:
        base = _POLICIES[kind]
        return DeskPolicy(
            (
                "Evaluated after each completed U.S. session when EOD analytics are published.",
                "প্রতি সম্পূর্ণ মার্কিন সেশনের EOD অ্যানালিটিক্স প্রকাশের পরে পরীক্ষা করা হয়।",
            ),
            base.methodology,
            base.post_rule,
            (
                "Completed-session U.S. market data and official filings where applicable.",
                "সম্পূর্ণ মার্কিন সেশনের বাজার ডেটা এবং প্রযোজ্য অফিসিয়াল ফাইলিং।",
            ),
            base.schedule,
        )
    return _POLICIES.get(kind or "", _POLICIES["factor"])


def _next_local_check(
    now: dt.datetime,
    market: str,
    times: tuple[dt.time, ...],
    *,
    trading_days: bool = True,
    weekdays: frozenset[int] | None = None,
) -> dt.datetime:
    profile = get_market_profile(market)
    local_now = now.astimezone(profile.tz)
    for offset in range(15):
        date = local_now.date() + dt.timedelta(days=offset)
        valid = (
            date.isoweekday() in profile.trading_isoweekdays and date not in profile.holidays
            if trading_days
            else weekdays is None or date.isoweekday() in weekdays
        )
        if not valid:
            continue
        for time in times:
            candidate = dt.datetime.combine(date, time, tzinfo=profile.tz)
            if candidate > local_now:
                return candidate
    raise RuntimeError(f"Could not resolve next desk check for {market}")


def _next_evaluation(now: dt.datetime, market: str, policy: DeskPolicy) -> dt.datetime:
    if market != "DSE":
        if policy.schedule == "ownership":
            for offset in range(8):
                date = now.date() + dt.timedelta(days=offset)
                candidate = dt.datetime.combine(date, dt.time(10, 0), tzinfo=dt.UTC)
                if candidate.isoweekday() == 7 and candidate > now:
                    return candidate.astimezone(get_market_profile(market).tz)
        if policy.schedule == "disclosure":
            candidate = dt.datetime.combine(now.date(), dt.time(6, 15), tzinfo=dt.UTC)
            if candidate <= now:
                candidate += dt.timedelta(days=1)
            return candidate.astimezone(get_market_profile(market).tz)
        if policy.schedule == "filings":
            candidate = dt.datetime.combine(now.date(), dt.time(6, 15), tzinfo=dt.UTC)
            if candidate <= now:
                candidate += dt.timedelta(days=1)
            return candidate.astimezone(get_market_profile(market).tz)
        if policy.schedule == "shorts":
            candidate = dt.datetime.combine(now.date(), dt.time(23, 55), tzinfo=dt.UTC)
            if candidate <= now:
                candidate += dt.timedelta(days=1)
            return candidate.astimezone(get_market_profile(market).tz)
        return analysis_schedule(now, market)[1].astimezone(get_market_profile(market).tz)
    if policy.schedule == "volume":
        return _next_local_check(now, market, (dt.time(11, 45), dt.time(12, 45), dt.time(13, 45)))
    if policy.schedule == "ownership":
        return _next_local_check(
            now, market, (dt.time(20, 10),), trading_days=False, weekdays=frozenset({5})
        )
    if policy.schedule == "disclosure":
        return _next_local_check(now, market, (dt.time(9, 35), dt.time(19, 35)))
    check_time = {
        "levels": dt.time(19, 25),
        "factor": dt.time(19, 40),
        "market": dt.time(19, 50),
    }[policy.schedule]
    return _next_local_check(now, market, (check_time,))


class DeskOut(BaseModel):
    handle: str
    name: str
    bio: str
    joined: str  # "Jan 2025"
    posts: int
    followers: int
    following: bool  # does the signed-in viewer follow this desk?
    verified: bool = True
    cadence: str
    next_evaluation_at: str
    methodology: str
    post_rule: str
    source_note: str
    last_post_at: str | None = None


class DeskSearchOut(BaseModel):
    handle: str
    name: str
    verified: bool = True


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _desk_search_statement(tenant_id: str, query: str, limit: int):
    """Build the public desk lookup with tenant and official-account gates in the SQL itself."""
    normalized = query.strip().removeprefix("@").strip()
    escaped = _escape_like(normalized)
    contains = f"%{escaped}%"
    prefix = f"{escaped}%"
    exact = normalized.casefold()
    rank = case(
        (func.lower(User.handle) == exact, 0),
        (func.lower(User.name) == exact, 0),
        (User.handle.ilike(prefix, escape="\\"), 1),
        (User.name.ilike(prefix, escape="\\"), 1),
        else_=2,
    )
    return (
        select(User.handle, User.name)
        .where(
            User.tenant_id == tenant_id,
            User.is_official.is_(True),
            or_(
                User.handle.ilike(contains, escape="\\"),
                User.name.ilike(contains, escape="\\"),
            ),
        )
        .order_by(rank, func.lower(User.name), func.lower(User.handle))
        .limit(limit)
    )


@router.get("/desks")
async def search_desks(
    tenant: CurrentTenant,
    session: DbSession,
    q: str = Query(min_length=1, max_length=80),
    limit: int = Query(default=4, ge=1, le=10),
) -> list[DeskSearchOut]:
    """Search verified agents in the current tenant without exposing ordinary member accounts."""
    enforce_market_feature(tenant, "automated_desks")
    normalized = q.strip().removeprefix("@").strip()
    if not normalized:
        return []
    rows = (await session.execute(_desk_search_statement(tenant.name, normalized, limit))).all()
    return [DeskSearchOut(handle=handle, name=name) for handle, name in rows]


async def _resolve_desk(session, tenant, handle: str) -> User:
    enforce_market_feature(tenant, "automated_desks")
    u = await session.scalar(
        select(User).where(User.tenant_id == tenant.name, User.handle == handle)
    )
    if u is None or not u.is_official:
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
    post_stats = (
        await session.execute(
            select(func.count(Post.id), func.max(Post.created_at)).where(
                Post.author_id == u.id,
                Post.parent_id.is_(None),
                Post.moderation_status == "published",
            )
        )
    ).one()
    posts, last_post_at = post_stats
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
    bio_en, bio_bn = _desk_bio(u.handle)
    policy = _policy_for(u.handle, tenant.market)
    language_index = 1 if locale == "bn" else 0
    next_evaluation = _next_evaluation(dt.datetime.now(dt.UTC), tenant.market, policy)
    return DeskOut(
        handle=handle,
        name=u.name,
        bio=bio_bn if locale == "bn" else bio_en,
        joined=u.created_at.strftime("%b %Y"),
        posts=int(posts or 0),
        followers=int(followers or 0),
        following=following,
        cadence=policy.cadence[language_index],
        next_evaluation_at=next_evaluation.isoformat(),
        methodology=policy.methodology[language_index],
        post_rule=policy.post_rule[language_index],
        source_note=policy.source_note[language_index],
        last_post_at=last_post_at.isoformat() if last_post_at else None,
    )


@router.post("/desks/{handle}/follow")
async def follow_desk(
    handle: str, tenant: CurrentTenant, session: DbSession, user: CurrentUser
) -> dict:
    u = await _resolve_desk(session, tenant, handle)
    # Idempotent — following twice is a no-op, not an error.
    await session.execute(
        pg_insert(Follow)
        .values(follower_id=user.id, followee_id=u.id, tenant_id=tenant.name)
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
