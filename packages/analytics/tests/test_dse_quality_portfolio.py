import datetime as dt

from bulls.analytics.dse_edges import EdgeBar, ExecutionPolicy
from bulls.analytics.dse_quality_portfolio import (
    QualityPortfolioPolicy,
    QualityRebalance,
    build_quality_rebalances,
    quality_value_scores,
    simulate_quality_portfolio,
)
from bulls.analytics.dse_quality_universe import (
    QualityDividend,
    QualityFinancial,
    QualitySnapshot,
    QualityUniversePolicy,
)


def _snapshot(code: str, *, pe: float, roe: float) -> QualitySnapshot:
    return QualitySnapshot(
        code=code,
        signal_date=dt.date(2025, 1, 1),
        passes=True,
        failures=(),
        fiscal_year=2023,
        trailing_value=100_000_000,
        required_trailing_value=10_000_000,
        full_target_capacity=True,
        pe=pe,
        pb=2,
        roe_pct=roe,
        eps_retention=1,
        cash_dividend_years=3,
    )


def test_quality_value_ranking_happens_inside_the_passing_universe() -> None:
    scores = quality_value_scores(
        {
            "CHEAP": _snapshot("CHEAP", pe=8, roe=20),
            "EXPENSIVE": _snapshot("EXPENSIVE", pe=20, roe=10),
        }
    )

    assert scores["CHEAP"] > scores["EXPENSIVE"]


def _market_fixture():
    start = dt.date(2024, 1, 1)
    dates = [start + dt.timedelta(days=index) for index in range(150)]
    by_code = {}
    financials = {}
    dividends = {}
    for code_index in range(5):
        code = f"QUALITY{code_index}"
        bars = []
        for index, date in enumerate(dates):
            close = 100 + index * (0.08 + code_index * 0.01)
            bars.append(
                EdgeBar(
                    date=date,
                    open=close * 0.999,
                    high=close * 1.01,
                    low=close * 0.99,
                    close=close,
                    volume=1_000_000,
                )
            )
        by_code[code] = bars
        financials[code] = [
            QualityFinancial(fiscal_year=2020, eps=8, nav_per_share=45),
            QualityFinancial(fiscal_year=2021, eps=9, nav_per_share=48),
            QualityFinancial(fiscal_year=2022, eps=10 + code_index, nav_per_share=50),
        ]
        dividends[code] = [
            QualityDividend(year=2020, cash_pct=10),
            QualityDividend(year=2021, cash_pct=10),
            QualityDividend(year=2022, cash_pct=10),
        ]
    market_closes = {date: 5_000 + index for index, date in enumerate(dates)}
    return by_code, market_closes, financials, dividends


def test_quality_portfolio_rebalances_targets_without_event_trade_exits() -> None:
    by_code, market_closes, financials, dividends = _market_fixture()
    execution = ExecutionPolicy(
        assumed_capital=1_000_000,
        target_position_weight=0.20,
    )
    portfolio_policy = QualityPortfolioPolicy(
        rebalance_sessions=30,
        target_positions=3,
        minimum_positions=3,
        gross_target_weight=0.60,
    )
    rebalances = build_quality_rebalances(
        by_code=by_code,
        market_closes=market_closes,
        financials=financials,
        dividends=dividends,
        quality_policy=QualityUniversePolicy(minimum_history=30),
        execution_policy=execution,
        portfolio_policy=portfolio_policy,
    )
    result = simulate_quality_portfolio(
        rebalances=rebalances,
        by_code=by_code,
        market_closes=market_closes,
        execution_policy=execution,
        portfolio_policy=portfolio_policy,
    )

    assert rebalances
    assert all(item.eligible_count == 5 for item in rebalances)
    assert all(len(item.targets) == 3 for item in rebalances)
    assert result.buys >= 3
    assert result.total_return_pct > 0
    assert all(trade.reason != "stop" and trade.reason != "target" for trade in result.trades)


def test_capacity_aware_targets_respect_name_sector_and_liquidity_limits() -> None:
    by_code, market_closes, financials, dividends = _market_fixture()
    sectors = {f"QUALITY{index}": "Bank" if index < 3 else "Pharmaceuticals" for index in range(5)}
    policy = QualityPortfolioPolicy(
        target_positions=5,
        minimum_positions=5,
        gross_target_weight=0.85,
        capacity_aware_targets=True,
        maximum_position_weight=0.20,
        maximum_sector_weight=0.30,
    )
    rebalances = build_quality_rebalances(
        by_code=by_code,
        market_closes=market_closes,
        financials=financials,
        dividends=dividends,
        quality_policy=QualityUniversePolicy(minimum_history=30),
        execution_policy=ExecutionPolicy(
            assumed_capital=1_000_000,
            target_position_weight=0.20,
            maximum_adv_participation=1.0,
        ),
        portfolio_policy=policy,
        sectors=sectors,
    )

    weights = dict(rebalances[0].target_weights)
    assert sum(weights.values()) <= policy.gross_target_weight
    assert max(weights.values()) <= policy.maximum_position_weight
    assert sum(weight for code, weight in weights.items() if sectors[code] == "Bank") <= 0.30
    assert (
        sum(weight for code, weight in weights.items() if sectors[code] == "Pharmaceuticals")
        <= 0.30
    )


def test_quality_portfolio_allocates_limited_cash_independent_of_score_order() -> None:
    start = dt.date(2025, 1, 1)
    dates = [start + dt.timedelta(days=index) for index in range(4)]
    by_code = {
        code: [
            EdgeBar(date=date, open=100, high=101, low=99, close=100, volume=1_000_000)
            for date in dates
        ]
        for code in ("AAA", "ZZZ")
    }
    snapshots = (
        _snapshot("AAA", pe=10, roe=20),
        _snapshot("ZZZ", pe=10, roe=20),
    )
    policy = QualityPortfolioPolicy(
        target_positions=2,
        minimum_positions=2,
        gross_target_weight=1.0,
    )
    execution = ExecutionPolicy(
        assumed_capital=1_000,
        target_position_weight=0.5,
        maximum_adv_participation=1.0,
    )

    def run(scores: tuple[tuple[str, float], ...]):
        return simulate_quality_portfolio(
            rebalances=[
                QualityRebalance(
                    signal_date=dates[0],
                    execution_date=dates[1],
                    eligible_count=2,
                    targets=("AAA", "ZZZ"),
                    scores=scores,
                    snapshots=snapshots,
                )
            ],
            by_code=by_code,
            market_closes={date: 5_000 for date in dates},
            execution_policy=execution,
            portfolio_policy=policy,
        )

    forward = run((("AAA", 1.0), ("ZZZ", 0.5)))
    reverse = run((("ZZZ", 1.0), ("AAA", 0.5)))

    forward_shares = {trade.code: trade.shares for trade in forward.trades}
    reverse_shares = {trade.code: trade.shares for trade in reverse.trades}
    assert forward_shares == reverse_shares
