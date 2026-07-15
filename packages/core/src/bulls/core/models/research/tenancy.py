"""Tenant-bound institutional organizations, workspaces, and memberships."""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from bulls.core.db import Base


class ResearchOrganization(Base):
    """A customer organization belonging to exactly one branded market tenant."""

    __tablename__ = "research_organizations"
    __table_args__ = (
        UniqueConstraint(
            "id",
            "tenant_id",
            "market",
            name="uq_research_organizations_security_scope",
        ),
        UniqueConstraint(
            "tenant_id",
            "slug",
            name="uq_research_organizations_tenant_slug",
        ),
        CheckConstraint(
            "status IN ('active', 'suspended', 'closed')",
            name="ck_research_organizations_status",
        ),
        CheckConstraint(
            "slug ~ '^[a-z0-9]+(?:-[a-z0-9]+)*$'",
            name="ck_research_organizations_slug",
        ),
        ForeignKeyConstraint(
            ["created_by_user_id", "tenant_id"],
            ["users.id", "users.tenant_id"],
            name="fk_research_organizations_creator_tenant",
            ondelete="RESTRICT",
        ),
        Index("ix_research_organizations_tenant_status", "tenant_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    tenant_id: Mapped[str] = mapped_column(String(64))
    market: Mapped[str] = mapped_column(String(8))
    slug: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(160))
    status: Mapped[str] = mapped_column(String(16), default="active", server_default="active")
    created_by_user_id: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ResearchOrganizationMembership(Base):
    __tablename__ = "research_organization_memberships"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "user_id",
            "tenant_id",
            "market",
            name="uq_research_org_memberships_security_scope",
        ),
        CheckConstraint(
            "role IN ('owner', 'admin', 'member')",
            name="ck_research_organization_memberships_role",
        ),
        CheckConstraint(
            "status IN ('invited', 'active', 'disabled')",
            name="ck_research_organization_memberships_status",
        ),
        ForeignKeyConstraint(
            ["organization_id", "tenant_id", "market"],
            [
                "research_organizations.id",
                "research_organizations.tenant_id",
                "research_organizations.market",
            ],
            name="fk_research_org_memberships_organization_scope",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["user_id", "tenant_id"],
            ["users.id", "users.tenant_id"],
            name="fk_research_org_memberships_user_tenant",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["invited_by_user_id", "tenant_id"],
            ["users.id", "users.tenant_id"],
            name="fk_research_org_memberships_inviter_tenant",
            ondelete="RESTRICT",
        ),
        Index(
            "ix_research_org_memberships_tenant_user_status",
            "tenant_id",
            "user_id",
            "status",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64))
    market: Mapped[str] = mapped_column(String(8))
    role: Mapped[str] = mapped_column(String(16), default="member", server_default="member")
    status: Mapped[str] = mapped_column(String(16), default="invited", server_default="invited")
    invited_by_user_id: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    activated_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))


class ResearchWorkspace(Base):
    """A private workspace fixed to its organization's single market."""

    __tablename__ = "research_workspaces"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "slug",
            name="uq_research_workspaces_organization_slug",
        ),
        UniqueConstraint(
            "id",
            "organization_id",
            "tenant_id",
            "market",
            name="uq_research_workspaces_security_scope",
        ),
        CheckConstraint(
            "status IN ('active', 'archived')",
            name="ck_research_workspaces_status",
        ),
        CheckConstraint(
            "slug ~ '^[a-z0-9]+(?:-[a-z0-9]+)*$'",
            name="ck_research_workspaces_slug",
        ),
        CheckConstraint(
            "base_currency ~ '^[A-Z]{3}$'",
            name="ck_research_workspaces_base_currency",
        ),
        ForeignKeyConstraint(
            ["organization_id", "tenant_id", "market"],
            [
                "research_organizations.id",
                "research_organizations.tenant_id",
                "research_organizations.market",
            ],
            name="fk_research_workspaces_organization_scope",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["organization_id", "created_by_user_id", "tenant_id", "market"],
            [
                "research_organization_memberships.organization_id",
                "research_organization_memberships.user_id",
                "research_organization_memberships.tenant_id",
                "research_organization_memberships.market",
            ],
            name="fk_research_workspaces_creator_membership",
            ondelete="RESTRICT",
        ),
        Index(
            "ix_research_workspaces_tenant_organization_status",
            "tenant_id",
            "organization_id",
            "status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    tenant_id: Mapped[str] = mapped_column(String(64))
    market: Mapped[str] = mapped_column(String(8))
    slug: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(160))
    status: Mapped[str] = mapped_column(String(16), default="active", server_default="active")
    base_currency: Mapped[str] = mapped_column(String(3))
    created_by_user_id: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ResearchWorkspaceMembership(Base):
    __tablename__ = "research_workspace_memberships"
    __table_args__ = (
        CheckConstraint(
            "role IN ('portfolio_manager', 'analyst', 'risk', 'viewer')",
            name="ck_research_workspace_memberships_role",
        ),
        CheckConstraint(
            "status IN ('active', 'disabled')",
            name="ck_research_workspace_memberships_status",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "organization_id", "tenant_id", "market"],
            [
                "research_workspaces.id",
                "research_workspaces.organization_id",
                "research_workspaces.tenant_id",
                "research_workspaces.market",
            ],
            name="fk_research_workspace_memberships_workspace_scope",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["organization_id", "user_id", "tenant_id", "market"],
            [
                "research_organization_memberships.organization_id",
                "research_organization_memberships.user_id",
                "research_organization_memberships.tenant_id",
                "research_organization_memberships.market",
            ],
            name="fk_research_workspace_memberships_organization_member",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["granted_by_user_id", "tenant_id"],
            ["users.id", "users.tenant_id"],
            name="fk_research_workspace_memberships_granter_tenant",
            ondelete="RESTRICT",
        ),
        Index(
            "ix_research_workspace_memberships_tenant_user_status",
            "tenant_id",
            "user_id",
            "status",
        ),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    tenant_id: Mapped[str] = mapped_column(String(64))
    market: Mapped[str] = mapped_column(String(8))
    role: Mapped[str] = mapped_column(String(24))
    status: Mapped[str] = mapped_column(String(16), default="active", server_default="active")
    granted_by_user_id: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
