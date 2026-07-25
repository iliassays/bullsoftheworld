from __future__ import annotations

import datetime as dt
import re

import pytest

from bulls.analytics.fintel_insider_algo import (
    InsiderTrade,
    evaluate_fintel_insider_algo,
    is_open_market_purchase,
    routine_owner_ciks,
)

AS_OF = dt.date(2026, 7, 25)


def trade(
    owner: int,
    transaction: str | None = "2026-07-01",
    *,
    known: str | None = None,
    code: str = "P",
    acquired: str = "A",
    shares: float | None = 1_000.0,
    price: float | None = 10.0,
    owned_after: float | None = 10_000.0,
    officer: bool = True,
    director: bool = False,
    ten_percent: bool = False,
    plan: bool = False,
) -> InsiderTrade:
    """A qualifying officer purchase by default; each test perturbs one field."""
    transaction_date = dt.date.fromisoformat(transaction) if transaction else None
    # Filed two days after the trade, which is the Section 16 deadline.
    if known is None:
        base = transaction_date or dt.date(2026, 7, 1)
        known_at = dt.datetime.combine(base + dt.timedelta(days=2), dt.time(21, 0), tzinfo=dt.UTC)
    else:
        known_at = dt.datetime.fromisoformat(known).replace(tzinfo=dt.UTC)
    return InsiderTrade(
        owner_cik=owner,
        known_at=known_at,
        transaction_date=transaction_date,
        code=code,
        acquired_disposed=acquired,
        shares=shares,
        price_per_share=price,
        shares_owned_after=owned_after,
        is_officer=officer,
        is_director=director,
        is_ten_percent_owner=ten_percent,
        is_10b5_1_plan=plan,
    )


def test_only_open_market_purchases_are_opinions() -> None:
    assert is_open_market_purchase(trade(1))
    # Grant, option exercise, tax withholding, sale: compensation or exit, not a view.
    for code in ("A", "M", "F", "S", "G"):
        assert not is_open_market_purchase(trade(1, code=code))
    assert not is_open_market_purchase(trade(1, acquired="D"))
    assert not is_open_market_purchase(trade(1, shares=0))
    assert not is_open_market_purchase(trade(1, shares=None))


def test_eligibility_gates_on_known_at_not_transaction_date() -> None:
    """A trade dated inside the window but not yet filed must not count."""
    rows = [trade(1, "2026-07-20", known="2026-07-28T21:00:00")]

    read = evaluate_fintel_insider_algo(rows, as_of=AS_OF)

    # Nothing was public by as_of, so there is no read at all — not a zero.
    assert read is None


def test_10b5_1_plan_rows_are_excluded_and_counted() -> None:
    rows = [trade(1, plan=True), trade(2, plan=True)]

    read = evaluate_fintel_insider_algo(rows, as_of=AS_OF)

    assert read is not None
    assert read.band == "no_signal"
    assert read.qualifying_buyers == 0
    assert read.excluded_plan_rows == 2
    assert any("10b5-1" in line for line in read.evidence)


def test_calendar_routine_buyer_is_excluded() -> None:
    """Same calendar month three consecutive years is a programme, not a view."""
    history = [
        trade(1, "2024-07-08"),
        trade(1, "2025-07-09"),
        trade(1, "2026-07-07"),
    ]

    assert routine_owner_ciks(history, as_of=AS_OF) == frozenset({1})

    read = evaluate_fintel_insider_algo(history, as_of=AS_OF)
    assert read is not None
    assert read.qualifying_buyers == 0
    assert read.excluded_routine_buyers == 1


def test_non_consecutive_years_in_the_same_month_are_not_routine() -> None:
    history = [trade(1, "2022-07-08"), trade(1, "2024-07-09"), trade(1, "2026-07-07")]

    assert routine_owner_ciks(history, as_of=AS_OF) == frozenset()


def test_routine_classification_reads_history_beyond_the_window() -> None:
    """The 90-day window cannot see three years of pattern; the classifier must."""
    history = [trade(1, "2024-07-08"), trade(1, "2025-07-09"), trade(1, "2026-07-07")]

    read = evaluate_fintel_insider_algo(history, as_of=AS_OF, window_days=90)

    assert read is not None
    assert read.excluded_routine_buyers == 1


def test_bands_track_distinct_buyers() -> None:
    def band_for(owners: list[int]) -> str:
        read = evaluate_fintel_insider_algo([trade(owner) for owner in owners], as_of=AS_OF)
        assert read is not None
        return read.band

    assert band_for([1]) == "single_buyer"
    assert band_for([1, 2]) == "cluster"
    assert band_for([1, 2, 3]) == "strong_cluster"
    # Two purchases by one insider are still one opinion.
    assert band_for([1, 1]) == "single_buyer"


