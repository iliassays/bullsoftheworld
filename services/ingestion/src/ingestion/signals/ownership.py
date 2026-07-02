"""Ownership agents: detect material stake changes between the two latest disclosures.

Foreign moves rarely, so its threshold is low; institutional wiggles constantly, so its threshold is
high. Each beat is published by its own agent. Facts + a plain "what it means," never advice.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import pairwise

from bulls.core.models import ShareholdingSnapshot

# beat -> (field on the snapshot, event_type, threshold in percentage points)
BEATS = {
    "foreign": ("foreign_pct", "foreign_change", 1.0),
    "institution": ("institute", "institution_change", 2.0),
    "sponsor": ("sponsor_director", "sponsor_change", 1.0),
}


@dataclass
class OwnSignal:
    beat: str
    event_type: str
    occurrence_key: str
    payload: dict


# A falling streak needs this many consecutive declining disclosures and at least this much
# cumulative drop — insiders steadily walking out the door, not one noisy month.
_STREAK_MIN_RUN = 3
_STREAK_MIN_DROP_PP = 1.0


def detect_sponsor_streak(snaps_desc: list[ShareholdingSnapshot]) -> OwnSignal | None:
    """Sponsor/director stake falling across ≥3 consecutive disclosures (newest first input).

    The pairwise detector above catches single big moves; this catches the slow bleed that never
    trips the per-disclosure threshold but sums to a material exit. The strongest ownership story
    a retail reader can get from public data — descriptive, source: DSE disclosures.
    """
    vals = [s.sponsor_director for s in snaps_desc]
    if len(vals) < _STREAK_MIN_RUN + 1 or any(v is None for v in vals[: _STREAK_MIN_RUN + 1]):
        return None
    run = 0
    for newer, older in pairwise(vals):
        if newer is not None and older is not None and newer < older:
            run += 1
        else:
            break
    if run < _STREAK_MIN_RUN:
        return None
    top = vals[run]
    drop = top - vals[0]
    if drop < _STREAK_MIN_DROP_PP:
        return None
    return OwnSignal(
        "sponsor",
        "sponsor_falling_streak",
        str(snaps_desc[0].as_of_date),
        {
            "now": round(vals[0], 2),
            "prev": round(top, 2),
            "as_of": str(snaps_desc[0].as_of_date),
            "runs": run,
            "drop": round(drop, 2),
            "up": False,
        },
    )


def detect(prev: ShareholdingSnapshot, latest: ShareholdingSnapshot) -> list[OwnSignal]:
    out: list[OwnSignal] = []
    key = str(latest.as_of_date)
    for beat, (field, event_type, threshold) in BEATS.items():
        now = getattr(latest, field)
        before = getattr(prev, field)
        if now is None or before is None:
            continue
        delta = now - before
        if abs(delta) >= threshold:
            out.append(
                OwnSignal(
                    beat,
                    event_type,
                    key,
                    {"now": round(now, 2), "prev": round(before, 2), "as_of": key, "up": delta > 0},
                )
            )
    return out


_TEMPLATES: dict[str, tuple[str, str]] = {
    "foreign_change": (
        "Foreign holders {dir} their stake to {now}% (from {prev}%) as of {as_of}. "
        "A shift in foreign ownership is often read as longer-term interest — one input, not advice.",
        "বিদেশি বিনিয়োগকারীরা তাদের অংশীদারিত্ব {now}% এ {dir_bn} ({prev}% থেকে), {as_of} অনুযায়ী। "
        "বিদেশি মালিকানার পরিবর্তন প্রায়ই দীর্ঘমেয়াদি আগ্রহ হিসেবে দেখা হয় — একটি সূচক, পরামর্শ নয়।",
    ),
    "institution_change": (
        "Institutions {dir} their holding to {now}% (from {prev}%) as of {as_of}. "
        "Institutional flows are watched as a 'smart money' cue — descriptive, not advice.",
        "প্রাতিষ্ঠানিক বিনিয়োগকারীরা তাদের অংশ {now}% এ {dir_bn} ({prev}% থেকে), {as_of} অনুযায়ী। "
        "প্রাতিষ্ঠানিক প্রবাহ 'স্মার্ট মানি' ইঙ্গিত হিসেবে দেখা হয় — তথ্যমূলক, পরামর্শ নয়।",
    ),
    "sponsor_change": (
        "Sponsors/directors {dir} their holding to {now}% (from {prev}%) as of {as_of} — "
        "insiders changing their own stake. Descriptive, not advice.",
        "স্পনসর/পরিচালকরা তাদের অংশ {now}% এ {dir_bn} ({prev}% থেকে), {as_of} অনুযায়ী — "
        "অভ্যন্তরীণরা নিজেদের অংশীদারিত্ব পরিবর্তন করছেন। তথ্যমূলক, পরামর্শ নয়।",
    ),
    "sponsor_falling_streak": (
        "Sponsor/director holding has fallen {runs} disclosures in a row: {prev}% → {now}% "
        "(-{drop} pp) as of {as_of}. A steady insider reduction over months — worth reading the "
        "disclosures yourself. Source: DSE shareholding data. Descriptive, not advice.",
        "স্পনসর/পরিচালকদের অংশ টানা {runs}টি ডিসক্লোজারে কমেছে: {prev}% → {now}% (-{drop} পিপি), "
        "{as_of} অনুযায়ী। মাসের পর মাস অভ্যন্তরীণদের ধারাবাহিক হ্রাস — ডিসক্লোজারগুলো নিজে পড়ে দেখুন। "
        "উৎস: DSE শেয়ারহোল্ডিং ডেটা। তথ্যমূলক, পরামর্শ নয়।",
    ),
}


def render(sig: OwnSignal, code: str, locale: str) -> str:
    en, bn = _TEMPLATES[sig.event_type]
    up = sig.payload["up"]
    fields = {
        **sig.payload,  # now / prev / as_of (+ runs / drop for streaks)
        "code": code,
        "dir": "raised" if up else "trimmed",
        "dir_bn": "বাড়িয়েছে" if up else "কমিয়েছে",
    }
    tmpl = bn if locale == "bn" else en
    return f"{code} — " + tmpl.format(**fields)
