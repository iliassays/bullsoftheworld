"""Tiered DSE circuit bands — test cases straight from docs/specs/scanner.md §12."""

from __future__ import annotations

from bulls.analytics import at_circuit, circuit_band


def test_band_tiers_match_the_bsec_order() -> None:
    assert circuit_band(150.0) == 10.0
    assert circuit_band(200.0) == 10.0
    assert circuit_band(200.01) == 8.75
    assert circuit_band(500.01) == 7.5
    assert circuit_band(1000.01) == 6.25
    assert circuit_band(2000.01) == 5.0
    assert circuit_band(5000.01) == 3.75


def test_at_circuit_uses_the_tier_not_a_flat_ten_percent() -> None:
    # a ৳300 stock locks at 8.75% — the old flat 9.7% check missed this entirely
    assert at_circuit(8.5, 300.0)
    assert not at_circuit(8.0, 300.0)
    # a ৳150 stock needs ~10% (within tick-rounding tolerance)
    assert at_circuit(9.75, 150.0)
    assert not at_circuit(8.5, 150.0)
    # lower circuit symmetrical
    assert at_circuit(-4.8, 2500.0)  # 5% band tier
