"""Create sessions and consent_log tables.

Revision ID: 001_sessions_consent
Revises:
Create Date: 2026-06-30 11:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "001_sessions_consent"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create sessions table
    op.create_table(
        "sessions",
        sa.Column("id", sa.UUID(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("last_active_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("status", sa.String(50), nullable=False, server_default="active"),
        sa.Column("user_agent_hash", sa.String(64), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_sessions_created_at"), "sessions", ["created_at"])
    op.create_index(op.f("ix_sessions_last_active_at"), "sessions", ["last_active_at"])

    # Create consent_log table
    op.create_table(
        "consent_log",
        sa.Column("id", sa.UUID(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("session_id", sa.UUID(), nullable=False),
        sa.Column("consent_value", sa.String(50), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("source", sa.String(100), nullable=True),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_consent_log_session_id"), "consent_log", ["session_id"])
    op.create_index(op.f("ix_consent_log_created_at"), "consent_log", ["created_at"])


def downgrade() -> None:
    op.drop_index(op.f("ix_consent_log_created_at"), table_name="consent_log")
    op.drop_index(op.f("ix_consent_log_session_id"), table_name="consent_log")
    op.drop_table("consent_log")
    op.drop_index(op.f("ix_sessions_last_active_at"), table_name="sessions")
    op.drop_index(op.f("ix_sessions_created_at"), table_name="sessions")
    op.drop_table("sessions")