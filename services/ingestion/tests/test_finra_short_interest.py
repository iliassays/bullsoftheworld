from __future__ import annotations

import datetime as dt

from ingestion.finra_short_interest import (
    dissemination_known_at,
    parse_rows,
    settlement_dates,
)

_HEADER = (
    "accountingYearMonthNumber,symbolCode,issueName,issuerServicesGroupExchangeCode,"
    "marketClassCode,currentShortPositionQuantity,previousShortPositionQuantity,"
    "stockSplitFlag,averageDailyVolumeQuantity,daysToCoverQuantity,revisionFlag,"
    "changePercent,changePreviousNumber,settlementDate"
)


def row(symbol: str, settlement: str, shares: str = "5331733", dtc: str = "2.12") -> str:
    return (
        f"20260630,{symbol},Some Issuer Inc.,A,NYSE,{shares},5662129,,2510868,{dtc},,"
        f"-5.84,-330396,{settlement}"
    )


def test_known_at_is_settlement_plus_eight_trading_days() -> None:
    # 2026-06-30 is a Tuesday; eight US trading days later is 2026-07-13 (July 3 holiday
    # observed and weekends excluded by the market calendar).
    assert dissemination_known_at(dt.date(2026, 6, 30)).date() == dt.date(2026, 7, 13)
    # End-of-day, so a same-day research cutoff cannot count it as known intraday.
    assert dissemination_known_at(dt.date(2026, 6, 30)).hour == 23


def test_known_at_never_precedes_settlement_and_grows_with_lag() -> None:
    settlement = dt.date(2026, 6, 30)
    assert dissemination_known_at(settlement).date() > settlement
    early = dissemination_known_at(settlement, business_days=2)
    late = dissemination_known_at(settlement, business_days=8)
    assert early < late  # a larger lag is strictly more conservative


def test_settlement_dates_are_mid_month_and_month_end_most_recent_first_sorted() -> None:
    dates = settlement_dates(dt.date(2026, 7, 25), 5)

    assert dates == [
        dt.date(2026, 5, 15),
        dt.date(2026, 5, 29),  # May 31 is a Sunday -> rolls back to the prior trading day
        dt.date(2026, 6, 15),
        dt.date(2026, 6, 30),
        dt.date(2026, 7, 15),
    ]
    assert all(value <= dt.date(2026, 7, 25) for value in dates)


def test_settlement_dates_never_returns_a_future_date() -> None:
    # Reference sits between the 15th and month end: the 15th is the newest eligible date.
    assert max(settlement_dates(dt.date(2026, 7, 20), 3)) == dt.date(2026, 7, 15)


def test_parse_rows_keeps_published_fields_and_drops_foreign_dates() -> None:
    payload = "\n".join(
        [_HEADER, row("AAA", "2026-06-30"), row("BBB", "2026-06-15")]
    )

    parsed = parse_rows(payload, expected=dt.date(2026, 6, 30))

    assert [item["symbol"] for item in parsed] == ["AAA"]
    assert float(parsed[0]["shares_short"]) == 5331733
    assert float(parsed[0]["days_to_cover"]) == 2.12
    assert float(parsed[0]["previous_shares_short"]) == 5662129
    assert parsed[0]["market_class"] == "NYSE"


def test_parse_rows_skips_unusable_rows_rather_than_guessing() -> None:
    payload = "\n".join(
        [
            _HEADER,
            row("", "2026-06-30"),  # no symbol
            row("CCC", "2026-06-30", shares=""),  # no short position
            row("DDD", "2026-06-30", shares="not-a-number"),
            row("EEE", "2026-06-30", dtc=""),  # missing DTC is fine; the position is what matters
        ]
    )

    parsed = parse_rows(payload, expected=dt.date(2026, 6, 30))

    assert [item["symbol"] for item in parsed] == ["EEE"]
    assert parsed[0]["days_to_cover"] is None
