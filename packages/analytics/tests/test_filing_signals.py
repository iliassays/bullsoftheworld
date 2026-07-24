"""Tests for the System A filings signal layer (Phase 12 / Phase 8 filter stack)."""

from __future__ import annotations

import datetime as dt

import pytest

from bulls.analytics.filing_signals import (
    ActivistEvent,
    ActivistRoster,
    InsiderTrade,
    classify_insider,
    classify_insiders,
    detect_clusters,
    has_plausible_transaction_clock,
    qualifying_activist_events,
    qualifying_purchases,
    qualifying_purchases_point_in_time,
)


def _trade(
    *,
    owner: int = 1,
    issuer: int = 100,
    day: dt.date | None = None,
    disseminated: dt.datetime | None = None,
    code: str = "P",
    shares: float = 1000.0,
    price: float | None = 10.0,
    plan: bool = False,
    officer: bool = False,
) -> InsiderTrade:
    day = day or dt.date(2026, 3, 2)
    return InsiderTrade(
        issuer_cik=issuer,
        issuer_symbol="TEST",
        owner_cik=owner,
        transaction_date=day,
        # Default dissemination is two business-ish days after the trade, as Form 4 requires.
        disseminated_at=disseminated or dt.datetime(day.year, day.month, day.day, 21, tzinfo=dt.UTC)
        + dt.timedelta(days=2),
        code=code,
        shares=shares,
        price_per_share=price,
        is_10b5_1_plan=plan,
        is_officer=officer,
    )


# --- Cohen-Malloy-Pomorski routine/opportunistic classifier --------------------------------


def test_same_month_three_consecutive_years_is_routine() -> None:
    dates = [dt.date(2023, 3, 10), dt.date(2024, 3, 12), dt.date(2025, 3, 9)]
    assert classify_insider(dates) == "routine"


def test_scattered_months_are_opportunistic() -> None:
    dates = [dt.date(2023, 2, 10), dt.date(2024, 7, 12), dt.date(2025, 11, 9)]
    assert classify_insider(dates) == "opportunistic"


def test_same_month_but_non_consecutive_years_is_not_routine() -> None:
    # A gap year breaks the calendar pattern the classifier is looking for.
    dates = [dt.date(2021, 3, 10), dt.date(2023, 3, 12), dt.date(2025, 3, 9)]
    assert classify_insider(dates) == "opportunistic"


def test_thin_history_is_unclassified_not_guessed() -> None:
    assert classify_insider([dt.date(2025, 3, 10), dt.date(2026, 3, 11)]) == "unclassified"


def test_routine_pattern_survives_extra_opportunistic_trades() -> None:
    # A March-every-year insider stays routine even with other scattered activity.
    dates = [
        dt.date(2023, 3, 10),
        dt.date(2024, 3, 12),
        dt.date(2025, 3, 9),
        dt.date(2025, 8, 1),
    ]
    assert classify_insider(dates) == "routine"


def test_classifier_rejects_degenerate_threshold() -> None:
    with pytest.raises(ValueError):
        classify_insider([dt.date(2025, 1, 1)], minimum_years=1)


def test_classify_insiders_uses_full_history_including_sales() -> None:
    history = [
        _trade(owner=7, day=dt.date(2023, 5, 3), code="S"),
        _trade(owner=7, day=dt.date(2024, 5, 6), code="S"),
        _trade(owner=7, day=dt.date(2025, 5, 4), code="P"),
    ]
    # The routine pattern lives in the scheduled sales; ignoring them would misclassify.
    assert classify_insiders(history)[7] == "routine"


def test_impossible_form_4_dates_are_rejected_before_classification() -> None:
    accepted = dt.datetime(2026, 3, 4, 21, tzinfo=dt.UTC)

    assert not has_plausible_transaction_clock(dt.date(24, 3, 2), accepted)
    assert not has_plausible_transaction_clock(dt.date(2026, 3, 5), accepted)
    assert has_plausible_transaction_clock(dt.date(2026, 3, 2), accepted)

    invalid = _trade(
        owner=7,
        day=dt.date(2027, 3, 2),
        disseminated=accepted,
    )
    assert classify_insiders([invalid]) == {}
    assert qualifying_purchases([invalid], {7: "opportunistic"}) == []


def test_purchase_classification_never_uses_later_filings() -> None:
    oldest = _trade(
        owner=1,
        day=dt.date(2023, 1, 10),
        disseminated=dt.datetime(2023, 1, 12, tzinfo=dt.UTC),
        code="S",
    )
    early = _trade(
        owner=1,
        day=dt.date(2024, 1, 10),
        disseminated=dt.datetime(2024, 1, 12, tzinfo=dt.UTC),
        code="P",
    )
    future = _trade(
        owner=1,
        day=dt.date(2025, 1, 10),
        disseminated=dt.datetime(2025, 1, 12, tzinfo=dt.UTC),
        code="S",
    )

    result = qualifying_purchases_point_in_time(
        [future, early, oldest],
        include_unclassified=True,
    )

    assert early in result
    assert future not in result


# --- the Form 4 filter stack ---------------------------------------------------------------


def test_only_open_market_purchases_survive() -> None:
    trades = [
        _trade(owner=1, code="P"),
        _trade(owner=1, code="S"),  # sale: no signal
        _trade(owner=1, code="A"),  # award
        _trade(owner=1, code="M"),  # option exercise
    ]
    kept = qualifying_purchases(trades, {1: "opportunistic"})
    assert [t.code for t in kept] == ["P"]


def test_scheduled_plan_trades_are_dropped() -> None:
    trades = [_trade(owner=1, plan=True), _trade(owner=1, plan=False)]
    kept = qualifying_purchases(trades, {1: "opportunistic"})
    assert len(kept) == 1
    assert kept[0].is_10b5_1_plan is False


