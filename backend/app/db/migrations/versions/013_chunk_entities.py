"""Add chunk_entities table (durable, per-chunk, admin-editable entity list).

Turns the previously ephemeral, uneditable "detected entities" list shown in the admin
chunk-review panel (GraphService.extract_entities run live on every GET request, never
persisted, no ID, no way to correct terminology) into a durable per-chunk record admins can
confirm, correct, reject, or supplement. Mirrors the chunk_summaries draft -> edited ->
approved/promoted shape and the chunk_reviews append-only audit-log pattern (see
db/models.py ChunkSummary/ChunkReview) rather than inventing a new review shape.

Safety note (CLAUDE.md graph-safety constraint, see graph_service.py comments): Neo4j entity
nodes are MERGE'd globally by (label, name) and shared across every document that mentions
them. Editing a row in this table never mutates an existing Neo4j node in place — it only
changes which node a document's MENTIONS edge targets on the next reindex (MERGE-or-create).

Revision ID: 013
Revises: 012
Create Date: 2026-07-21 00:00:00.000000

Note (matching this project's existing migration-file convention, see 012's own header
comment and 011_hit_rate_at_3.py before it): deployed databases (dev and prod) are
initialized by init_db()'s create_all in app/db/session.py, which picks up the new
ChunkEntity model automatically — this migration is the canonical schema record for future
alembic adoption, it is not auto-run today.

"""
from alembic import op
import sqlalchemy as sa


revision = "013"
down_revision = "012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "chunk_entities",
        sa.Column("id", sa.UUID(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("chunk_id", sa.UUID(), nullable=False),
        sa.Column("document_id", sa.UUID(), nullable=False),
        sa.Column("entity_type", sa.String(50), nullable=False),
        sa.Column("detected_text", sa.String(500), nullable=False),
        sa.Column("corrected_text", sa.String(500), nullable=True),
        sa.Column("corrected_type", sa.String(50), nullable=True),
        sa.Column("source", sa.String(20), nullable=False, server_default="llm_detected"),
        sa.Column("status", sa.String(20), nullable=False, server_default="detected"),
        sa.Column("reviewed_by", sa.String(100), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["chunk_id"], ["document_chunks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_chunk_entities_chunk_id"), "chunk_entities", ["chunk_id"])
    op.create_index(op.f("ix_chunk_entities_document_id"), "chunk_entities", ["document_id"])
    op.create_index(op.f("ix_chunk_entities_status"), "chunk_entities", ["status"])


def downgrade() -> None:
    op.drop_index(op.f("ix_chunk_entities_status"), table_name="chunk_entities")
    op.drop_index(op.f("ix_chunk_entities_document_id"), table_name="chunk_entities")
    op.drop_index(op.f("ix_chunk_entities_chunk_id"), table_name="chunk_entities")
    op.drop_table("chunk_entities")
