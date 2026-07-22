"""Add Evaluation Layer Phase 4 tables: evaluation_scenarios, asq_responses, sus_responses.

Revision ID: 008
Revises: 007
Create Date: 2026-07-07 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create evaluation_scenarios, asq_responses, sus_responses tables."""

    op.create_table(
        "evaluation_scenarios",
        sa.Column("id", sa.UUID(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("code", sa.String(100), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("instruction", sa.Text(), nullable=False),
        sa.Column("expected_task", sa.Text(), nullable=True),
        sa.Column("order_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_evaluation_scenarios_code"),
    )

    op.create_table(
        "asq_responses",
        sa.Column("id", sa.UUID(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("participant_code", sa.String(100), nullable=False),
        sa.Column("scenario_id", sa.UUID(), nullable=False),
        sa.Column("scenario_code", sa.String(100), nullable=False),
        sa.Column("session_id", sa.String(64), nullable=True),
        sa.Column("trace_id", sa.String(64), nullable=True),
        sa.Column("asq_1", sa.Integer(), nullable=False),
        sa.Column("asq_2", sa.Integer(), nullable=False),
        sa.Column("asq_3", sa.Integer(), nullable=False),
        sa.Column("average_score", sa.Float(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.CheckConstraint("asq_1 BETWEEN 1 AND 7", name="ck_asq_responses_asq_1_range"),
        sa.CheckConstraint("asq_2 BETWEEN 1 AND 7", name="ck_asq_responses_asq_2_range"),
        sa.CheckConstraint("asq_3 BETWEEN 1 AND 7", name="ck_asq_responses_asq_3_range"),
        sa.ForeignKeyConstraint(["scenario_id"], ["evaluation_scenarios.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_asq_responses_participant_code"), "asq_responses", ["participant_code"])
    op.create_index(op.f("ix_asq_responses_scenario_id"), "asq_responses", ["scenario_id"])
    op.create_index(op.f("ix_asq_responses_scenario_code"), "asq_responses", ["scenario_code"])
    op.create_index(op.f("ix_asq_responses_session_id"), "asq_responses", ["session_id"])
    op.create_index(op.f("ix_asq_responses_trace_id"), "asq_responses", ["trace_id"])
    op.create_index(op.f("ix_asq_responses_created_at"), "asq_responses", ["created_at"])

    sus_columns = [sa.Column(f"sus_{i}", sa.Integer(), nullable=False) for i in range(1, 11)]
    sus_checks = [
        sa.CheckConstraint(f"sus_{i} BETWEEN 1 AND 5", name=f"ck_sus_responses_sus_{i}_range")
        for i in range(1, 11)
    ]
    op.create_table(
        "sus_responses",
        sa.Column("id", sa.UUID(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("participant_code", sa.String(100), nullable=False),
        sa.Column("session_id", sa.String(64), nullable=True),
        *sus_columns,
        sa.Column("sus_score", sa.Float(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        *sus_checks,
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_sus_responses_participant_code"), "sus_responses", ["participant_code"])
    op.create_index(op.f("ix_sus_responses_session_id"), "sus_responses", ["session_id"])
    op.create_index(op.f("ix_sus_responses_created_at"), "sus_responses", ["created_at"])


def downgrade() -> None:
    """Drop sus_responses, asq_responses, evaluation_scenarios tables."""
    op.drop_index(op.f("ix_sus_responses_created_at"), table_name="sus_responses")
    op.drop_index(op.f("ix_sus_responses_session_id"), table_name="sus_responses")
    op.drop_index(op.f("ix_sus_responses_participant_code"), table_name="sus_responses")
    op.drop_table("sus_responses")

    op.drop_index(op.f("ix_asq_responses_created_at"), table_name="asq_responses")
    op.drop_index(op.f("ix_asq_responses_trace_id"), table_name="asq_responses")
    op.drop_index(op.f("ix_asq_responses_session_id"), table_name="asq_responses")
    op.drop_index(op.f("ix_asq_responses_scenario_code"), table_name="asq_responses")
    op.drop_index(op.f("ix_asq_responses_scenario_id"), table_name="asq_responses")
    op.drop_index(op.f("ix_asq_responses_participant_code"), table_name="asq_responses")
    op.drop_table("asq_responses")

    op.drop_table("evaluation_scenarios")