def test_routine_insiders_are_dropped() -> None:
    trades = [_trade(owner=1), _trade(owner=2)]
    kept = qualifying_purchases(trades, {1: "routine", 2: "opportunistic"})
    assert [t.owner_cik for t in kept] == [2]


def test_unclassified_insiders_are_excluded_by_default_and_opt_in() -> None:
    trades = [_trade(owner=3)]
    assert qualifying_purchases(trades, {3: "unclassified"}) == []
    assert len(qualifying_purchases(trades, {3: "unclassified"}, include_unclassified=True)) == 1


def test_zero_share_rows_are_ignored() -> None:
    assert qualifying_purchases([_trade(owner=1, shares=0.0)], {1: "opportunistic"}) == []


# --- clustering, on dissemination time -----------------------------------------------------


def test_cluster_groups_multiple_insiders_within_the_window() -> None:
    base = dt.datetime(2026, 3, 2, 21, tzinfo=dt.UTC)
    purchases = [
        _trade(owner=1, disseminated=base),
        _trade(owner=2, disseminated=base + dt.timedelta(days=5)),
        _trade(owner=3, disseminated=base + dt.timedelta(days=10)),
    ]
    clusters = detect_clusters(purchases, window_days=30)
    assert len(clusters) == 1
    cluster = clusters[0]
    assert cluster.distinct_insiders == 3
    assert cluster.trade_count == 3
    # Signal time is the LAST filing: you could not have acted on the cluster before it existed.
    assert cluster.signal_at == base + dt.timedelta(days=10)
    assert cluster.first_disseminated_at == base


def test_filings_outside_the_window_form_separate_clusters() -> None:
    base = dt.datetime(2026, 3, 2, 21, tzinfo=dt.UTC)
    purchases = [
        _trade(owner=1, disseminated=base),
        _trade(owner=2, disseminated=base + dt.timedelta(days=45)),
    ]
    clusters = detect_clusters(purchases, window_days=30)
    assert len(clusters) == 2
    assert all(c.distinct_insiders == 1 for c in clusters)


def test_minimum_insiders_filters_out_singletons() -> None:
    base = dt.datetime(2026, 3, 2, 21, tzinfo=dt.UTC)
    purchases = [
        _trade(owner=1, issuer=100, disseminated=base),
        _trade(owner=1, issuer=200, disseminated=base),
        _trade(owner=2, issuer=200, disseminated=base + dt.timedelta(days=2)),
    ]
    clusters = detect_clusters(purchases, window_days=30, minimum_insiders=2)
    assert [c.issuer_cik for c in clusters] == [200]


def test_cluster_separates_issuers() -> None:
    base = dt.datetime(2026, 3, 2, 21, tzinfo=dt.UTC)
    purchases = [
        _trade(owner=1, issuer=100, disseminated=base),
        _trade(owner=2, issuer=200, disseminated=base),
    ]
    assert {c.issuer_cik for c in detect_clusters(purchases)} == {100, 200}


def test_unpriced_trades_leave_value_unknown_not_zero() -> None:
    base = dt.datetime(2026, 3, 2, 21, tzinfo=dt.UTC)
    cluster = detect_clusters([_trade(owner=1, price=None, disseminated=base)])[0]
    assert cluster.total_value is None
    assert cluster.total_shares == 1000.0


def test_cluster_flags_officer_participation() -> None:
    base = dt.datetime(2026, 3, 2, 21, tzinfo=dt.UTC)
    plain = detect_clusters([_trade(owner=1, disseminated=base)])[0]
    with_officer = detect_clusters([_trade(owner=1, officer=True, disseminated=base)])[0]
    assert plain.includes_officer_or_director is False
    assert with_officer.includes_officer_or_director is True


def test_window_days_must_be_positive() -> None:
    with pytest.raises(ValueError):
        detect_clusters([], window_days=0)


# --- activist roster -----------------------------------------------------------------------


def _event(
    *, cik: int | None, name: str | None, amendment: bool = False, accession: str = "a"
) -> ActivistEvent:
    return ActivistEvent(
        accession_number=accession,
        subject_cik=999,
        subject_name="TARGET CO",
        filed_by_cik=cik,
        filed_by_name=name,
        form="SCHEDULE 13D/A" if amendment else "SCHEDULE 13D",
        signal_at=dt.datetime(2026, 3, 2, 21, tzinfo=dt.UTC),
        is_amendment=amendment,
    )


def test_roster_matches_by_cik_and_by_name_fragment() -> None:
    roster = ActivistRoster(ciks=frozenset({902012}), name_fragments=("third point",))
    assert roster.matches(cik=902012, name=None) is True
    assert roster.matches(cik=None, name="Third Point LLC") is True
    assert roster.matches(cik=None, name="THIRD POINT LLC") is True
    assert roster.matches(cik=123, name="Unknown Capital") is False


def test_only_rostered_filers_produce_signals() -> None:
    roster = ActivistRoster(ciks=frozenset({902012}))
    events = [
        _event(cik=902012, name="Elliott", accession="keep"),
        _event(cik=555, name="Random LLC", accession="drop"),
    ]
    assert [e.accession_number for e in qualifying_activist_events(events, roster)] == ["keep"]


def test_amendments_are_excluded_by_default() -> None:
    roster = ActivistRoster(ciks=frozenset({902012}))
    events = [
        _event(cik=902012, name="Elliott", amendment=True, accession="amend"),
        _event(cik=902012, name="Elliott", amendment=False, accession="new"),
    ]
    assert [e.accession_number for e in qualifying_activist_events(events, roster)] == ["new"]
    assert len(qualifying_activist_events(events, roster, include_amendments=True)) == 2
