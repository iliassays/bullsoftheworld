from __future__ import annotations

from sqlalchemy import ForeignKeyConstraint

from bulls.core.models import (
    EvidenceDocument,
    EvidenceSpan,
    ResearchAccountingEvent,
    ResearchAuditEvent,
    ResearchAutomationPolicy,
    ResearchClaim,
    ResearchClaimCitation,
    ResearchDataEntitlement,
    ResearchDatasetEvaluation,
    ResearchDatasetSnapshot,
    ResearchDecisionEvent,
    ResearchInvestmentMandate,
    ResearchOutcomeObservation,
    ResearchRun,
    ResearchRunEvidence,
    ResearchShadowPortfolio,
    ResearchShadowSnapshot,
    ResearchStrategyTrial,
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
        ResearchAutomationPolicy,
        ResearchRun,
        ResearchRunEvidence,
        ResearchClaim,
        ResearchClaimCitation,
        ResearchShadowPortfolio,
        ResearchShadowSnapshot,
        ResearchOutcomeObservation,
        ResearchInvestmentMandate,
        ResearchStrategyTrial,
        ResearchDecisionEvent,
        ResearchAccountingEvent,
    ):
        for column_name in ("organization_id", "tenant_id", "market"):
            assert not model.__table__.c[column_name].nullable, model.__tablename__


def test_shared_official_evidence_is_tenant_and_market_bound() -> None:
    for model in (
        EvidenceDocument,
        EvidenceSpan,
        ResearchDataEntitlement,
        ResearchDatasetEvaluation,
        ResearchDatasetSnapshot,
    ):
        assert "organization_id" not in model.__table__.c
        assert not model.__table__.c.tenant_id.nullable
        assert not model.__table__.c.market.nullable


def test_dataset_snapshot_cannot_reference_cross_tenant_entitlement() -> None:
    assert (
        ("entitlement_id", "tenant_id", "market", "dataset_key"),
        (
            "research_data_entitlements.id",
            "research_data_entitlements.tenant_id",
            "research_data_entitlements.market",
            "research_data_entitlements.dataset_key",
        ),
    ) in _composite_foreign_keys(ResearchDatasetSnapshot)


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


def test_shadow_books_and_outcomes_cannot_cross_market_or_organization() -> None:
    assert (
        ("source_run_id", "organization_id", "tenant_id", "market"),
        (
            "research_runs.id",
            "research_runs.organization_id",
            "research_runs.tenant_id",
            "research_runs.market",
        ),
    ) in _composite_foreign_keys(ResearchShadowPortfolio)
    assert (
        ("portfolio_id", "organization_id", "tenant_id", "market"),
        (
            "research_shadow_portfolios.id",
            "research_shadow_portfolios.organization_id",
            "research_shadow_portfolios.tenant_id",
            "research_shadow_portfolios.market",
        ),
    ) in _composite_foreign_keys(ResearchShadowSnapshot)
    assert (
        ("run_id", "organization_id", "tenant_id", "market"),
        (
            "research_runs.id",
            "research_runs.organization_id",
            "research_runs.tenant_id",
            "research_runs.market",
        ),
    ) in _composite_foreign_keys(ResearchOutcomeObservation)


def test_automation_policy_is_bound_to_workspace_and_requester_scope() -> None:
    constraints = _composite_foreign_keys(ResearchAutomationPolicy)
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
        ("organization_id", "requested_by_user_id", "tenant_id", "market"),
        (
            "research_organization_memberships.organization_id",
            "research_organization_memberships.user_id",
            "research_organization_memberships.tenant_id",
            "research_organization_memberships.market",
        ),
    ) in constraints


def test_investment_governance_cannot_cross_workspace_market_or_portfolio() -> None:
    mandate_constraints = _composite_foreign_keys(ResearchInvestmentMandate)
    assert (
        ("workspace_id", "organization_id", "tenant_id", "market"),
        (
            "research_workspaces.id",
            "research_workspaces.organization_id",
            "research_workspaces.tenant_id",
            "research_workspaces.market",
        ),
    ) in mandate_constraints

    trial_constraints = _composite_foreign_keys(ResearchStrategyTrial)
    assert (
        ("source_run_id", "organization_id", "tenant_id", "market"),
        (
            "research_runs.id",
            "research_runs.organization_id",
            "research_runs.tenant_id",
            "research_runs.market",
        ),
    ) in trial_constraints

    event_constraints = _composite_foreign_keys(ResearchDecisionEvent)
    assert (
        ("portfolio_id", "organization_id", "tenant_id", "market"),
        (
            "research_shadow_portfolios.id",
            "research_shadow_portfolios.organization_id",
            "research_shadow_portfolios.tenant_id",
            "research_shadow_portfolios.market",
        ),
    ) in event_constraints

    accounting_constraints = _composite_foreign_keys(ResearchAccountingEvent)
    assert (
        ("portfolio_id", "workspace_id", "organization_id", "tenant_id", "market"),
        (
            "research_shadow_portfolios.id",
            "research_shadow_portfolios.workspace_id",
            "research_shadow_portfolios.organization_id",
            "research_shadow_portfolios.tenant_id",
            "research_shadow_portfolios.market",
        ),
    ) in accounting_constraints
    assert (
        ("snapshot_id", "organization_id", "tenant_id", "market"),
        (
            "research_shadow_snapshots.id",
            "research_shadow_snapshots.organization_id",
            "research_shadow_snapshots.tenant_id",
            "research_shadow_snapshots.market",
        ),
    ) in event_constraints


def test_decision_events_have_idempotent_ordered_lineage_contract() -> None:
    constraints = {constraint.name for constraint in ResearchDecisionEvent.__table__.constraints}

    assert "uq_research_decision_events_sequence" in constraints
    assert "uq_research_decision_events_key" in constraints
    assert {
        "correlation_id",
        "sequence",
        "event_key",
        "caused_by_event_key",
        "payload_hash",
        "effective_date",
    } <= set(ResearchDecisionEvent.__table__.c.keys())


def test_accounting_events_have_independent_idempotent_ordered_contract() -> None:
    constraints = {constraint.name for constraint in ResearchAccountingEvent.__table__.constraints}

    assert "uq_research_accounting_events_sequence" in constraints
    assert "uq_research_accounting_events_key" in constraints
    assert {
        "portfolio_id",
        "sequence",
        "session_number",
        "event_key",
        "event_type",
        "engine_version",
        "payload_hash",
        "effective_date",
    } <= set(ResearchAccountingEvent.__table__.c.keys())
    assert "snapshot_id" not in ResearchAccountingEvent.__table__.c
