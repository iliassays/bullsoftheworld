"""Today's Watch — an AI note highlighting notable stocks from the day's activity.

Like the digest: the caller computes the ranked facts (movers + chatter) in code; the LLM only
writes the prose naming them. One LLM call for the whole note (cheap, cacheable daily).
"""

from __future__ import annotations

from pydantic import BaseModel

from bulls.ai.llm import structured_complete
from bulls.ai.prompts.watch import WATCH_SYSTEM_V1


class WatchItem(BaseModel):
    code: str
    change_pct: float
    posts: int
    bull: int
    bear: int


class WatchOut(BaseModel):
    summary: str


def _render(items: list[WatchItem]) -> str:
    lines = ["Active / moving stocks today:"]
    for it in items:
        lines.append(
            f"- {it.code}: {it.change_pct:+.2f}% today, {it.posts} posts "
            f"({it.bull} bull / {it.bear} bear)"
        )
    return "\n".join(lines)


async def todays_watch(items: list[WatchItem], *, language: str = "English") -> str:
    """Grounded 2-3 sentence watch note in the requested language."""
    if not items:
        return ""
    system = f"{WATCH_SYSTEM_V1}\n\nWrite the note in {language}."
    result = await structured_complete(system, _render(items), WatchOut)
    return result.summary.strip()
