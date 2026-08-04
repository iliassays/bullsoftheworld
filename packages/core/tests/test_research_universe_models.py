from sqlalchemy import CheckConstraint, ForeignKeyConstraint

from bulls.core.models import ResearchUniverseMember, ResearchUniverseSnapshot


def _constraint_names(model, constraint_type) -> set[str]:
    return {
        constraint.name
        for constraint in model.__table__.constraints
        if isinstance(constraint, constraint_type) and constraint.name is not None
    }


def test_research_universe_snapshot_has_hard_market_and_count_boundaries() -> None:
    names = _constraint_names(ResearchUniverseSnapshot, CheckConstraint)

    assert "ck_research_universe_snapshots_market" in names
    assert "ck_research_universe_snapshots_counts" in names
    assert "ck_research_universe_snapshots_model_ready" in names
    assert "ck_research_universe_snapshots_input_hash" in names


def test_research_universe_member_cannot_cross_market_or_cohort_scope() -> None:
    names = _constraint_names(ResearchUniverseMember, CheckConstraint)
    foreign_keys = [
        constraint
        for constraint in ResearchUniverseMember.__table__.constraints
        if isinstance(constraint, ForeignKeyConstraint)
    ]

    assert "ck_research_universe_members_market" in names
    assert "ck_research_universe_members_market_cohort" in names
    assert any(
        tuple(column.name for column in constraint.columns) == ("snapshot_id", "market")
        for constraint in foreign_keys
    )
