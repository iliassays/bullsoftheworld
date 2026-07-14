from __future__ import annotations

import datetime as dt
from decimal import Decimal
from types import SimpleNamespace

import pytest

from ingestion.finra_short import _build_symbol_aliases, _recent_sessions, parse_cnms
from ingestion.signals.shorts import detect

HEADER = "Date|Symbol|ShortVolume|ShortExemptVolume|TotalVolume|Market"


def test_parse_cnms_preserves_fractional_volume_and_validates_trailer() -> None:
    rows = parse_cnms(
        "\n".join(
            [
                HEADER,
                "20260713|AAPL|120.500000|1.250000|300.750000|Q,N",
                # ShortVolume includes the exempt subset, so short + exempt may exceed total.
                "20260713|EMDV|0.050000|0.020000|0.057000|Q",
                "2",
            ]
        ),
        expected_date=dt.date(2026, 7, 13),
    )

    assert len(rows) == 2
    assert rows[1]["total_volume"] == Decimal("0.057000")
    assert rows[1]["short_volume"] == Decimal("0.050000")
    assert rows[1]["short_exempt_volume"] == Decimal("0.020000")


def test_finra_symbols_preserve_case_and_map_only_authoritative_aliases() -> None:
    rows = parse_cnms(
        "\n".join(
            [
                HEADER,
                "20260608|BCpC|1757|0|4007|Q",
                "20260608|BCPC|24070.127951|1680|49038.772549|B,Q,N",
                "2",
            ]
        ),
        expected_date=dt.date(2026, 6, 8),
    )
    assert [row["code"] for row in rows] == ["BCpC", "BCPC"]

    aliases = _build_symbol_aliases(
        [
            SimpleNamespace(
                symbol="BRK-B",
                raw_symbol="BRK.B",
                cqs_symbol="BRK.B",
                nasdaq_symbol="BRK-B",
            )
        ],
        {"BCPC", "BRK-B"},
    )
    assert aliases["BCPC"] == "BCPC"
    assert aliases["BRK.B"] == "BRK-B"
    assert aliases["BRK/B"] == "BRK-B"
    assert "BCpC" not in aliases


def test_finra_class_alias_maps_to_the_product_canonical_code() -> None:
    aliases = _build_symbol_aliases(
        [
            SimpleNamespace(
                symbol="BRK-B",
                raw_symbol="BRK.B",
                cqs_symbol="BRK.B",
                nasdaq_symbol="BRK-B",
            )
        ],
        {"BRK.B"},
    )

    assert aliases["BRK/B"] == "BRK.B"
    assert aliases["BRK-B"] == "BRK.B"


@pytest.mark.parametrize(
    "body",
    [
        f"{HEADER}\n20260713|AAPL|1|0|2|Q\n2",
        f"{HEADER}\n20260713|AAPL|3|0|2|Q\n1",
        f"{HEADER}\n20260713|AAPL|1|2|3|Q\n1",
        "wrong|header\n20260713|AAPL|1|0|2|Q\n1",
    ],
)
def test_parse_cnms_rejects_incomplete_or_invalid_files(body: str) -> None:
    with pytest.raises(ValueError):
        parse_cnms(body, expected_date=dt.date(2026, 7, 13))


def test_short_signal_requires_ratio_statistical_and_activity_confirmation() -> None:
    signal = detect(
        650_000,
        1_000_000,
        0.42,
        0.08,
        800_000,
        20,
        "2026-07-13",
    )
    assert signal is not None
    assert signal.z_score == pytest.approx(2.875)
    assert signal.volume_vs_norm == pytest.approx(1.25)

    assert detect(650_000, 1_000_000, 0.42, 0.20, 800_000, 20, "2026-07-13") is None
    assert detect(65_000, 100_000, 0.42, 0.08, 800_000, 20, "2026-07-13") is None


def test_default_finra_catchup_provides_a_full_baseline() -> None:
    sessions = _recent_sessions(dt.datetime(2026, 7, 14, 23, tzinfo=dt.UTC), 25)

    assert len(sessions) == 25
    assert sessions == sorted(sessions)
    assert all(day.weekday() < 5 for day in sessions)
