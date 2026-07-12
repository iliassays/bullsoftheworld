import datetime as dt

from ingestion.growth_retention import BETA_FEEDBACK_RETENTION_DAYS, RAW_EVENT_RETENTION_DAYS


def test_raw_growth_retention_is_bounded() -> None:
    assert RAW_EVENT_RETENTION_DAYS == 180
    assert dt.timedelta(days=RAW_EVENT_RETENTION_DAYS) < dt.timedelta(days=365)
    assert BETA_FEEDBACK_RETENTION_DAYS == 365