def test_ten_percent_owners_excluded_by_default_but_optional() -> None:
    rows = [trade(1, officer=False, director=False, ten_percent=True)]

    default = evaluate_fintel_insider_algo(rows, as_of=AS_OF)
    assert default is not None
    assert default.qualifying_buyers == 0
    assert default.excluded_ten_percent_buyers == 1

    opted_in = evaluate_fintel_insider_algo(rows, as_of=AS_OF, include_ten_percent_owners=True)
    assert opted_in is not None
    assert opted_in.qualifying_buyers == 1


def test_undated_rows_abstain_rather_than_defaulting_into_the_window() -> None:
    """Rows the repair migration nulled must not be silently treated as in-window."""
    rows = [trade(1, None, known="2026-07-02T21:00:00")]

    read = evaluate_fintel_insider_algo(rows, as_of=AS_OF)

    assert read is not None
    assert read.qualifying_buyers == 0
    assert read.excluded_undated_rows == 1


def test_purchases_outside_the_window_are_ignored() -> None:
    rows = [trade(1, "2026-01-05")]

    read = evaluate_fintel_insider_algo(rows, as_of=AS_OF, window_days=90)

    assert read is not None
    assert read.qualifying_buyers == 0
    assert read.excluded_undated_rows == 0


def test_value_and_conviction_are_aggregated_per_owner() -> None:
    rows = [
        trade(1, "2026-07-01", shares=1_000, price=10.0, owned_after=4_000),
        trade(2, "2026-07-02", shares=2_000, price=20.0, owned_after=8_000),
    ]

    read = evaluate_fintel_insider_algo(rows, as_of=AS_OF)

    assert read is not None
    assert read.aggregate_value_usd == pytest.approx(50_000.0)
    assert read.value_is_partial is False
    # Both raised their holding by 25%; the median of two equal values is that value.
    assert read.median_stake_increase_pct == pytest.approx(25.0)
    assert read.first_purchase_on == dt.date(2026, 7, 1)
    assert read.last_purchase_on == dt.date(2026, 7, 2)


def test_missing_price_makes_the_value_a_disclosed_floor() -> None:
    rows = [trade(1, "2026-07-01", price=10.0), trade(2, "2026-07-02", price=None)]

    read = evaluate_fintel_insider_algo(rows, as_of=AS_OF)

    assert read is not None
    assert read.aggregate_value_usd == pytest.approx(10_000.0)
    assert read.value_is_partial is True
    assert any("disclosed a price" in line for line in read.evidence)


def test_thin_history_is_reported_not_hidden() -> None:
    rows = [trade(1, "2026-07-01")]

    read = evaluate_fintel_insider_algo(rows, as_of=AS_OF)
    assert read is not None
    assert read.qualifying_buyers == 1
    assert read.thin_history_buyers == 1

    strict = evaluate_fintel_insider_algo(rows, as_of=AS_OF, include_thin_history=False)
    assert strict is not None
    assert strict.qualifying_buyers == 0
    assert strict.thin_history_buyers == 1


def test_score_is_bounded_and_breadth_dominates() -> None:
    one = evaluate_fintel_insider_algo([trade(1)], as_of=AS_OF)
    three = evaluate_fintel_insider_algo([trade(1), trade(2), trade(3)], as_of=AS_OF)

    assert one is not None and three is not None
    assert 0 < one.score < three.score <= 100

    # A maximal cluster: four officers and directors, big cheques, large stake increases.
    maximal = evaluate_fintel_insider_algo(
        [
            trade(
                owner,
                "2026-07-01",
                shares=100_000,
                price=50.0,
                owned_after=150_000,
                officer=True,
                director=True,
            )
            for owner in (1, 2, 3, 4)
        ],
        as_of=AS_OF,
    )
    assert maximal is not None
    assert maximal.score == 100


def test_empty_input_returns_none_but_filtered_input_returns_a_zero_read() -> None:
    assert evaluate_fintel_insider_algo([], as_of=AS_OF) is None

    # Distinguishing "no data" from "looked, found nothing" is the point.
    filtered = evaluate_fintel_insider_algo([trade(1, code="S", acquired="D")], as_of=AS_OF)
    assert filtered is not None
    assert filtered.band == "no_signal"
    assert filtered.score == 0
    assert filtered.known_through is not None


def test_evidence_never_recommends() -> None:
    """Descriptive-only is a hard platform rule: the evidence states filings, not advice."""
    read = evaluate_fintel_insider_algo([trade(1), trade(2)], as_of=AS_OF)

    assert read is not None
    text = " ".join(read.evidence).lower()
    # Whole words only — "buyers" and "bought" are descriptions of what was filed.
    for banned in ("buy", "sell", "hold", "target", "should", "recommend", "undervalued"):
        assert not re.search(rf"\b{banned}\b", text), f"advice word {banned!r} in {text!r}"
