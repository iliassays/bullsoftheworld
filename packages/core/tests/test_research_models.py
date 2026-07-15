from __future__ import annotations

from sqlalchemy import ForeignKeyConstraint

from bulls.core.models import (
    EvidenceDocument,
    EvidenceSpan,
    ResearchAuditEvent,
    ResearchClaim,
    ResearchClaimCitation,
    ResearchRun,
    ResearchRunEvidence,
    ResearchWorkspace,
)


def _composite_foreign_keys(model: type) -> set[tuple[tuple[str, ...], tuple[str, ...]]]:
    constraints: set[tuple[tuple[str, ...], tuple[str, ...]]] = set()
    for constraint in model.__table__.constraints:
        if not isinstance(constraint, ForeignKeyConstraint):
            continue
        local = tuple(element.parent.name for element in constraint.elements)
        remote = tuple(element.target_fullname for element in constraint.elements)
        constraints.add((local, remote))
    return constraints


def test_research_private_tables_have_non_nullable_full_security_scope() -> None:
    for model in (
        ResearchWorkspace,
        ResearchAuditEvent,
        ResearchRun,
        ResearchRunEvidence,
        ResearchClaim,
        ResearchClaimCitation,
    ):
        for column_name in ("organization_id", "tenant_id", "market"):
            assert not model.__table__.c[column_name].nullable, model.__tablename__


def test_shared_official_evidence_is_tenant_and_market_bound() -> None:
    for model in (EvidenceDocument, EvidenceSpan):
        assert "organization_id" not in model.__table__.c
        assert not model.__table__.c.tenant_id.nullable
        assert not model.__table__.c.market.nullable


def test_run_cannot_reference_a_workspace_from_another_organization() -> None:
    assert (
        ("workspace_id", "organization_id", "tenant_id", "market"),
        (
            "research_workspaces.id",
            "research_workspaces.organization_id",
            "research_workspaces.tenant_id",
            "research_workspaces.market",
        ),
    ) in _composite_foreign_keys(ResearchRun)


def test_claim_and_citation_lineage_cannot_cross_organizations() -> None:
    assert (
        ("run_id", "organization_id", "tenant_id", "market"),
        (
            "research_runs.id",
            "research_runs.organization_id",
            "research_runs.tenant_id",
            "research_runs.market",
        ),
    ) in _composite_foreign_keys(ResearchClaim)
    assert (
        ("claim_id", "organization_id", "tenant_id", "market"),
        (
            "research_claims.id",
            "research_claims.organization_id",
            "research_claims.tenant_id",
            "research_claims.market",
        ),
    ) in _composite_foreign_keys(ResearchClaimCitation)


def test_run_evidence_ledger_cannot_cross_organizations() -> None:
    constraints = _composite_foreign_keys(ResearchRunEvidence)
    assert (
        ("run_id", "organization_id", "tenant_id", "market"),
        (
            "research_runs.id",
            "research_runs.organization_id",
            "research_runs.tenant_id",
            "research_runs.market",
        ),
    ) in constraints
    assert (
        ("evidence_document_id", "tenant_id", "market"),
        (
            "research_evidence_documents.id",
            "research_evidence_documents.tenant_id",
            "research_evidence_documents.market",
        ),
    ) in constraints
    assert (
        ("evidence_span_id", "tenant_id", "market"),
        (
            "research_evidence_spans.id",
            "research_evidence_spans.tenant_id",
            "research_evidence_spans.market",
        ),
    ) in _composite_foreign_keys(ResearchClaimCitation)


def test_run_records_point_in_time_and_reproducibility_fields() -> None:
    required = {
        "knowledge_cutoff_at",
        "provider",
        "model",
        "prompt_version",
        "code_version",
        "evidence_snapshot_hash",
        "idempotency_key",
    }

    assert required <= set(ResearchRun.__table__.c.keys())


def test_evidence_records_bitemporal_source_context() -> None:
    required = {
        "effective_at",
        "published_at",
        "known_at",
        "ingested_at",
        "source_revision",
        "content_hash",
    }

    assert required <= set(EvidenceDocument.__table__.c.keys())


def test_audit_events_are_bound_to_actor_organization_and_workspace() -> None:
    constraints = _composite_foreign_keys(ResearchAuditEvent)
    assert (
        ("workspace_id", "organization_id", "tenant_id", "market"),
        (
            "research_workspaces.id",
            "research_workspaces.organization_id",
            "research_workspaces.tenant_id",
            "research_workspaces.market",
        ),
    ) in constraints
    assert (
        ("organization_id", "actor_user_id", "tenant_id", "market"),
        (
            "research_organization_memberships.organization_id",
            "research_organization_memberships.user_id",
            "research_organization_memberships.tenant_id",
            "research_organization_memberships.market",
        ),
    ) in constraints
