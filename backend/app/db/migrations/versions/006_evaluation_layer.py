"""Add Evaluation Layer Phase 1 tables: chat_evaluation_logs, retrieval_evaluation_logs,
citation_evaluation_logs, acif_trace_logs, graph_consistency_logs.

Revision ID: 006
Revises: 005
Create Date: 2026-07-07 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create the 5 Evaluation Layer Phase 1 tables."""

    op.create_table(
        "chat_evaluation_logs",
        sa.Column("id", sa.UUID(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("trace_id", sa.String(64), nullable=False),
        sa.Column("session_id", sa.UUID(), nullable=True),
        sa.Column("participant_code", sa.String(100), nullable=True),
        sa.Column("scenario_code", sa.String(100), nullable=True),
        sa.Column("evaluation_mode", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("user_question", sa.Text(), nullable=False),
        sa.Column("normalized_question", sa.Text(), nullable=True),
        sa.Column("final_answer", sa.Text(), nullable=True),
        sa.Column("fallback_triggered", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("fallback_reason", sa.Text(), nullable=True),
        sa.Column("answer_status", sa.String(50), nullable=False),
        sa.Column("total_latency_ms", sa.Integer(), nullable=True),
        sa.Column("retrieval_latency_ms", sa.Integer(), nullable=True),
        sa.Column("graph_latency_ms", sa.Integer(), nullable=True),
        sa.Column("acif_latency_ms", sa.Integer(), nullable=True),
        sa.Column("llm_latency_ms", sa.Integer(), nullable=True),
        sa.Column("output_verification_latency_ms", sa.Integer(), nullable=True),
        sa.Column("model_used", sa.String(255), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("estimated_cost", sa.Float(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_chat_evaluation_logs_trace_id"), "chat_evaluation_logs", ["trace_id"], unique=True)
    op.create_index(op.f("ix_chat_evaluation_logs_session_id"), "chat_evaluation_logs", ["session_id"])
    op.create_index(op.f("ix_chat_evaluation_logs_participant_code"), "chat_evaluation_logs", ["participant_code"])
    op.create_index(op.f("ix_chat_evaluation_logs_scenario_code"), "chat_evaluation_logs", ["scenario_code"])
    op.create_index(op.f("ix_chat_evaluation_logs_created_at"), "chat_evaluation_logs", ["created_at"])

    op.create_table(
        "retrieval_evaluation_logs",
        sa.Column("id", sa.UUID(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("trace_id", sa.String(64), nullable=False),
        sa.Column("chunk_id", sa.String(255), nullable=True),
        sa.Column("document_id", sa.String(255), nullable=True),
        sa.Column("document_version_id", sa.String(255), nullable=True),
        sa.Column("document_title", sa.Text(), nullable=True),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("chunk_type", sa.String(50), nullable=True),
        sa.Column("retrieval_source", sa.String(20), nullable=False, server_default="vector"),
        sa.Column("retrieval_rank", sa.Integer(), nullable=False),
        sa.Column("retrieval_score", sa.Float(), nullable=True),
        sa.Column("selected_for_context", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("rejected_reason", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_retrieval_evaluation_logs_trace_id"), "retrieval_evaluation_logs", ["trace_id"])
    op.create_index(op.f("ix_retrieval_evaluation_logs_chunk_id"), "retrieval_evaluation_logs", ["chunk_id"])
    op.create_index(op.f("ix_retrieval_evaluation_logs_document_id"), "retrieval_evaluation_logs", ["document_id"])
    op.create_index(op.f("ix_retrieval_evaluation_logs_created_at"), "retrieval_evaluation_logs", ["created_at"])

    op.create_table(
        "citation_evaluation_logs",
        sa.Column("id", sa.UUID(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("trace_id", sa.String(64), nullable=False),
        sa.Column("document_id", sa.String(255), nullable=True),
        sa.Column("chunk_id", sa.String(255), nullable=True),
        sa.Column("document_title", sa.Text(), nullable=True),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("citation_type", sa.String(20), nullable=False, server_default="text"),
        sa.Column("is_visual_source", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_valid", sa.Boolean(), nullable=True),
        sa.Column("validation_notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_citation_evaluation_logs_trace_id"), "citation_evaluation_logs", ["trace_id"])
    op.create_index(op.f("ix_citation_evaluation_logs_document_id"), "citation_evaluation_logs", ["document_id"])
    op.create_index(op.f("ix_citation_evaluation_logs_created_at"), "citation_evaluation_logs", ["created_at"])

    op.create_table(
        "acif_trace_logs",
        sa.Column("id", sa.UUID(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("trace_id", sa.String(64), nullable=False),
        sa.Column("gate_number", sa.Integer(), nullable=False),
        sa.Column("gate_name", sa.String(100), nullable=False),
        sa.Column("gate_status", sa.String(20), nullable=False),
        sa.Column("risk_score", sa.Float(), nullable=True),
        sa.Column("risk_level", sa.String(20), nullable=True),
        sa.Column("action_taken", sa.String(255), nullable=True),
        sa.Column("risk_flags", sa.JSON(), nullable=True),
        sa.Column("public_summary", sa.Text(), nullable=True),
        sa.Column("admin_summary", sa.Text(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_acif_trace_logs_trace_id"), "acif_trace_logs", ["trace_id"])
    op.create_index(op.f("ix_acif_trace_logs_gate_name"), "acif_trace_logs", ["gate_name"])
    op.create_index(op.f("ix_acif_trace_logs_gate_status"), "acif_trace_logs", ["gate_status"])
    op.create_index(op.f("ix_acif_trace_logs_created_at"), "acif_trace_logs", ["created_at"])

    op.create_table(
        "graph_consistency_logs",
        sa.Column("id", sa.UUID(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("trace_id", sa.String(64), nullable=False),
        sa.Column("graph_entity", sa.Text(), nullable=True),
        sa.Column("graph_relation", sa.Text(), nullable=True),
        sa.Column("supporting_document_id", sa.String(255), nullable=True),
        sa.Column("supporting_chunk_id", sa.String(255), nullable=True),
        sa.Column("consistency_status", sa.String(30), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_graph_consistency_logs_trace_id"), "graph_consistency_logs", ["trace_id"])
    op.create_index(op.f("ix_graph_consistency_logs_created_at"), "graph_consistency_logs", ["created_at"])


def downgrade() -> None:
    """Drop the 5 Evaluation Layer Phase 1 tables."""
    op.drop_index(op.f("ix_graph_consistency_logs_created_at"), table_name="graph_consistency_logs")
    op.drop_index(op.f("ix_graph_consistency_logs_trace_id"), table_name="graph_consistency_logs")
    op.drop_table("graph_consistency_logs")

    op.drop_index(op.f("ix_acif_trace_logs_created_at"), table_name="acif_trace_logs")
    op.drop_index(op.f("ix_acif_trace_logs_gate_status"), table_name="acif_trace_logs")
    op.drop_index(op.f("ix_acif_trace_logs_gate_name"), table_name="acif_trace_logs")
    op.drop_index(op.f("ix_acif_trace_logs_trace_id"), table_name="acif_trace_logs")
    op.drop_table("acif_trace_logs")

    op.drop_index(op.f("ix_citation_evaluation_logs_created_at"), table_name="citation_evaluation_logs")
    op.drop_index(op.f("ix_citation_evaluation_logs_document_id"), table_name="citation_evaluation_logs")
    op.drop_index(op.f("ix_citation_evaluation_logs_trace_id"), table_name="citation_evaluation_logs")
    op.drop_table("citation_evaluation_logs")

    op.drop_index(op.f("ix_retrieval_evaluation_logs_created_at"), table_name="retrieval_evaluation_logs")
    op.drop_index(op.f("ix_retrieval_evaluation_logs_document_id"), table_name="retrieval_evaluation_logs")
    op.drop_index(op.f("ix_retrieval_evaluation_logs_chunk_id"), table_name="retrieval_evaluation_logs")
    op.drop_index(op.f("ix_retrieval_evaluation_logs_trace_id"), table_name="retrieval_evaluation_logs")
    op.drop_table("retrieval_evaluation_logs")

    op.drop_index(op.f("ix_chat_evaluation_logs_created_at"), table_name="chat_evaluation_logs")
    op.drop_index(op.f("ix_chat_evaluation_logs_scenario_code"), table_name="chat_evaluation_logs")
    op.drop_index(op.f("ix_chat_evaluation_logs_participant_code"), table_name="chat_evaluation_logs")
    op.drop_index(op.f("ix_chat_evaluation_logs_session_id"), table_name="chat_evaluation_logs")
    op.drop_index(op.f("ix_chat_evaluation_logs_trace_id"), table_name="chat_evaluation_logs")
    op.drop_table("chat_evaluation_logs")
