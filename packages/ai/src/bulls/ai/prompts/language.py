"""Shared language directive for AI prose tasks.

Local models (qwen2.5) tend to code-switch and mistranslate finance terms when asked to write
Bengali. This directive pins the output to fluent Bengali and supplies the correct vocabulary,
fixing the common failures: transliterated English ("শares"), wrong verbs ("হ্যাঙ্গ" for fell),
and "bear" mistranslated as "নিষেধাজ্ঞা" (ban).
"""

from __future__ import annotations

_BENGALI_GUIDE = """Write the response in natural, fluent Bengali (Bangla).
Strict rules:
- Do NOT transliterate or code-switch English words into Bengali script (never write things like
  "শares" or "হ্যাঙ্গ"). Write every word in correct Bengali.
- Keep ONLY the ticker code (e.g. GP, BEXIMCO) and numbers in their original form.
- Use correct financial vocabulary:
  - rose / went up = বেড়েছে ; fell / went down = কমেছে (never "হ্যাঙ্গ")
  - bullish = চাঙা / ইতিবাচক ; bearish = মন্দা / নেতিবাচক (never "নিষেধাজ্ঞা")
  - share / shares = শেয়ার (never "শares" or "শেখার") ; stock = স্টক / শেয়ার
  - volume = লেনদেনের পরিমাণ ; support = সাপোর্ট ; resistance = রেজিস্ট্যান্স
  - moving average = মুভিং অ্যাভারেজ ; overbought = অতিরিক্ত কেনা
  - posts / comments = পোস্ট / মন্তব্য (do not call them "সন্দেহময়"/suspicious)"""


def language_directive(language: str) -> str:
    """Return a strong instruction to write in `language` with finance vocabulary guidance."""
    if "Bengali" in language or "Bangla" in language:
        return _BENGALI_GUIDE
    return f"Write the response in natural, fluent {language}."
