"""Celery tasks for the official-document sync (replaces app/workers/document_sync_worker.py).

The task itself is a thin sync wrapper around the async pipeline — Celery tasks are sync
entrypoints, so each run gets its own asyncio event loop via asyncio.run(), same pattern already
used by this repo's other standalone-script entrypoints (run_evaluation.py, cleanup_old_logs.py).
"""
import asyncio
import logging

from celery.signals import worker_ready

from app.agents.document_monitor_agent import DocumentMonitorAgent
from app.celery_app import celery_app
from app.core.config import settings
from app.db.session import AsyncSessionLocal

logger = logging.getLogger(__name__)


async def _sync_documents_async() -> None:
    """Delegate the actual fetch/parse/diff/download/classify/ingest work to
    DocumentMonitorAgent.execute() (CLAUDE.md §11A.3) — this function is just the scheduling
    shell, as CLAUDE.md §21.8 specifies."""
    if not settings.document_sync_enabled:
        logger.info("Document sync disabled (DOCUMENT_SYNC_ENABLED=false)")
        return

    logger.info("Starting document synchronization...")

    async with AsyncSessionLocal() as db:
        agent_result = await DocumentMonitorAgent().execute(
            {"db": db, "source_url": settings.document_sync_source_url},
            db=db,
            task_type="scheduled_sync",
        )
        result = agent_result.output or {"errors": [agent_result.error or "unknown error"]}

        logger.info(
            f"Sync completed: "
            f"{result.get('total_found', 0)} found, "
            f"{result.get('total_new', 0)} new, "
            f"{result.get('total_updated', 0)} updated"
        )

        if result.get("errors"):
            logger.warning(f"Sync errors: {result['errors']}")


@celery_app.task(name="app.workers.tasks.sync_documents_task", ignore_result=True)
def sync_documents_task() -> None:
    asyncio.run(_sync_documents_async())


@worker_ready.connect
def _trigger_sync_on_startup(**kwargs) -> None:
    """Fire a sync immediately when the celery-worker process comes up, matching the previous
    worker's behavior of always syncing on startup rather than waiting a full interval (verified
    important in IMPLEMENTATION.md's 2026-07-21 deploy notes). Registered only on the worker
    process (this module), not celery-beat, so a simultaneous restart of both containers doesn't
    double-fire."""
    logger.info("celery-worker ready — triggering initial document sync")
    sync_documents_task.delay()
