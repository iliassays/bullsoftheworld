"""On-demand SEC refresh report: correct exit code and coverage delta wording."""

from __future__ import annotations

import pytest

from ingestion import us_sec_refresh


@pytest.mark.asyncio
async def test_run_reports_success_and_exits_zero_when_watchdog_is_clean(monkeypatch) -> None:
    monkeypatch.setattr(us_sec_refresh, "_ready_symbol_count", _fake(367))
    monkeypatch.setattr(
        us_sec_refresh,
        "_coverage_snapshot",
        _fake_sequence([{"sec_edgar": 65}, {"sec_edgar": 367}]),
    )
    monkeypatch.setattr(us_sec_refresh, "refresh_sec_evidence", _fake({"symbols_requested": 377}))
    monkeypatch.setattr(us_sec_refresh, "_database_problems", _fake([]))
    sent: list[str] = []

    async def fake_send(lines: list[str]) -> None:
        sent.extend(lines)

    monkeypatch.setattr(us_sec_refresh, "_send_report", fake_send)

    exit_code = await us_sec_refresh.run(include_13f=False)

    assert exit_code == 0
    assert any("65 -> 367" in line for line in sent)
    assert any("all US data health checks pass" in line for line in sent)


@pytest.mark.asyncio
async def test_run_surfaces_remaining_problems_and_exits_nonzero(monkeypatch) -> None:
    monkeypatch.setattr(us_sec_refresh, "_ready_symbol_count", _fake(367))
    monkeypatch.setattr(
        us_sec_refresh,
        "_coverage_snapshot",
        _fake_sequence([{"sec_edgar": 65}, {"sec_edgar": 200}]),
    )
    monkeypatch.setattr(us_sec_refresh, "refresh_sec_evidence", _fake({"symbols_requested": 377}))
    monkeypatch.setattr(
        us_sec_refresh, "_database_problems", _fake(["SEC EDGAR covers 200/367 ready symbols"])
    )
    sent: list[str] = []
    monkeypatch.setattr(us_sec_refresh, "_send_report", _capture(sent))

    exit_code = await us_sec_refresh.run(include_13f=False)

    assert exit_code == 1
    assert any("Remaining watchdog problems" in line for line in sent)


def _fake(value):
    async def inner(*args, **kwargs):
        return value

    return inner


def _fake_sequence(values: list):
    iterator = iter(values)

    async def inner(*args, **kwargs):
        return next(iterator)

    return inner


def _capture(sink: list[str]):
    async def inner(lines: list[str]) -> None:
        sink.extend(lines)

    return inner
