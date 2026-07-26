import datetime as dt

from bulls.analytics.dse_compression_breakout import (
    CompressionBreakoutObservation,
    CompressionBreakoutPolicy,
    build_compression_breakout_schedule,
    delay_weight_schedule,
)


def _sessions(count: int = 30) -> list[dt.date]:
    start = dt.date(2026, 1, 1)
    return [start + dt.timedelta(days=index) for index in range(count)]


def _confirmation(
    code: str,
    date: dt.date,
    *,
    evidence_mode: str = "forward",
    adv: float = 20.0,
    trigger: float = 100.0,
    risk: float = 8.0,
) -> CompressionBreakoutObservation:
    return CompressionBreakoutObservation(
        code=code,
        as_of_date=date,
        state="confirmed",
        previous_state="trigger_ready",
        evidence_mode=evidence_mode,
        methodology_version="squeeze-monitor-v3",
        setup_price=101.0,
        trigger_price=trigger,
        invalidation_price=trigger - risk,
        risk_per_share=risk,
        average_daily_value_mn=adv,
    )


def test_forward_book_excludes_reconstructed_and_pre_registration_signals() -> None:
    sessions = _sessions()
    result = build_compression_breakout_schedule(
        observations=[
            _confirmation("OLD", sessions[3], evidence_mode="forward"),
            _confirmation("REPLAY", sessions[5], evidence_mode="reconstructed"),
            _confirmation("LIVE", sessions[6], evidence_mode="forward"),
        ],
        sessions=sessions,
        evidence_mode="forward",
        signal_not_before=sessions[5],
    )

    assert list(result.target_weights) == [sessions[6], sessions[26]]
    assert set(result.target_weights[sessions[6]]) == {"LIVE"}
    assert result.target_weights[sessions[26]] == {}


def test_schedule_risk_sizes_caps_positions_and_uses_liquidity_priority() -> None:
    sessions = _sessions()
    policy = CompressionBreakoutPolicy(maximum_positions=2)
    result = build_compression_breakout_schedule(
        observations=[
            _confirmation("LOW", sessions[2], adv=3),
            _confirmation("HIGH", sessions[2], adv=30),
            _confirmation("MID", sessions[2], adv=12),
        ],
        sessions=sessions,
        policy=policy,
    )

    assert set(result.target_weights[sessions[2]]) == {"HIGH", "MID"}
    assert result.target_weights[sessions[2]]["HIGH"] == 0.09375
    assert any(item.code == "LOW" and item.reason == "position_limit" for item in result.rejections)


def test_terminal_state_removes_target_before_time_exit() -> None:
    sessions = _sessions()
    confirmation = _confirmation("FAIL", sessions[2])
    failed = confirmation.model_copy(
        update={
            "as_of_date": sessions[5],
            "state": "failed",
            "previous_state": "confirmed",
        }
    )

    result = build_compression_breakout_schedule(
        observations=[confirmation, failed],
        sessions=sessions,
    )

    assert result.target_weights[sessions[2]]
    assert result.target_weights[sessions[5]] == {}
    assert sessions[22] not in result.target_weights


def test_risk_and_liquidity_gates_fail_closed() -> None:
    sessions = _sessions()
    result = build_compression_breakout_schedule(
        observations=[
            _confirmation("ILLIQUID", sessions[2], adv=1),
            _confirmation("WIDE", sessions[2], trigger=100, risk=20),
        ],
        sessions=sessions,
    )

    assert result.target_weights == {}
    assert {item.reason for item in result.rejections} == {
        "average_daily_value_below_floor",
        "stop_distance_outside_registered_range",
    }


def test_delayed_schedule_moves_changes_by_completed_sessions() -> None:
    sessions = _sessions(10)
    schedule = {sessions[1]: {"A": 0.1}, sessions[4]: {}}

    delayed = delay_weight_schedule(schedule, sessions=sessions, delay_sessions=2)

    assert delayed == {sessions[3]: {"A": 0.1}, sessions[6]: {}}
