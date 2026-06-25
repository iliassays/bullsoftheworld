"""Ownership agents: detect material stake changes between the two latest disclosures.

Foreign moves rarely, so its threshold is low; institutional wiggles constantly, so its threshold is
high. Each beat is published by its own agent. Facts + a plain "what it means," never advice.
"""

from __future__ import annotations

from dataclasses import dataclass

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
        "বিদেশি মালিকানার পরিবর্তন প্রায়ই দীর্ঘমেয়াদি আগ্রহ হিসেবে দেখা হয় — একটি ইনপুট, পরামর্শ নয়।",
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
}


def render(sig: OwnSignal, code: str, locale: str) -> str:
    en, bn = _TEMPLATES[sig.event_type]
    up = sig.payload["up"]
    fields = {
        "code": code,
        "now": sig.payload["now"],
        "prev": sig.payload["prev"],
        "as_of": sig.payload["as_of"],
        "dir": "raised" if up else "trimmed",
        "dir_bn": "বাড়িয়েছে" if up else "কমিয়েছে",
    }
    tmpl = bn if locale == "bn" else en
    return f"{code} — " + tmpl.format(**fields)
