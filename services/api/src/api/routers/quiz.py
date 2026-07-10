"""Daily quiz — one market-literacy question a day, streaks and points for learning.

Everyone gets the same question on a given day (deterministic rotation over the active bank), so
the community can talk about it. Points measure understanding, never trading performance.
"""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from api.deps import CurrentLocale, CurrentTenant, CurrentUser, DbSession
from bulls.core.models import QuizAnswer, QuizQuestion
from bulls.market_data.calendar import to_market_tz

router = APIRouter(prefix="/quiz", tags=["quiz"])

POINTS_PER_CORRECT = 10


def question_index_for_day(day: dt.date, bank_size: int) -> int:
    """Deterministic rotation: same question for everyone on a given market day."""
    return day.toordinal() % bank_size if bank_size else 0


def current_streak(days: set[dt.date], today: dt.date) -> int:
    """Consecutive answered days ending today or yesterday (today not yet answered ≠ broken)."""
    anchor = today if today in days else today - dt.timedelta(days=1)
    streak = 0
    while anchor in days:
        streak += 1
        anchor -= dt.timedelta(days=1)
    return streak


def _pick(i18n: dict, locale: str):
    return i18n.get(locale) or i18n.get("en") or next(iter(i18n.values()))


class QuizToday(BaseModel):
    question_id: int
    topic: str
    question: str
    choices: list[str]
    answered: bool
    # present only after answering — never leak the answer with the question
    your_choice: int | None = None
    correct: bool | None = None
    answer_idx: int | None = None
    explanation: str | None = None
    streak: int
    points: int


class QuizSubmit(BaseModel):
    question_id: int
    choice_idx: int = Field(ge=0, le=7)


async def _stats(session, user_id: int, today: dt.date) -> tuple[int, int]:
    days = set(
        await session.scalars(select(QuizAnswer.answered_on).where(QuizAnswer.user_id == user_id))
    )
    correct = await session.scalar(
        select(func.count())
        .select_from(QuizAnswer)
        .where(QuizAnswer.user_id == user_id, QuizAnswer.correct.is_(True))
    )
    return current_streak(days, today), int(correct or 0) * POINTS_PER_CORRECT


async def _question_of_the_day(session, today: dt.date, market: str) -> QuizQuestion | None:
    ids = list(
        await session.scalars(
            select(QuizQuestion.id)
            .where(QuizQuestion.market == market, QuizQuestion.is_active.is_(True))
            .order_by(QuizQuestion.id)
        )
    )
    if not ids:
        return None
    return await session.get(QuizQuestion, ids[question_index_for_day(today, len(ids))])


@router.get("/today")
async def today(
    user: CurrentUser,
    tenant: CurrentTenant,
    session: DbSession,
    locale: CurrentLocale,
) -> QuizToday:
    day = to_market_tz(dt.datetime.now(dt.UTC), market=tenant.market).date()
    q = await _question_of_the_day(session, day, tenant.market)
    if q is None:
        raise HTTPException(status_code=404, detail="No quiz configured")
    prior = await session.get(QuizAnswer, (user.id, day))
    streak, points = await _stats(session, user.id, day)
    out = QuizToday(
        question_id=q.id,
        topic=q.topic,
        question=_pick(q.question_i18n, locale),
        choices=_pick(q.choices_i18n, locale),
        answered=prior is not None,
        streak=streak,
        points=points,
    )
    if prior is not None:
        out.your_choice = prior.choice_idx
        out.correct = prior.correct
        out.answer_idx = q.answer_idx
        out.explanation = _pick(q.explanation_i18n, locale)
    return out


@router.post("/answer")
async def answer(
    body: QuizSubmit,
    user: CurrentUser,
    tenant: CurrentTenant,
    session: DbSession,
    locale: CurrentLocale,
) -> QuizToday:
    day = to_market_tz(dt.datetime.now(dt.UTC), market=tenant.market).date()
    q = await _question_of_the_day(session, day, tenant.market)
    if q is None or q.id != body.question_id:
        raise HTTPException(status_code=409, detail="That question is no longer today's quiz")
    if body.choice_idx >= len(q.choices_i18n.get("en", [])):
        raise HTTPException(status_code=422, detail="Choice out of range")
    if await session.get(QuizAnswer, (user.id, day)) is not None:
        raise HTTPException(status_code=409, detail="Already answered today")
    correct = body.choice_idx == q.answer_idx
    session.add(
        QuizAnswer(
            user_id=user.id,
            answered_on=day,
            question_id=q.id,
            choice_idx=body.choice_idx,
            correct=correct,
        )
    )
    await session.flush()
    streak, points = await _stats(session, user.id, day)
    return QuizToday(
        question_id=q.id,
        topic=q.topic,
        question=_pick(q.question_i18n, locale),
        choices=_pick(q.choices_i18n, locale),
        answered=True,
        your_choice=body.choice_idx,
        correct=correct,
        answer_idx=q.answer_idx,
        explanation=_pick(q.explanation_i18n, locale),
        streak=streak,
        points=points,
    )
