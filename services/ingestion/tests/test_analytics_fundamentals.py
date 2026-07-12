from ingestion.analytics import _comparable_eps_growth


def test_eps_growth_requires_a_positive_comparable_base() -> None:
    assert _comparable_eps_growth(12.0, 10.0) == 20.0
    assert _comparable_eps_growth(8.0, 10.0) == -20.0


def test_loss_base_is_not_presented_as_percentage_growth() -> None:
    assert _comparable_eps_growth(2.0, -2.0) is None
    assert _comparable_eps_growth(-1.0, -2.0) is None
    assert _comparable_eps_growth(2.0, 0.0) is None
    assert _comparable_eps_growth(None, 2.0) is None
