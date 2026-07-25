from __future__ import annotations

import pytest

from ingestion.daily_shortlist_scan import _range_position_pct, _validated_market


def test_shortlist_scan_is_explicitly_dse_only() -> None:
    assert _validated_market("dse") == "DSE"
    with pytest.raises(ValueError, match="validated only"):
        _validated_market("US")


def test_range_position_refuses_missing_or_degenerate_ranges() -> None:
    assert _range_position_pct(50.0, 100.0, 0.0) == pytest.approx(50.0)
    assert _range_position_pct(50.0, None, 0.0) is None
    assert _range_position_pct(50.0, 10.0, 10.0) is None
