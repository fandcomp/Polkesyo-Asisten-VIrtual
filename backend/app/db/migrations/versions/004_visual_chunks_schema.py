"""Add visual chunk support to document schema."""
from alembic import op
import sqlalchemy as sa


revision = "004"
down_revision = "003_openrouter_logs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add visual chunk fields to document_chunks table."""

    op.add_column(
        "document_chunks",
        sa.Column("chunk_type", sa.String(50), nullable=False, server_default="text"),
    )
    op.add_column(
        "document_chunks",
        sa.Column("image_artifact_path", sa.String(1024), nullable=True),
    )
    op.add_column(
        "document_chunks",
        sa.Column("image_hash", sa.String(64), nullable=True),
    )
    op.add_column(
        "document_chunks",
        sa.Column("bounding_box", sa.JSON(), nullable=True),
    )
    op.add_column(
        "document_chunks",
        sa.Column("extraction_method", sa.String(100), nullable=True),
    )
    op.add_column(
        "document_chunks",
        sa.Column("vision_model", sa.String(255), nullable=True),
    )
    op.add_column(
        "document_chunks",
        sa.Column("vision_prompt_version", sa.Integer(), nullable=True),
    )
    op.add_column(
        "document_chunks",
        sa.Column("raw_visual_description", sa.Text(), nullable=True),
    )
    op.add_column(
        "document_chunks",
        sa.Column("visible_text_draft", sa.Text(), nullable=True),
    )
    op.add_column(
        "document_chunks",
        sa.Column("uncertainty_notes", sa.Text(), nullable=True),
    )
    op.add_column(
        "document_chunks",
        sa.Column("confidence_score", sa.Float(), nullable=True),
    )
    op.add_column(
        "document_chunks",
        sa.Column("risk_flags", sa.JSON(), nullable=True, server_default="[]"),
    )
    op.add_column(
        "document_chunks",
        sa.Column("admin_status", sa.String(50), nullable=False, server_default="pending_review"),
    )
    op.add_column(
        "document_chunks",
        sa.Column("reviewed_by", sa.String(100), nullable=True),
    )
    op.add_column(
        "document_chunks",
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "document_chunks",
        sa.Column("admin_notes", sa.Text(), nullable=True),
    )

    op.create_index(
        "ix_document_chunks_chunk_type",
        "document_chunks",
        ["chunk_type"],
    )
    op.create_index(
        "ix_document_chunks_admin_status",
        "document_chunks",
        ["admin_status"],
    )
    op.create_index(
        "ix_document_chunks_image_hash",
        "document_chunks",
        ["image_hash"],
    )
    op.create_index(
        "ix_document_chunks_reviewed_at",
        "document_chunks",
        ["reviewed_at"],
    )


def downgrade() -> None:
    """Remove visual chunk fields from document_chunks table."""

    op.drop_index("ix_document_chunks_reviewed_at", table_name="document_chunks")
    op.drop_index("ix_document_chunks_image_hash", table_name="document_chunks")
    op.drop_index("ix_document_chunks_admin_status", table_name="document_chunks")
    op.drop_index("ix_document_chunks_chunk_type", table_name="document_chunks")

    op.drop_column("document_chunks", "admin_notes")
    op.drop_column("document_chunks", "reviewed_at")
    op.drop_column("document_chunks", "reviewed_by")
    op.drop_column("document_chunks", "admin_status")
    op.drop_column("document_chunks", "risk_flags")
    op.drop_column("document_chunks", "confidence_score")
    op.drop_column("document_chunks", "uncertainty_notes")
    op.drop_column("document_chunks", "visible_text_draft")
    op.drop_column("document_chunks", "raw_visual_description")
    op.drop_column("document_chunks", "vision_prompt_version")
    op.drop_column("document_chunks", "vision_model")
    op.drop_column("document_chunks", "extraction_method")
    op.drop_column("document_chunks", "bounding_box")
    op.drop_column("document_chunks", "image_hash")
    op.drop_column("document_chunks", "image_artifact_path")
    op.drop_column("document_chunks", "chunk_type")
