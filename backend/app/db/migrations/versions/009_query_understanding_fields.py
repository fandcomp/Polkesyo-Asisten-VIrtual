"""Add Query Understanding Layer fields to chat_evaluation_logs.

Canonical record of the schema change. Note: deployed databases (dev and prod) are
initialized by init_db()'s create_all + the idempotent _ADDITIVE_COLUMNS ALTERs in
app/db/session.py — this migration exists for future alembic adoption, it is not
auto-run today.

Revision ID: 009
Revises: 008
Create Date: 2026-07-09 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "009"
down_revision = "008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add query-understanding columns to chat_evaluation_logs."""
    op.add_column("chat_evaluation_logs", sa.Column("rewritten_queries", sa.JSON(), nullable=True))
    op.add_column("chat_evaluation_logs", sa.Column("detected_terms", sa.JSON(), nullable=True))
    op.add_column("chat_evaluation_logs", sa.Column("expanded_terms", sa.JSON(), nullable=True))
    op.add_column("chat_evaluation_logs", sa.Column("intent", sa.String(50), nullable=True))
    op.add_column("chat_evaluation_logs", sa.Column("intent_confidence", sa.Float(), nullable=True))
    op.add_column(
        "chat_evaluation_logs",
        sa.Column(
            "clarification_used",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("chat_evaluation_logs", "clarification_used")
    op.drop_column("chat_evaluation_logs", "intent_confidence")
    op.drop_column("chat_evaluation_logs", "intent")
    op.drop_column("chat_evaluation_logs", "expanded_terms")
    op.drop_column("chat_evaluation_logs", "detected_terms")
    op.drop_column("chat_evaluation_logs", "rewritten_queries")
