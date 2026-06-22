"""Labeled eval set for sentiment classification.

Hand-labeled, Bangla + English, with deliberately tricky cases (sarcasm, stop-loss = bearish,
questions = neutral). Grow this over time — it's the ground truth the classifier is measured on.
"""

from __future__ import annotations

from pydantic import BaseModel


class Example(BaseModel):
    text: str
    label: str  # "bull" | "bear" | "neutral"
    note: str = ""  # why this label (esp. for tricky cases)


SENTIMENT_EVAL_SET: list[Example] = [
    # --- clear bull (English) ---
    Example(text="$GP breaking out on huge volume, loading up before earnings 🚀", label="bull"),
    Example(
        text="Accumulating $BEXIMCO down here, fundamentals are solid for the long term.",
        label="bull",
    ),
    # --- clear bear (English) ---
    Example(text="$ROBI looks weak, support broke. Cutting my position.", label="bear"),
    Example(
        text="Took my stop-loss on $WALTONHIL, momentum is dead.",
        label="bear",
        note="stop-loss = bearish on direction",
    ),
    # --- neutral (English) ---
    Example(
        text="Anyone know when $SQURPHARMA reports next quarter?",
        label="neutral",
        note="question, no stance",
    ),
    Example(text="$GP closed at 254.1 today, volume 283k.", label="neutral", note="pure data"),
    # --- sarcasm / tricky (English) ---
    Example(
        text="Oh sure, $BEXIMCO to the moon 🙄 another pump before the dump.",
        label="bear",
        note="sarcasm flips literal",
    ),
    Example(
        text="Great, my $ROBI bag is down another 5%. Love it here.", label="bear", note="sarcastic"
    ),
    # --- clear bull (Bangla) ---
    Example(text="$GP আজকে ব্রেকআউট দিচ্ছে, আমি আরও কিনছি। লং টার্মে দারুণ।", label="bull"),
    Example(text="$SQURPHARMA ডিভিডেন্ড ভালো, ধরে রাখার মতো শেয়ার।", label="bull"),
    # --- clear bear (Bangla) ---
    Example(text="$BEXIMCO সাপোর্ট ভেঙে গেছে, আরও নামবে। সাবধান।", label="bear"),
    Example(text="$WALTONHIL এ লস দিয়ে বের হয়ে গেলাম, মোমেন্টাম শেষ।", label="bear"),
    # --- neutral (Bangla) ---
    Example(text="$ROBI এর পরবর্তী রিপোর্ট কবে কেউ জানেন?", label="neutral", note="question"),
    Example(
        text="আজকে ডিএসই সূচক ৫০ পয়েন্ট বেড়েছে।",
        label="neutral",
        note="market data, no single-stock stance",
    ),
    # --- mixed language ---
    Example(text="$GP strong আছে, আমি bullish — target 320.", label="bull"),
    Example(text="honestly $BEXIMCO ছেড়ে দেওয়াই ভালো, no hope.", label="bear"),
]
