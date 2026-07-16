from dataclasses import dataclass

import pytest

from bulls.analytics.agent_performance import calculate_agent_performance


@dataclass
class Trade:
    code: str
    side: str
    quantity: int
    price: float
    fee: float


def test_fifo_performance_separates_realized_and_unrealized_pnl() -> None:
    result = calculate_agent_performance(
        [
            Trade("ABC", "buy", 10, 100.0, 4.0),
            Trade("ABC", "buy", 5, 110.0, 2.2),
            Trade("ABC", "sell", 12, 120.0, 5.76),
        ],
        {"ABC": 115.0},
    )

    # FIFO sell: 10 shares from the first lot and 2 from the second, with both-side fees.
    assert result.realized_pnl == pytest.approx(209.36)
    assert result.unrealized_pnl == pytest.approx(13.68)
    assert result.open_cost == pytest.approx(331.32)
    assert result.fees == pytest.approx(11.96)
    assert result.closed_trades == 1
    assert result.win_rate == 100.0


def test_missing_mark_keeps_unrealized_pnl_unknown() -> None:
    result = calculate_agent_performance([Trade("ABC", "buy", 2, 10.0, 0.08)], {})
    assert result.realized_pnl == 0
    assert result.unrealized_pnl is None
    assert result.open_cost == pytest.approx(20.08)


def test_sell_without_inventory_is_rejected() -> None:
    with pytest.raises(ValueError, match="exceeds FIFO inventory"):
        calculate_agent_performance([Trade("ABC", "sell", 1, 10.0, 0.04)], {})
