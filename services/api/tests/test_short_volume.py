from api.routers.regulatory import _short_volume_classification


def _classify(**overrides):
    values = {
        "baseline_sessions": 20,
        "latest_total_volume": 500_000,
        "ratio": 0.60,
        "deviation": 0.15,
        "z_score": 2.0,
        "activity_vs": 1.2,
    }
    values.update(overrides)
    return _short_volume_classification(**values)


def test_short_volume_elevated_requires_all_confirmation_gates() -> None:
    status, _, interpretation = _classify()
    assert status == "elevated"
    assert "does not establish bearish direction" in interpretation

    assert _classify(baseline_sessions=14)[0] == "limited_history"
    assert _classify(latest_total_volume=99_999)[0] == "normal"
    assert _classify(deviation=0.119)[0] == "normal"
    assert _classify(z_score=1.49)[0] == "normal"
    assert _classify(activity_vs=0.49)[0] == "normal"


def test_short_volume_below_norm_is_not_called_bullish() -> None:
    status, _, interpretation = _classify(ratio=0.25, deviation=-0.12, z_score=-2.0)
    assert status == "below_normal"
    assert "must not be interpreted as a bullish signal" in interpretation
