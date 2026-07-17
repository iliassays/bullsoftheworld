"""Volume agent: flag unusual intraday volume, day-fraction scaled.

A half-day's volume must be compared to *expected-by-now*, not the full-day average — otherwise
everything looks quiet before the close. Pure detection; the runner supplies the session fraction.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from bulls.market_data.calendar import MARKET_CLOSE, MARKET_OPEN, to_market_tz

BEAT = "volume"
_RELVOL = 2.5  # ~p98 of the relative-volume distribution
_MIN_AVG_VOL = 50_000  # liquidity floor — don't flag thin names
_MIN_SESSION_FRACTION = 0.10  # ignore the unstable opening sample (roughly first 27 minutes)


@dataclass
class VolSignal:
    event_type: str
    occurrence_key: str
    payload: dict


def session_fraction(now: dt.datetime) -> float:
    """Fraction of the DSE session elapsed (0.05-1.0)."""
    local = to_market_tz(now)
    t = local.time()
    if t <= MARKET_OPEN:
        return 0.05
    if t >= MARKET_CLOSE:
        return 1.0
    o = dt.datetime.combine(local.date(), MARKET_OPEN, tzinfo=local.tzinfo)
    c = dt.datetime.combine(local.date(), MARKET_CLOSE, tzinfo=local.tzinfo)
    return max(0.05, min(1.0, (local - o).total_seconds() / (c - o).total_seconds()))


def detect(
    volume_today: int | None,
    avg_volume_20: float | None,
    fraction: float,
    day: str,
    change_pct: float | None = None,
) -> VolSignal | None:
    if (
        not volume_today
        or not avg_volume_20
        or avg_volume_20 < _MIN_AVG_VOL
        or fraction < _MIN_SESSION_FRACTION
    ):
        return None
    expected = avg_volume_20 * max(fraction, 0.05)
    relvol = volume_today / expected
    if relvol < _RELVOL:
        return None
    # pair the surge with today's price direction → heavy buying vs selling vs just busy
    if change_pct is not None and change_pct >= 0.5:
        direction = "buying"
    elif change_pct is not None and change_pct <= -0.5:
        direction = "selling"
    else:
        direction = "flat"
    return VolSignal("unusual_volume", day, {"relvol": round(relvol, 1), "direction": direction})


# direction -> (English, Bangla)
# Several phrasings per direction so a run of volume notes doesn't read word-for-word identical.
# A stable per-code pick keeps it deterministic (no drift) — a given stock always gets the same one.
_TEMPLATES: dict[str, list[tuple[str, str]]] = {
    "buying": [
        (
            "{code} is trading at ~{relvol}x its usual volume today and rising — heavy buying. Could be news; we just flag it. Not advice.",
            "{code} আজ স্বাভাবিকের প্রায় {relvol}x ভলিউমে লেনদেন হচ্ছে এবং দাম বাড়ছে — জোরালো কেনাকাটা। খবর থাকতে পারে; আমরা শুধু জানাচ্ছি। পরামর্শ নয়।",
        ),
        (
            "Heavy buying in {code} — volume is ~{relvol}x normal and the price is up. Worth checking why. Not advice.",
            "{code}-তে জোরালো ক্রয় — ভলিউম স্বাভাবিকের প্রায় {relvol}x এবং দাম উপরে। কেন, দেখে নিতে পারেন। পরামর্শ নয়।",
        ),
        (
            "{code} is unusually active (~{relvol}x normal) and climbing — buyers in control today. Descriptive, not advice.",
            "{code} আজ অস্বাভাবিক সক্রিয় (~{relvol}x) এবং উপরে উঠছে — ক্রেতারা নিয়ন্ত্রণে। তথ্যমূলক, পরামর্শ নয়।",
        ),
    ],
    "selling": [
        (
            "{code} is trading at ~{relvol}x its usual volume today and falling — heavy selling. Could be news; we just flag it. Not advice.",
            "{code} আজ স্বাভাবিকের প্রায় {relvol}x ভলিউমে লেনদেন হচ্ছে এবং দাম পড়ছে — জোরালো বিক্রি। খবর থাকতে পারে; আমরা শুধু জানাচ্ছি। পরামর্শ নয়।",
        ),
        (
            "Heavy selling in {code} — volume is ~{relvol}x normal and the price is down. Worth checking why. Not advice.",
            "{code}-তে জোরালো বিক্রি — ভলিউম স্বাভাবিকের প্রায় {relvol}x এবং দাম নিচে। কেন, যাচাই করুন। পরামর্শ নয়।",
        ),
        (
            "{code} is unusually active (~{relvol}x normal) but sliding — sellers in control today. Descriptive, not advice.",
            "{code} আজ অস্বাভাবিক সক্রিয় (~{relvol}x) কিন্তু পড়ছে — বিক্রেতারা নিয়ন্ত্রণে। তথ্যমূলক, পরামর্শ নয়।",
        ),
    ],
    "flat": [
        (
            "{code} is trading at ~{relvol}x its usual volume today — unusual activity. Could be news; we just flag it. Not advice.",
            "{code} আজ স্বাভাবিকের প্রায় {relvol}x ভলিউমে লেনদেন হচ্ছে — অস্বাভাবিক তৎপরতা। খবর থাকতে পারে; আমরা শুধু জানাচ্ছি। পরামর্শ নয়।",
        ),
        (
            "Unusual activity in {code} — volume is ~{relvol}x its normal pace. Worth checking why. Not advice.",
            "{code}-তে অস্বাভাবিক তৎপরতা — ভলিউম স্বাভাবিকের প্রায় {relvol}x। কারণ যাচাই করতে পারেন। পরামর্শ নয়।",
        ),
    ],
}


def render(sig: VolSignal, code: str, locale: str) -> str:
    variants = _TEMPLATES.get(sig.payload.get("direction", "flat"), _TEMPLATES["flat"])
    # Stable per-code variant pick (deterministic; avoids process-randomized hash()).
    pair = variants[sum(ord(c) for c in code) % len(variants)]
    body = pair[1 if locale == "bn" else 0].format(code=code, relvol=sig.payload["relvol"])
    suffix = (
        " এটি ১৫ মিনিট বিলম্বিত দুটি স্ন্যাপশটে দেখা প্রাথমিক ইন্ট্রাডে পর্যবেক্ষণ।"
        if locale == "bn"
        else " Provisional intraday observation confirmed across two 15-minute-delayed snapshots."
    )
    return f"{body}{suffix}"
