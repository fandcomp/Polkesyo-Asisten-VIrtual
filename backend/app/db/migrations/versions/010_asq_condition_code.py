"""Add condition_code to asq_responses (Evaluation Layer Phase 5 with/without-ACIF hook).

Canonical record of the schema change. Note: deployed databases (dev and prod) are
initialized by init_db()'s create_all + the idempotent _ADDITIVE_COLUMNS ALTERs in
app/db/session.py — this migration exists for future alembic adoption, it is not
auto-run today.

Revision ID: 010
Revises: 009
Create Date: 2026-07-14 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add nullable condition_code to asq_responses."""
    op.add_column("asq_responses", sa.Column("condition_code", sa.String(50), nullable=True))


def downgrade() -> None:
    op.drop_column("asq_responses", "condition_code")
