"""Add hit_rate_at_3 to evaluation_results (Bab 4.4 evaluation-strengthening pass).

Canonical record of the schema change. Note: deployed databases (dev and prod) are
initialized by init_db()'s create_all + the idempotent _ADDITIVE_COLUMNS ALTERs in
app/db/session.py — this migration exists for future alembic adoption, it is not
auto-run today.

Complements precision_at_3/recall_at_3: with a single pinned expected_chunk_id per gold
question, precision_at_3 is structurally capped at 1/3 even for a perfect retrieval.
hit_rate_at_3 (1.0/0.0, no ceiling) is the more representative headline retrieval metric
for that singleton ground-truth shape — see app/evaluation/metrics.py::hit_rate_at_k.

Revision ID: 011
Revises: 010
Create Date: 2026-07-16 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "011"
down_revision = "010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add nullable hit_rate_at_3 to evaluation_results."""
    op.add_column("evaluation_results", sa.Column("hit_rate_at_3", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("evaluation_results", "hit_rate_at_3")
