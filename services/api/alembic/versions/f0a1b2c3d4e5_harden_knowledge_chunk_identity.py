"""tenant-safe, model-versioned knowledge chunk identity

Revision ID: f0a1b2c3d4e5
Revises: e9f0a1b2c3d4
"""

from alembic import op

revision = "f0a1b2c3d4e5"
down_revision = "e9f0a1b2c3d4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("uq_knowledge_chunk_source", "knowledge_chunks", type_="unique")
    op.create_unique_constraint(
        "uq_knowledge_chunk_source",
        "knowledge_chunks",
        [
            "tenant_id",
            "market",
            "source_type",
            "source_id",
            "code",
            "chunk_index",
            "embedding_model",
        ],
        postgresql_nulls_not_distinct=True,
    )
    op.create_index(
        "ix_knowledge_chunks_retrieval_scope",
        "knowledge_chunks",
        ["market", "code", "embedding_model", "tenant_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_knowledge_chunks_retrieval_scope", table_name="knowledge_chunks")
    op.drop_constraint("uq_knowledge_chunk_source", "knowledge_chunks", type_="unique")
    op.create_unique_constraint(
        "uq_knowledge_chunk_source",
        "knowledge_chunks",
        ["source_type", "source_id", "code", "chunk_index"],
    )
