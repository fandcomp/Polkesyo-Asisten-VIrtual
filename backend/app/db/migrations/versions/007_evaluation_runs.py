"""Add Evaluation Layer Phase 3 tables: evaluation_runs, evaluation_results.

Revision ID: 007
Revises: 006
Create Date: 2026-07-07 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create evaluation_runs and evaluation_results tables."""

    op.create_table(
        "evaluation_runs",
        sa.Column("id", sa.UUID(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("run_name", sa.String(255), nullable=False),
        sa.Column("config_name", sa.String(100), nullable=True),
        sa.Column("run_type", sa.String(20), nullable=False, server_default="full"),
        sa.Column("total_questions", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completed_questions", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.String(100), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_evaluation_runs_created_at"), "evaluation_runs", ["created_at"])
    op.create_index(op.f("ix_evaluation_runs_status"), "evaluation_runs", ["status"])

    op.create_table(
        "evaluation_results",
        sa.Column("id", sa.UUID(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("evaluation_run_id", sa.UUID(), nullable=False),
        sa.Column("question_id", sa.String(64), nullable=False),
        sa.Column("trace_id", sa.String(64), nullable=True),
        sa.Column("category", sa.String(100), nullable=True),
        sa.Column("expected_behavior", sa.String(30), nullable=False),
        sa.Column("precision_at_3", sa.Float(), nullable=True),
        sa.Column("recall_at_3", sa.Float(), nullable=True),
        sa.Column("citation_present", sa.Boolean(), nullable=True),
        sa.Column("citation_correct", sa.Boolean(), nullable=True),
        sa.Column("fallback_correct", sa.Boolean(), nullable=True),
        sa.Column("answer_relevance_score", sa.Float(), nullable=True),
        sa.Column("faithfulness_score", sa.Float(), nullable=True),
        sa.Column("hallucination_detected", sa.Boolean(), nullable=True),
        sa.Column("attack_success", sa.Boolean(), nullable=True),
        sa.Column("total_latency_ms", sa.Integer(), nullable=True),
        sa.Column("retrieval_latency_ms", sa.Integer(), nullable=True),
        sa.Column("llm_latency_ms", sa.Integer(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["evaluation_run_id"], ["evaluation_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_evaluation_results_evaluation_run_id"), "evaluation_results", ["evaluation_run_id"])
    op.create_index(op.f("ix_evaluation_results_question_id"), "evaluation_results", ["question_id"])
    op.create_index(op.f("ix_evaluation_results_trace_id"), "evaluation_results", ["trace_id"])
    op.create_index(op.f("ix_evaluation_results_created_at"), "evaluation_results", ["created_at"])


def downgrade() -> None:
    """Drop evaluation_results and evaluation_runs tables."""
    op.drop_index(op.f("ix_evaluation_results_created_at"), table_name="evaluation_results")
    op.drop_index(op.f("ix_evaluation_results_trace_id"), table_name="evaluation_results")
    op.drop_index(op.f("ix_evaluation_results_question_id"), table_name="evaluation_results")
    op.drop_index(op.f("ix_evaluation_results_evaluation_run_id"), table_name="evaluation_results")
    op.drop_table("evaluation_results")

    op.drop_index(op.f("ix_evaluation_runs_status"), table_name="evaluation_runs")
    op.drop_index(op.f("ix_evaluation_runs_created_at"), table_name="evaluation_runs")
    op.drop_table("evaluation_runs")
