"""Add precision_at_5/recall_at_5/hit_rate_at_5/retrieval_relevance_score to evaluation_results.

Canonical record of the schema change. Note: deployed databases (dev and prod) are
initialized by init_db()'s create_all + the idempotent _ADDITIVE_COLUMNS ALTERs in
app/db/session.py -- this migration exists for future alembic adoption, it is not
auto-run today.

Root cause this addresses (2026-07-25): precision_at_3/recall_at_3/hit_rate_at_3 all check
only the top-3 retrieved chunks, but the system's real answer-generation context width is
max_context_chunks=5 -- so a correctly-retrieved, correctly-used chunk at rank 4-5 scores as
a miss under the @3 metrics even though it genuinely reached the LLM and contributed to a
correct answer. The @5 columns are additive (not a replacement) so @3 numbers already cited
in prior reports stay comparable. retrieval_relevance_score is a complementary soft/semantic
LLM-judge signal ("is this chunk topically relevant to the question"), independent of exact
chunk-ID matching -- see app/evaluation/llm_judge.py::judge_retrieval_relevance.

Revision ID: 014
Revises: 013
Create Date: 2026-07-25 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "014"
down_revision = "013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("evaluation_results", sa.Column("precision_at_5", sa.Float(), nullable=True))
    op.add_column("evaluation_results", sa.Column("recall_at_5", sa.Float(), nullable=True))
    op.add_column("evaluation_results", sa.Column("hit_rate_at_5", sa.Float(), nullable=True))
    op.add_column("evaluation_results", sa.Column("retrieval_relevance_score", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("evaluation_results", "retrieval_relevance_score")
    op.drop_column("evaluation_results", "hit_rate_at_5")
    op.drop_column("evaluation_results", "recall_at_5")
    op.drop_column("evaluation_results", "precision_at_5")
