"""DSE circuit-breaker bands — the tiered daily price limits, shared by every consumer.

BSEC Order BSEC/Surveillance/2020-975/558 (08 Jun 2026) restored the 17 Jun 2021 tiered limits
(Order .../219) for listed securities from 09 Jun 2026. One helper so the circuit desk, scanner
boards and any future label all agree — a flat ±10% both misses real locks on pricier tiers and
over-focuses on the cheap tier where junk lives.
"""

from __future__ import annotations

# (upper price bound inclusive, band %) — reference price is the previous close.
_TIERS: tuple[tuple[float, float], ...] = (
    (200.0, 10.0),
    (500.0, 8.75),
    (1000.0, 7.5),
    (2000.0, 6.25),
    (5000.0, 5.0),
)
_TOP_BAND = 3.75  # above ৳5,000

# Locked stocks settle a touch under the band from tick rounding (a 10%-band stock closes
# ~9.7-9.95%); "at the limit" therefore means within this tolerance of the band.
AT_LIMIT_TOLERANCE_PP = 0.3


def circuit_band(reference_price: float) -> float:
    """The daily ±% limit for a stock at this reference (previous-close) price."""
    for bound, band in _TIERS:
        if reference_price <= bound:
            return band
    return _TOP_BAND


def at_circuit(change_pct: float, reference_price: float) -> bool:
    """True when today's move sits at (within tick-rounding of) the stock's daily limit."""
    return abs(change_pct) >= circuit_band(reference_price) - AT_LIMIT_TOLERANCE_PP
