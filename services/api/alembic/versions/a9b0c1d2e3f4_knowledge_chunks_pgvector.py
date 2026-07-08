"""knowledge_chunks_pgvector

Revision ID: a9b0c1d2e3f4
Revises: c6d7e8f9a0b1
"""

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision = "a9b0c1d2e3f4"
down_revision = "c6d7e8f9a0b1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "knowledge_chunks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=True),
        sa.Column("market", sa.String(length=8), nullable=False),
        sa.Column("code", sa.String(length=16), nullable=True),
        sa.Column("source_type", sa.String(length=24), nullable=False),
        sa.Column("source_id", sa.String(length=64), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("source_date", sa.Date(), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("reliability", sa.String(length=16), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("embedding_model", sa.String(length=80), nullable=False),
        sa.Column("embedding", Vector(768), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source_type",
            "source_id",
            "code",
            "chunk_index",
            name="uq_knowledge_chunk_source",
        ),
    )
    op.create_index(op.f("ix_knowledge_chunks_code"), "knowledge_chunks", ["code"], unique=False)
    op.create_index(
        op.f("ix_knowledge_chunks_content_hash"),
        "knowledge_chunks",
        ["content_hash"],
        unique=False,
    )
    op.create_index(
        "ix_knowledge_chunks_embedding_hnsw",
        "knowledge_chunks",
        ["embedding"],
        unique=False,
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )
    op.create_index(
        op.f("ix_knowledge_chunks_market"), "knowledge_chunks", ["market"], unique=False
    )
    op.create_index(
        op.f("ix_knowledge_chunks_source_date"),
        "knowledge_chunks",
        ["source_date"],
        unique=False,
    )
    op.create_index(
        op.f("ix_knowledge_chunks_source_type"),
        "knowledge_chunks",
        ["source_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_knowledge_chunks_tenant_id"),
        "knowledge_chunks",
        ["tenant_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_knowledge_chunks_tenant_id"), table_name="knowledge_chunks")
    op.drop_index(op.f("ix_knowledge_chunks_source_type"), table_name="knowledge_chunks")
    op.drop_index(op.f("ix_knowledge_chunks_source_date"), table_name="knowledge_chunks")
    op.drop_index(op.f("ix_knowledge_chunks_market"), table_name="knowledge_chunks")
    op.drop_index("ix_knowledge_chunks_embedding_hnsw", table_name="knowledge_chunks")
    op.drop_index(op.f("ix_knowledge_chunks_content_hash"), table_name="knowledge_chunks")
    op.drop_index(op.f("ix_knowledge_chunks_code"), table_name="knowledge_chunks")
    op.drop_table("knowledge_chunks")
