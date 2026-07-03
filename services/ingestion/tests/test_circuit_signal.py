"""Circuit desk uses the tiered bands — a ৳300 stock locking at 8.75% must fire."""

from __future__ import annotations

from ingestion.signals.factors import detect_circuit


def test_tiered_detection_fires_on_mid_tier_lock() -> None:
    sig = detect_circuit(8.6, "2026-07-03", reference_price=300.0)
    assert sig is not None and sig.event_type == "circuit_up"


def test_tiered_detection_ignores_non_lock_on_cheap_tier() -> None:
    # +8.6% on a ৳150 stock is a big move but NOT its 10% limit
    assert detect_circuit(8.6, "2026-07-03", reference_price=150.0) is None


def test_lower_circuit_and_fallback_band() -> None:
    down = detect_circuit(-9.8, "2026-07-03", reference_price=150.0)
    assert down is not None and down.event_type == "circuit_down"
    # no reference price → conservative 10% band
    assert detect_circuit(-8.0, "2026-07-03") is None
    assert detect_circuit(9.8, "2026-07-03") is not None
