from sqlalchemy import select
from sqlalchemy.dialects import postgresql

from api.news_materiality import material_dse_announcement_filter
from bulls.core.models import Announcement


def test_material_disclosure_sql_requires_decoded_outcome_facts() -> None:
    statement = select(Announcement.id).where(material_dse_announcement_filter())
    sql = str(
        statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )

    assert "eps_current" in sql
    assert "cash_pct" in sql
    assert "no_dividend" in sql
    assert "long_term" in sql
    assert "board_meeting" not in sql
    assert "corporate_action" not in sql
