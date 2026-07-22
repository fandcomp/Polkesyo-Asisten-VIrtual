"""Create openrouter_usage_logs table for cost tracking.

Revision ID: 003_openrouter_logs
Revises: 002_document_workflow
Create Date: 2026-07-01 09:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "003_openrouter_logs"
down_revision = "002_document_workflow"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create openrouter_usage_logs table."""
    op.create_table(
        "openrouter_usage_logs",
        sa.Column("id", sa.UUID(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("model", sa.String(255), nullable=False),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completion_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cost_usd", sa.Float(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        op.f("ix_openrouter_usage_logs_created_at"),
        "openrouter_usage_logs",
        ["created_at"],
    )
    op.create_index(
        op.f("ix_openrouter_usage_logs_model"),
        "openrouter_usage_logs",
        ["model"],
    )


def downgrade() -> None:
    """Drop openrouter_usage_logs table."""
    op.drop_index(
        op.f("ix_openrouter_usage_logs_model"),
        table_name="openrouter_usage_logs",
    )
    op.drop_index(
        op.f("ix_openrouter_usage_logs_created_at"),
        table_name="openrouter_usage_logs",
    )
    op.drop_table("openrouter_usage_logs")
