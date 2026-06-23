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


class AdviceExample(BaseModel):
    text: str
    is_advice: bool
    note: str = ""


# Ground truth for the no-advice compliance gate. `is_advice=True` must be caught; `False` is
# descriptive prose the gate must let through. Grow this whenever the gate mis-fires in the wild.
ADVICE_EVAL_SET: list[AdviceExample] = [
    # --- advice (English) — must be flagged ---
    AdviceExample(text="Buy $GP now, it's a great entry.", is_advice=True),
    AdviceExample(text="I'd sell here and book profit.", is_advice=True),
    AdviceExample(text="Time to accumulate, target 320.", is_advice=True),
    AdviceExample(text="Set a stop-loss at 240 and go long.", is_advice=True),
    AdviceExample(text="You should hold this for the long term.", is_advice=True),
    # --- advice (Bangla) — must be flagged ---
    AdviceExample(text="এখন $GP কিনুন, ভালো সুযোগ।", is_advice=True),
    AdviceExample(text="টার্গেট ৩২০, লাভ তুলে নিন।", is_advice=True),
    AdviceExample(text="$BEXIMCO বিক্রি করে দিন, আর আশা নেই।", is_advice=True),
    # --- descriptive (English) — must pass ---
    AdviceExample(
        text="$GP rose 2% today on heavy volume; RSI is elevated at 72.",
        is_advice=False,
        note="pure description",
    ),
    AdviceExample(
        text="Support sits near 250 and resistance near 257.",
        is_advice=False,
        note="levels, not a call",
    ),
    AdviceExample(
        text="Buyers stepped in after the stock sold off this morning.",
        is_advice=False,
        note="'buyers'/'sold off' are descriptive, not imperative",
    ),
    AdviceExample(
        text="The stock is trading below its 200-day average.",
        is_advice=False,
    ),
    # --- descriptive (Bangla) — must pass ---
    AdviceExample(
        text="$GP আজ ১% কমেছে, ভলিউম গড়ের চেয়ে বেশি।",
        is_advice=False,
        note="price description in Bangla",
    ),
    AdviceExample(
        text="শেয়ারটি তার ২০০ দিনের গড়ের নিচে রয়েছে।",
        is_advice=False,
    ),
]
