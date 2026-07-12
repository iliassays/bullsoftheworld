import pytest

from api.eod import completed_session_change_pct


def test_completed_session_change_uses_newest_and_prior_raw_close() -> None:
    assert completed_session_change_pct([110.0, 100.0]) == pytest.approx(10.0)


def test_completed_session_change_omits_thin_or_invalid_history() -> None:
    assert completed_session_change_pct([100.0]) is None
    assert completed_session_change_pct([100.0, 0.0]) is None
