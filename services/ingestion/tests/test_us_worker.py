from __future__ import annotations

import datetime as dt
import json
from types import SimpleNamespace

import pytest

import ingestion.us_worker as us_worker
from ingestion.history import _is_ready
from ingestion.us_worker import (
    _chain_lock_key,
    _completion_key,
    _resolve_options_inbox_file,
    eod_run_state_key,
    most_recent_due_session,
    run_us_eod_chain,
)


class _Redis:
    def __init__(self, values: dict[str, str] | None = None) -> None:
        self.values = values or {}

    async def get(self, key: str):
        return self.values.get(key)

    async def set(self, key: str, value: str, *, nx: bool = False, ex: int | None = None):
        del ex
        if nx and key in self.values:
            return None
        self.values[key] = value
        return True

    async def delete(self, key: str) -> None:
        self.values.pop(key, None)

    async def eval(self, script: str, key_count: int, key: str, token: str) -> int:
        del script, key_count
        if self.values.get(key) != token:
            return 0
        self.values.pop(key)
        return 1


def _utc(year: int, month: int, day: int, hour: int, minute: int = 0) -> dt.datetime:
    return dt.datetime(year, month, day, hour, minute, tzinfo=dt.UTC)


def test_due_session_waits_for_eod_publication_window() -> None:
    # 2026-07-09 closes at 20:00 UTC; before 21:30, the prior session is still the due one.
    assert most_recent_due_session(_utc(2026, 7, 9, 21, 29)) == dt.date(2026, 7, 8)
    assert most_recent_due_session(_utc(2026, 7, 9, 21, 30)) == dt.date(2026, 7, 9)


def test_due_session_handles_weekends_and_early_closes() -> None:
    assert most_recent_due_session(_utc(2026, 7, 12, 12)) == dt.date(2026, 7, 10)
    # 2026-11-27 closes at 18:00 UTC, so its EOD window opens at 19:30 UTC.
    assert most_recent_due_session(_utc(2026, 11, 27, 19, 30)) == dt.date(2026, 11, 27)


def test_us_publication_readiness_requires_depth_and_freshness() -> None:
    end = dt.date(2026, 7, 9)
    assert _is_ready(252, end, end)
    assert not _is_ready(251, end, end)
    assert not _is_ready(252, dt.date(2026, 6, 28), end)


def test_eod_completion_marker_is_tenant_and_session_specific() -> None:
    assert _completion_key(dt.date(2026, 7, 9)) == (
        "ingestion:bullsofwallst:eod-complete:v2:2026-07-09"
    )


def test_eod_runtime_keys_are_tenant_session_and_version_specific() -> None:
    day = dt.date(2026, 7, 31)
    assert eod_run_state_key(day) == "ingestion:bullsofwallst:eod-run:v2:2026-07-31"
    assert _chain_lock_key(day) == "ingestion:bullsofwallst:eod-lock:v2:2026-07-31"


@pytest.mark.asyncio
async def test_eod_revalidates_stale_marker_and_retries_only_missing_symbols(monkeypatch) -> None:
    day = dt.date(2026, 7, 31)
    redis = _Redis({_completion_key(day): "1"})
    requested: list[str] = []

    async def fake_coverage(_day: dt.date) -> tuple[int, int]:
        return 100, 80

    async def fake_missing(_day: dt.date) -> list[str]:
        return ["MISS"]

    async def fake_collect(market: str, *, days: int, codes) -> dict[str, int]:
        assert market == "US"
        assert days > 0
        requested.extend(codes)
        return {"bars_upserted": 0, "symbols": 1, "symbols_with_data": 0}

    monkeypatch.setattr(us_worker, "most_recent_due_session", lambda _now: day)
    monkeypatch.setattr(us_worker, "_coverage", fake_coverage)
    monkeypatch.setattr(us_worker, "_analytics_date", lambda: _async_value(day))
    monkeypatch.setattr(us_worker, "_missing_ready_codes", fake_missing)
    monkeypatch.setattr(us_worker, "collect", fake_collect)
    monkeypatch.setattr(
        us_worker,
        "get_settings",
        lambda: SimpleNamespace(us_eod_min_coverage=0.90),
    )

    result = await run_us_eod_chain({"redis": redis})

    assert result.startswith("retry_pending:")
    assert requested == ["MISS"]
    assert _completion_key(day) not in redis.values
    state = json.loads(redis.values[eod_run_state_key(day)])
    assert state["status"] == "retry_pending"
    assert state["missing"] == 20
    assert _chain_lock_key(day) not in redis.values


async def _async_value(value):
    return value


def test_options_worker_input_stays_inside_configured_inbox(tmp_path) -> None:
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    delivery = inbox / "delivery.zip"
    delivery.write_bytes(b"PK")

    assert _resolve_options_inbox_file(str(inbox), delivery.name) == delivery
    with pytest.raises(ValueError, match="basename"):
        _resolve_options_inbox_file(str(inbox), "../delivery.zip")

    outside = tmp_path / "outside.zip"
    outside.write_bytes(b"PK")
    (inbox / "escaped.zip").symlink_to(outside)
    with pytest.raises(ValueError, match="escaped"):
        _resolve_options_inbox_file(str(inbox), "escaped.zip")
