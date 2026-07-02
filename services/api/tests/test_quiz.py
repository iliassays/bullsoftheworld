"""Quiz logic unit tests (pure) + DB-gated endpoint flow.

DB_TESTS=1 uv run pytest -k quiz
"""

from __future__ import annotations

import datetime as dt
import os
import uuid

import pytest
from fastapi.testclient import TestClient

from api.routers.quiz import current_streak, question_index_for_day


def test_question_rotation_is_deterministic_and_covers_bank() -> None:
    day = dt.date(2026, 7, 2)
    assert question_index_for_day(day, 10) == question_index_for_day(day, 10)
    # consecutive days walk the bank without gaps
    idxs = {question_index_for_day(day + dt.timedelta(days=i), 10) for i in range(10)}
    assert idxs == set(range(10))
    assert question_index_for_day(day, 0) == 0  # empty bank must not divide by zero


def test_streak_counts_consecutive_days() -> None:
    today = dt.date(2026, 7, 2)
    days = {today, today - dt.timedelta(days=1), today - dt.timedelta(days=2)}
    assert current_streak(days, today) == 3


def test_streak_not_broken_before_answering_today() -> None:
    """At 9am you haven't answered yet — yesterday's streak must still show."""
    today = dt.date(2026, 7, 2)
    days = {today - dt.timedelta(days=1), today - dt.timedelta(days=2)}
    assert current_streak(days, today) == 2


def test_streak_broken_by_a_gap() -> None:
    today = dt.date(2026, 7, 2)
    days = {today, today - dt.timedelta(days=2)}  # missed yesterday
    assert current_streak(days, today) == 1
    assert current_streak(set(), today) == 0


@pytest.mark.skipif(not os.getenv("DB_TESTS"), reason="set DB_TESTS=1 with Postgres + ingestion")
def test_quiz_flow() -> None:
    from api.main import app

    with TestClient(app) as c:
        handle = "t" + uuid.uuid4().hex[:12]
        reg = c.post(
            "/auth/register",
            json={
                "handle": handle,
                "name": "Quiz Tester",
                "email": f"{handle}@example.com",
                "password": "password123",
            },
        )
        assert reg.status_code == 201, reg.text
        hdr = {"Authorization": f"Bearer {reg.json()['access_token']}"}

        q = c.get("/quiz/today", headers=hdr).json()
        assert q["answered"] is False
        assert q["answer_idx"] is None  # never leak the answer with the question
        assert len(q["choices"]) >= 2

        r = c.post(
            "/quiz/answer",
            json={"question_id": q["question_id"], "choice_idx": 0},
            headers=hdr,
        ).json()
        assert r["answered"] is True
        assert r["answer_idx"] is not None and r["explanation"]
        assert r["streak"] >= 1

        # double answering rejected; state persists on re-fetch
        assert (
            c.post(
                "/quiz/answer",
                json={"question_id": q["question_id"], "choice_idx": 1},
                headers=hdr,
            ).status_code
            == 409
        )
        again = c.get("/quiz/today", headers=hdr).json()
        assert again["answered"] is True and again["your_choice"] == 0
