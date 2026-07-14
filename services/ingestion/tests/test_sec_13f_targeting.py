from __future__ import annotations

import datetime as dt

from sqlalchemy.dialects import postgresql

from ingestion import sec_13f


def test_target_codes_are_normalized_and_deduplicated() -> None:
    assert sec_13f._normalize_codes(" nxtc,AGEN,NXTC, ") == ["AGEN", "NXTC"]
    assert sec_13f._normalize_codes(None) is None


def test_target_cli_keeps_codes_explicit() -> None:
    args = sec_13f._args(["--history-quarters", "8", "--force", "--codes", "NXTC,AGEN"])

    assert args.history_quarters == 8
    assert args.force is True
    assert args.codes == "NXTC,AGEN"


def test_target_period_delete_is_symbol_scoped() -> None:
    position_delete, summary_delete = sec_13f._period_deletes(
        dt.date(2026, 3, 31), ["AGEN", "NXTC"]
    )
    position_sql = str(
        position_delete.compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )
    summary_sql = str(
        summary_delete.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
    )

    assert "institutional_positions.code IN ('AGEN', 'NXTC')" in position_sql
    assert "institutional_holding_summaries.code IN ('AGEN', 'NXTC')" in summary_sql
