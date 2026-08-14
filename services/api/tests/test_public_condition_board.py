from __future__ import annotations

import datetime as dt

from sqlalchemy.dialects import postgresql

from api.public_condition_board import (
    PublicConditionBoardOut,
    PublicConditionGroupOut,
    PublicConditionItemOut,
    _latest_public_session_date_query,
    _public_observation_query,
)


def test_public_condition_query_is_market_scoped_and_public_only() -> None:
    query = _public_observation_query(
        "US",
        latest_session_date=dt.date(2026, 8, 13),
        cap_tier="small",
        limit_per_condition=5,
    )
    sql = str(
        query.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
    )

    assert "research_condition_transitions.market = 'US'" in sql
    assert "symbols.market = 'US'" in sql
    assert "ticker_analytics.market = 'US'" in sql
    assert "symbols.is_active IS true" in sql
    assert "symbols.is_hidden IS false" in sql
    assert "symbols.data_status = 'ready'" in sql
    assert "ticker_analytics.cap_tier = 'small'" in sql
    assert "public_rank <= 5" in sql
    assert "PARTITION BY latest_public_condition_transitions.condition_key" in sql


def test_public_condition_freshness_ignores_hidden_or_restricted_symbols() -> None:
    sql = str(
        _latest_public_session_date_query("DSE").compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )

    assert "ticker_analytics.market = 'DSE'" in sql
    assert "symbols.market = 'DSE'" in sql
    assert "symbols.is_active IS true" in sql
    assert "symbols.is_hidden IS false" in sql
    assert "symbols.data_status = 'ready'" in sql


def test_public_condition_contract_excludes_private_atlas_fields() -> None:
    item = PublicConditionItemOut(
        code="AAPL",
        name="Apple Inc.",
        sector="Technology",
        cap_tier="mega",
        observed_on=dt.date(2026, 8, 12),
        latest_session_date=dt.date(2026, 8, 13),
        reference_close=225.0,
        latest_close=228.0,
        close_return_since_observation_pct=1.3333,
        average_daily_value_mn=8_000.0,
        evidence_mode="forward",
        is_new=False,
    )
    payload = PublicConditionBoardOut(
        market="US",
        as_of_date=dt.date(2026, 8, 13),
        generated_at=dt.datetime(2026, 8, 14, tzinfo=dt.UTC),
        methodology_version="research-conditions-v1",
        cap_tier="mega",
        groups=[
            PublicConditionGroupOut(
                key="trend_alignment",
                version="1.0.0",
                title="Trend alignment",
                category="trend context",
                why_it_matters="Context",
                limitation="Lagging",
                observed_count=1,
                new_count=0,
                items=[item],
            )
        ],
        disclaimer="Not a trade signal.",
    ).model_dump()

    serialized_item = payload["groups"][0]["items"][0]
    assert payload["market"] == "US"
    assert set(serialized_item) == {
        "code",
        "name",
        "sector",
        "cap_tier",
        "observed_on",
        "latest_session_date",
        "reference_close",
        "latest_close",
        "close_return_since_observation_pct",
        "average_daily_value_mn",
        "evidence_mode",
        "is_new",
    }
    assert not {"tenant_id", "workspace_id", "subscribed", "checks"} & set(serialized_item)
