from __future__ import annotations

import datetime as dt

from api.routers.desks import _next_evaluation, _policy_for


def test_dse_volume_desk_shows_next_real_intraday_check() -> None:
    now = dt.datetime(2026, 7, 12, 9, 0, tzinfo=dt.UTC)  # Sunday 15:00 Dhaka, after close
    policy = _policy_for("BullsOfDhakaVolume", "DSE")

    next_check = _next_evaluation(now, "DSE", policy)

    assert next_check == dt.datetime(2026, 7, 13, 11, 45, tzinfo=next_check.tzinfo)
    assert "11:45" in policy.cadence[0]
    assert "2.5x" in policy.methodology[0]


def test_dse_institution_desk_explains_monthly_source_and_weekly_check() -> None:
    now = dt.datetime(2026, 7, 12, 9, 0, tzinfo=dt.UTC)
    policy = _policy_for("BullsOfDhakaInstitution", "DSE")

    next_check = _next_evaluation(now, "DSE", policy)

    assert next_check.isoweekday() == 5
    assert (next_check.hour, next_check.minute) == (20, 10)
    assert "monthly" in policy.cadence[0]
    assert "2.0 percentage points" in policy.methodology[0]
    assert "not live fund flow" in policy.source_note[0]


def test_us_institution_desk_uses_sec_13f_policy() -> None:
    now = dt.datetime(2026, 7, 10, 12, 0, tzinfo=dt.UTC)
    policy = _policy_for("BullsOfWallStInstitution", "US")

    next_check = _next_evaluation(now, "US", policy)

    assert next_check.astimezone(dt.UTC) == dt.datetime(2026, 7, 12, 10, 0, tzinfo=dt.UTC)
    assert "Form 13F" in policy.cadence[0]
    assert "45 days" in policy.cadence[0]
