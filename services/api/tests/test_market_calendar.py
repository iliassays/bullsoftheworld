from api.routers.market import EarningsEventOut, _bounded_calendar_events


def event(code: str, date: str) -> EarningsEventOut:
    return EarningsEventOut(code=code, name_en=code, meeting_date=date)


def test_calendar_is_bounded_per_day_and_preserves_true_totals() -> None:
    events = [event(f"A{i}", "2026-08-03") for i in range(6)] + [
        event(f"B{i}", "2026-08-04") for i in range(2)
    ]

    result = _bounded_calendar_events(events, per_day=3)

    first_day = [item for item in result if item.meeting_date == "2026-08-03"]
    second_day = [item for item in result if item.meeting_date == "2026-08-04"]
    assert len(first_day) == 3
    assert {item.day_total for item in first_day} == {6}
    assert len(second_day) == 2
    assert {item.day_total for item in second_day} == {2}


def test_calendar_sample_prioritizes_larger_companies_then_code() -> None:
    events = [event("SMALL", "2026-08-03"), event("MEGA", "2026-08-03"), event("MID", "2026-08-03")]

    result = _bounded_calendar_events(
        events,
        per_day=2,
        priority_by_code={"SMALL": 10, "MID": 100, "MEGA": 1_000},
    )

    assert [item.code for item in result] == ["MEGA", "MID"]
    assert all(item.day_total == 3 for item in result)
