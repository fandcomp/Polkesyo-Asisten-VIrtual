"""Add agentic architecture tables: document_sources, agent_run_logs, acif_decision_logs.

Revision ID: 005
Revises: 004
Create Date: 2026-07-02 16:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create document_sources, agent_run_logs, acif_decision_logs tables."""

    op.create_table(
        "document_sources",
        sa.Column("id", sa.UUID(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("source_name", sa.String(255), nullable=False),
        sa.Column("source_url", sa.String(1024), nullable=False),
        sa.Column("source_type", sa.String(50), nullable=False, server_default="official_sync"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "agent_run_logs",
        sa.Column("id", sa.UUID(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("agent_name", sa.String(100), nullable=False),
        sa.Column("task_type", sa.String(100), nullable=True),
        sa.Column("input_summary", sa.Text(), nullable=True),
        sa.Column("output_summary", sa.Text(), nullable=True),
        sa.Column("status", sa.String(50), nullable=False),
        sa.Column("latency_ms", sa.Float(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_agent_run_logs_agent_name"), "agent_run_logs", ["agent_name"])
    op.create_index(op.f("ix_agent_run_logs_created_at"), "agent_run_logs", ["created_at"])

    op.create_table(
        "acif_decision_logs",
        sa.Column("id", sa.UUID(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("query_id", sa.UUID(), nullable=True),
        sa.Column("document_id", sa.UUID(), nullable=True),
        sa.Column("chunk_id", sa.UUID(), nullable=True),
        sa.Column("agent_run_id", sa.UUID(), nullable=True),
        sa.Column("risk_level", sa.String(20), nullable=False),
        sa.Column("filtering_mode", sa.String(20), nullable=False),
        sa.Column("context_integrity_score", sa.Float(), nullable=True),
        sa.Column("source_integrity_score", sa.Float(), nullable=True),
        sa.Column("graph_integrity_score", sa.Float(), nullable=True),
        sa.Column("decision", sa.String(50), nullable=False),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("fallback_required", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["agent_run_id"], ["agent_run_logs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_acif_decision_logs_created_at"), "acif_decision_logs", ["created_at"])


def downgrade() -> None:
    """Drop acif_decision_logs, agent_run_logs, document_sources tables."""
    op.drop_index(op.f("ix_acif_decision_logs_created_at"), table_name="acif_decision_logs")
    op.drop_table("acif_decision_logs")

    op.drop_index(op.f("ix_agent_run_logs_created_at"), table_name="agent_run_logs")
    op.drop_index(op.f("ix_agent_run_logs_agent_name"), table_name="agent_run_logs")
    op.drop_table("agent_run_logs")

    op.drop_table("document_sources")
