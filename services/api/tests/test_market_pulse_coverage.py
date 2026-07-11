from api.routers.screener import _coverage_from_counts


def test_partial_launch_cohort_is_not_whole_market_coverage() -> None:
    assert _coverage_from_counts(60, 5000) == (60, 5000, 0.012, False)


def test_near_complete_universe_is_explicitly_complete() -> None:
    assert _coverage_from_counts(95, 100) == (95, 100, 0.95, True)


def test_empty_and_inconsistent_counts_fail_closed() -> None:
    assert _coverage_from_counts(0, 0) == (0, 0, 0.0, False)
    assert _coverage_from_counts(101, 100) == (101, 100, 1.0, True)
