"""Evaluation Layer retention/cleanup — deletes rows older than EVALUATION_RETENTION_DAYS.

Manual invocation only: `python -m app.evaluation.cleanup_old_logs` (run via cron on the VPS
host, or manually) — never scheduled automatically inside the app, matching the runner's own
"no automatic startup trigger" convention (Part 9 principle 9).

Deletes from the Phase 1 per-trace logging tables (chat_evaluation_logs and its children).
evaluation_runs/evaluation_results/asq_responses/sus_responses are intentionally NOT covered
by this retention sweep — those are durable academic-reporting artifacts (evaluation results,
usability survey responses), not high-volume operational logs, and deleting a completed
research run's data on a timer would be actively harmful to the thesis this system supports.
"""
import asyncio
import logging
from datetime import datetime, timedelta

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.db.models import (
    AcifTraceLog,
    ChatEvaluationLog,
    CitationEvaluationLog,
    GraphConsistencyLog,
    RetrievalEvaluationLog,
)

logger = logging.getLogger(__name__)

_TABLES_BY_TRACE_ID = [RetrievalEvaluationLog, CitationEvaluationLog, AcifTraceLog, GraphConsistencyLog]


async def cleanup_old_logs(retention_days: int | None = None) -> dict[str, int]:
    """Delete chat_evaluation_logs (and every row in the 4 child tables sharing its trace_id)
    older than `retention_days` (defaults to settings.evaluation_retention_days). Returns a
    dict of table_name -> rows_deleted for logging/verification."""
    days = retention_days if retention_days is not None else settings.evaluation_retention_days
    cutoff = datetime.utcnow() - timedelta(days=days)

    engine = create_async_engine(settings.database_url)
    db_factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    deleted_counts: dict[str, int] = {}

    async with db_factory() as db:
        # Find the trace_ids being retired before deleting anything, so the 4 child tables
        # (which have no created_at cutoff of their own that reliably lines up with the
        # parent — a trace's rows are all written within the same request) can be cleaned
        # by trace_id rather than duplicating the same date-cutoff logic 5 times.
        old_trace_ids_result = await db.execute(
            ChatEvaluationLog.__table__.select()
            .with_only_columns(ChatEvaluationLog.trace_id)
            .where(ChatEvaluationLog.created_at < cutoff)
        )
        old_trace_ids = [row[0] for row in old_trace_ids_result.all()]

        if not old_trace_ids:
            logger.info(f"No chat_evaluation_logs older than {days} days — nothing to clean up.")
            await engine.dispose()
            return {"chat_evaluation_logs": 0}

        for model in _TABLES_BY_TRACE_ID:
            result = await db.execute(delete(model).where(model.trace_id.in_(old_trace_ids)))
            deleted_counts[model.__tablename__] = result.rowcount or 0

        result = await db.execute(delete(ChatEvaluationLog).where(ChatEvaluationLog.trace_id.in_(old_trace_ids)))
        deleted_counts["chat_evaluation_logs"] = result.rowcount or 0

        await db.commit()

    logger.info(f"Evaluation Layer retention cleanup (cutoff={cutoff.isoformat()}, {days}d): {deleted_counts}")
    await engine.dispose()
    return deleted_counts


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(cleanup_old_logs())
