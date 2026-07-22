"""Add document workflow and operational tables.

Revision ID: 002_document_workflow
Revises: 001_sessions_consent
Create Date: 2026-06-30 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "002_document_workflow"
down_revision = "001_sessions_consent"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create chat_history table
    op.create_table(
        "chat_history",
        sa.Column("id", sa.UUID(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("session_id", sa.UUID(), nullable=False),
        sa.Column("turn_index", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(10), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_chat_history_session_id"), "chat_history", ["session_id"])
    op.create_index(op.f("ix_chat_history_created_at"), "chat_history", ["created_at"])

    # Create documents table (official source documents)
    op.create_table(
        "documents",
        sa.Column("id", sa.UUID(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("document_type", sa.String(50), nullable=False),
        sa.Column("source_url", sa.String(1024), nullable=True),
        sa.Column("source_type", sa.String(50), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="discovered"),
        sa.Column("year", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_documents_status"), "documents", ["status"])
    op.create_index(op.f("ix_documents_created_at"), "documents", ["created_at"])
    op.create_index(op.f("ix_documents_document_type"), "documents", ["document_type"])

    # Create document_versions table
    op.create_table(
        "document_versions",
        sa.Column("id", sa.UUID(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("document_id", sa.UUID(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("checksum", sa.String(64), nullable=False),
        sa.Column("file_path", sa.String(512), nullable=True),
        sa.Column("file_size", sa.Integer(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("document_id", "checksum"),
    )
    op.create_index(op.f("ix_document_versions_document_id"), "document_versions", ["document_id"])
    op.create_index(op.f("ix_document_versions_checksum"), "document_versions", ["checksum"])

    # Create document_chunks table (original, immutable text)
    op.create_table(
        "document_chunks",
        sa.Column("id", sa.UUID(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("document_id", sa.UUID(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("page", sa.Integer(), nullable=True),
        sa.Column("section", sa.String(255), nullable=True),
        sa.Column("token_count", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(50), nullable=False, server_default="pending_review"),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_document_chunks_document_id"), "document_chunks", ["document_id"])
    op.create_index(op.f("ix_document_chunks_status"), "document_chunks", ["status"])
    op.create_index(op.f("ix_document_chunks_active"), "document_chunks", ["active"])
    op.create_index(op.f("ix_document_chunks_approved_at"), "document_chunks", ["approved_at"])

    # Create chunk_summaries table (LLM draft + admin approved separately)
    op.create_table(
        "chunk_summaries",
        sa.Column("id", sa.UUID(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("chunk_id", sa.UUID(), nullable=False),
        sa.Column("llm_draft_summary", sa.Text(), nullable=True),
        sa.Column("admin_summary", sa.Text(), nullable=True),
        sa.Column("admin_notes", sa.Text(), nullable=True),
        sa.Column("status", sa.String(50), nullable=False, server_default="summary_drafted"),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_by_admin", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["chunk_id"], ["document_chunks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_chunk_summaries_chunk_id"), "chunk_summaries", ["chunk_id"])
    op.create_index(op.f("ix_chunk_summaries_status"), "chunk_summaries", ["status"])

    # Create chunk_reviews table (audit trail)
    op.create_table(
        "chunk_reviews",
        sa.Column("id", sa.UUID(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("chunk_id", sa.UUID(), nullable=False),
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column("review_notes", sa.Text(), nullable=True),
        sa.Column("reviewed_by_admin", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["chunk_id"], ["document_chunks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_chunk_reviews_chunk_id"), "chunk_reviews", ["chunk_id"])
    op.create_index(op.f("ix_chunk_reviews_action"), "chunk_reviews", ["action"])

    # Create document_approval_events table (audit trail)
    op.create_table(
        "document_approval_events",
        sa.Column("id", sa.UUID(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("document_id", sa.UUID(), nullable=False),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("previous_status", sa.String(50), nullable=True),
        sa.Column("new_status", sa.String(50), nullable=True),
        sa.Column("details_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_document_approval_events_document_id"), "document_approval_events", ["document_id"])
    op.create_index(op.f("ix_document_approval_events_event_type"), "document_approval_events", ["event_type"])

    # Create ingestion_jobs table (tracking document processing)
    op.create_table(
        "ingestion_jobs",
        sa.Column("id", sa.UUID(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("document_id", sa.UUID(), nullable=False),
        sa.Column("job_type", sa.String(50), nullable=False),
        sa.Column("status", sa.String(50), nullable=False),
        sa.Column("progress", sa.Integer(), nullable=False, server_default=0),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_ingestion_jobs_document_id"), "ingestion_jobs", ["document_id"])
    op.create_index(op.f("ix_ingestion_jobs_status"), "ingestion_jobs", ["status"])

    # Create retrieval_logs table
    op.create_table(
        "retrieval_logs",
        sa.Column("id", sa.UUID(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("session_id", sa.UUID(), nullable=False),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("retrieved_chunk_ids", sa.JSON(), nullable=True),
        sa.Column("retrieval_method", sa.String(50), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_retrieval_logs_session_id"), "retrieval_logs", ["session_id"])
    op.create_index(op.f("ix_retrieval_logs_created_at"), "retrieval_logs", ["created_at"])

    # Create security_events table
    op.create_table(
        "security_events",
        sa.Column("id", sa.UUID(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("session_id", sa.UUID(), nullable=True),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("risk_level", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_security_events_session_id"), "security_events", ["session_id"])
    op.create_index(op.f("ix_security_events_event_type"), "security_events", ["event_type"])
    op.create_index(op.f("ix_security_events_created_at"), "security_events", ["created_at"])

    # Create acif_context_score_logs table
    op.create_table(
        "acif_context_score_logs",
        sa.Column("id", sa.UUID(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("chunk_id", sa.UUID(), nullable=False),
        sa.Column("session_id", sa.UUID(), nullable=True),
        sa.Column("gate_number", sa.Integer(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("decision", sa.String(50), nullable=False),
        sa.Column("details_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["chunk_id"], ["document_chunks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_acif_context_score_logs_chunk_id"), "acif_context_score_logs", ["chunk_id"])
    op.create_index(op.f("ix_acif_context_score_logs_gate_number"), "acif_context_score_logs", ["gate_number"])

    # Create acif_output_verification_logs table
    op.create_table(
        "acif_output_verification_logs",
        sa.Column("id", sa.UUID(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("session_id", sa.UUID(), nullable=False),
        sa.Column("claim_type", sa.String(50), nullable=False),
        sa.Column("claim_text", sa.Text(), nullable=False),
        sa.Column("verified", sa.Boolean(), nullable=False),
        sa.Column("supporting_chunk_id", sa.UUID(), nullable=True),
        sa.Column("details_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["supporting_chunk_id"], ["document_chunks.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_acif_output_verification_logs_session_id"), "acif_output_verification_logs", ["session_id"])
    op.create_index(op.f("ix_acif_output_verification_logs_claim_type"), "acif_output_verification_logs", ["claim_type"])

    # Create openrouter_usage_logs table
    op.create_table(
        "openrouter_usage_logs",
        sa.Column("id", sa.UUID(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("session_id", sa.UUID(), nullable=True),
        sa.Column("model", sa.String(100), nullable=False),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False),
        sa.Column("completion_tokens", sa.Integer(), nullable=False),
        sa.Column("total_tokens", sa.Integer(), nullable=False),
        sa.Column("cost_usd", sa.Numeric(precision=10, scale=6), nullable=True),
        sa.Column("request_type", sa.String(50), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_openrouter_usage_logs_session_id"), "openrouter_usage_logs", ["session_id"])
    op.create_index(op.f("ix_openrouter_usage_logs_created_at"), "openrouter_usage_logs", ["created_at"])
    op.create_index(op.f("ix_openrouter_usage_logs_model"), "openrouter_usage_logs", ["model"])

    # Create evaluation_logs table
    op.create_table(
        "evaluation_logs",
        sa.Column("id", sa.UUID(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("session_id", sa.UUID(), nullable=False),
        sa.Column("test_case_id", sa.String(100), nullable=False),
        sa.Column("metric_name", sa.String(100), nullable=False),
        sa.Column("metric_value", sa.Float(), nullable=False),
        sa.Column("details_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_evaluation_logs_session_id"), "evaluation_logs", ["session_id"])
    op.create_index(op.f("ix_evaluation_logs_metric_name"), "evaluation_logs", ["metric_name"])

    # Create rate_limit_logs table
    op.create_table(
        "rate_limit_logs",
        sa.Column("id", sa.UUID(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("session_id", sa.UUID(), nullable=True),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("limit_type", sa.String(50), nullable=False),
        sa.Column("current_count", sa.Integer(), nullable=False),
        sa.Column("limit_threshold", sa.Integer(), nullable=False),
        sa.Column("blocked", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_rate_limit_logs_session_id"), "rate_limit_logs", ["session_id"])
    op.create_index(op.f("ix_rate_limit_logs_created_at"), "rate_limit_logs", ["created_at"])


def downgrade() -> None:
    # Drop tables in reverse order (respect foreign keys)
    op.drop_index(op.f("ix_rate_limit_logs_created_at"), table_name="rate_limit_logs")
    op.drop_index(op.f("ix_rate_limit_logs_session_id"), table_name="rate_limit_logs")
    op.drop_table("rate_limit_logs")
    
    op.drop_index(op.f("ix_evaluation_logs_metric_name"), table_name="evaluation_logs")
    op.drop_index(op.f("ix_evaluation_logs_session_id"), table_name="evaluation_logs")
    op.drop_table("evaluation_logs")
    
    op.drop_index(op.f("ix_openrouter_usage_logs_model"), table_name="openrouter_usage_logs")
    op.drop_index(op.f("ix_openrouter_usage_logs_created_at"), table_name="openrouter_usage_logs")
    op.drop_index(op.f("ix_openrouter_usage_logs_session_id"), table_name="openrouter_usage_logs")
    op.drop_table("openrouter_usage_logs")
    
    op.drop_index(op.f("ix_acif_output_verification_logs_claim_type"), table_name="acif_output_verification_logs")
    op.drop_index(op.f("ix_acif_output_verification_logs_session_id"), table_name="acif_output_verification_logs")
    op.drop_table("acif_output_verification_logs")
    
    op.drop_index(op.f("ix_acif_context_score_logs_gate_number"), table_name="acif_context_score_logs")
    op.drop_index(op.f("ix_acif_context_score_logs_chunk_id"), table_name="acif_context_score_logs")
    op.drop_table("acif_context_score_logs")
    
    op.drop_index(op.f("ix_security_events_created_at"), table_name="security_events")
    op.drop_index(op.f("ix_security_events_event_type"), table_name="security_events")
    op.drop_index(op.f("ix_security_events_session_id"), table_name="security_events")
    op.drop_table("security_events")
    
    op.drop_index(op.f("ix_retrieval_logs_created_at"), table_name="retrieval_logs")
    op.drop_index(op.f("ix_retrieval_logs_session_id"), table_name="retrieval_logs")
    op.drop_table("retrieval_logs")
    
    op.drop_index(op.f("ix_ingestion_jobs_status"), table_name="ingestion_jobs")
    op.drop_index(op.f("ix_ingestion_jobs_document_id"), table_name="ingestion_jobs")
    op.drop_table("ingestion_jobs")
    
    op.drop_index(op.f("ix_document_approval_events_event_type"), table_name="document_approval_events")
    op.drop_index(op.f("ix_document_approval_events_document_id"), table_name="document_approval_events")
    op.drop_table("document_approval_events")
    
    op.drop_index(op.f("ix_chunk_reviews_action"), table_name="chunk_reviews")
    op.drop_index(op.f("ix_chunk_reviews_chunk_id"), table_name="chunk_reviews")
    op.drop_table("chunk_reviews")
    
    op.drop_index(op.f("ix_chunk_summaries_status"), table_name="chunk_summaries")
    op.drop_index(op.f("ix_chunk_summaries_chunk_id"), table_name="chunk_summaries")
    op.drop_table("chunk_summaries")
    
    op.drop_index(op.f("ix_document_chunks_approved_at"), table_name="document_chunks")
    op.drop_index(op.f("ix_document_chunks_active"), table_name="document_chunks")
    op.drop_index(op.f("ix_document_chunks_status"), table_name="document_chunks")
    op.drop_index(op.f("ix_document_chunks_document_id"), table_name="document_chunks")
    op.drop_table("document_chunks")
    
    op.drop_index(op.f("ix_document_versions_checksum"), table_name="document_versions")
    op.drop_index(op.f("ix_document_versions_document_id"), table_name="document_versions")
    op.drop_table("document_versions")
    
    op.drop_index(op.f("ix_documents_document_type"), table_name="documents")
    op.drop_index(op.f("ix_documents_created_at"), table_name="documents")
    op.drop_index(op.f("ix_documents_status"), table_name="documents")
    op.drop_table("documents")
    
    op.drop_index(op.f("ix_chat_history_created_at"), table_name="chat_history")
    op.drop_index(op.f("ix_chat_history_session_id"), table_name="chat_history")
    op.drop_table("chat_history")