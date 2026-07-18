import datetime as dt

from bulls.analytics.leader_capture import LeaderFinancialFact, build_leader_evidence


def _fact(
    metric: str,
    period_end: dt.date,
    value: float,
    *,
    known_at: dt.datetime,
    accession: str,
) -> LeaderFinancialFact:
    return LeaderFinancialFact(
        code="LEAD",
        metric=metric,
        value=value,
        period_start=period_end - dt.timedelta(days=89),
        period_end=period_end,
        period_type="quarter",
        form="10-Q",
        accession_number=accession,
        source_url=f"https://www.sec.gov/Archives/{accession}",
        known_at=known_at,
        normalization_version="test-v1",
    )


def test_financial_evidence_replays_acceleration_at_filing_time() -> None:
    periods = [
        dt.date(2023, 3, 31),
        dt.date(2023, 6, 30),
        dt.date(2023, 9, 30),
        dt.date(2023, 12, 31),
        dt.date(2024, 3, 31),
        dt.date(2024, 6, 30),
    ]
    revenue = [100, 110, 120, 130, 125, 160]
    income = [10, 12, 13, 14, 15, 24]
    facts = []
    for index, period_end in enumerate(periods):
        known_at = dt.datetime.combine(
            period_end + dt.timedelta(days=45),
            dt.time(12),
            tzinfo=dt.UTC,
        )
        facts.extend(
            [
                _fact(
                    "revenue",
                    period_end,
                    revenue[index],
                    known_at=known_at,
                    accession=f"rev-{index}",
                ),
                _fact(
                    "net_income",
                    period_end,
                    income[index],
                    known_at=known_at,
                    accession=f"income-{index}",
                ),
            ]
        )

    observations = build_leader_evidence(facts)["LEAD"]

    assert len(observations) == 1
    snapshot = observations[0]
    assert snapshot.known_at == dt.datetime(2024, 8, 14, 12, tzinfo=dt.UTC)
    assert round(float(snapshot.features["revenue_growth_yoy_pct"]), 3) == 45.455
    assert round(float(snapshot.features["revenue_acceleration_pct"]), 3) == 20.455
    assert snapshot.features["reported_earnings_confirmation"] is True


def test_future_revision_does_not_mutate_earlier_evidence_snapshot() -> None:
    periods = [
        dt.date(2023, 3, 31),
        dt.date(2023, 6, 30),
        dt.date(2023, 9, 30),
        dt.date(2023, 12, 31),
        dt.date(2024, 3, 31),
        dt.date(2024, 6, 30),
    ]
    facts = [
        _fact(
            "revenue",
            period_end,
            value,
            known_at=dt.datetime.combine(
                period_end + dt.timedelta(days=40),
                dt.time(10),
                tzinfo=dt.UTC,
            ),
            accession=f"original-{index}",
        )
        for index, (period_end, value) in enumerate(
            zip(periods, [100, 110, 120, 130, 125, 160], strict=True)
        )
    ]
    facts.extend(
        _fact(
            "net_income",
            period_end,
            value,
            known_at=dt.datetime.combine(
                period_end + dt.timedelta(days=40),
                dt.time(10),
                tzinfo=dt.UTC,
            ),
            accession=f"income-{index}",
        )
        for index, (period_end, value) in enumerate(
            zip(periods, [10, 12, 13, 14, 15, 24], strict=True)
        )
    )
    facts.append(
        _fact(
            "revenue",
            periods[-1],
            180,
            known_at=dt.datetime(2025, 1, 15, 12, tzinfo=dt.UTC),
            accession="future-restatement",
        )
    )

    observations = build_leader_evidence(facts)["LEAD"]

    assert len(observations) == 2
    assert round(float(observations[0].features["revenue_growth_yoy_pct"]), 3) == 45.455
    assert round(float(observations[1].features["revenue_growth_yoy_pct"]), 3) == 63.636
    assert observations[0].known_at < observations[1].known_at
