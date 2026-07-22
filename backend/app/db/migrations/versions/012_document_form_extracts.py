"""Add document_form_extracts table (structure-aware document extraction plan).

Standalone table, not a document_chunks row — form/attachment zone pages produced by
DocumentStructureAgent/FormExtractionAgent/VisionFormConversionAgent are explicitly excluded
from chunking/vector retrieval (CLAUDE.md §4.7). Mirrors the document_chunks/visual-chunk
status-lifecycle convention (pending_review -> approved/rejected/needs_revision -> active/
archived) via its own `status` column, kept in a dedicated table since these rows are never
chunked/indexed/embedded.

Note (matching this project's existing migration-file convention, see 011_hit_rate_at_3.py's
own header comment): deployed databases (dev and prod) are initialized by init_db()'s
create_all in app/db/session.py, which picks up the new DocumentFormExtract model
automatically — this migration is the canonical schema record for future alembic adoption,
it is not auto-run today.

Revision ID: 012
Revises: 011
Create Date: 2026-07-21 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "012"
down_revision = "011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "document_form_extracts",
        sa.Column("id", sa.UUID(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("document_id", sa.UUID(), nullable=False),
        sa.Column("document_version_id", sa.UUID(), nullable=False),
        sa.Column("zone_type", sa.String(20), nullable=False),
        sa.Column("form_title", sa.String(255), nullable=False),
        sa.Column("source_page_start", sa.Integer(), nullable=False),
        sa.Column("source_page_end", sa.Integer(), nullable=False),
        sa.Column("extraction_method", sa.String(20), nullable=False),
        sa.Column("docx_artifact_path", sa.String(1024), nullable=True),
        sa.Column("status", sa.String(50), nullable=False, server_default="pending_review"),
        sa.Column("reviewed_by", sa.String(100), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("admin_notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["document_version_id"], ["document_versions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_document_form_extracts_document_id"), "document_form_extracts", ["document_id"])
    op.create_index(op.f("ix_document_form_extracts_status"), "document_form_extracts", ["status"])


def downgrade() -> None:
    op.drop_index(op.f("ix_document_form_extracts_status"), table_name="document_form_extracts")
    op.drop_index(op.f("ix_document_form_extracts_document_id"), table_name="document_form_extracts")
    op.drop_table("document_form_extracts")
