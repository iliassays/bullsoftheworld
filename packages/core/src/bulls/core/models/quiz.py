"""Daily quiz — gamify learning, never trading.

One market-literacy question per day (same for everyone: deterministic rotation over the active
bank). Streaks and points reward understanding; nothing here ever touches trading performance.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import JSON, Boolean, Date, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from bulls.core.db import Base


class QuizQuestion(Base):
    __tablename__ = "quiz_questions"

    id: Mapped[int] = mapped_column(primary_key=True)
    topic: Mapped[str] = mapped_column(String(32))  # valuation | market_basics | risk | ownership
    question_i18n: Mapped[dict] = mapped_column(JSON)  # {"en": ..., "bn": ...}
    choices_i18n: Mapped[dict] = mapped_column(JSON)  # {"en": [...], "bn": [...]} same order
    answer_idx: Mapped[int] = mapped_column(Integer)
    explanation_i18n: Mapped[dict] = mapped_column(JSON)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class QuizAnswer(Base):
    """One row per user per day — answering is the daily ritual the streak counts."""

    __tablename__ = "quiz_answers"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    answered_on: Mapped[dt.date] = mapped_column(Date, primary_key=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("quiz_questions.id"))
    choice_idx: Mapped[int] = mapped_column(Integer)
    correct: Mapped[bool] = mapped_column(Boolean)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
