"""Celery application — broker/scheduler for the periodic official-document sync.

Replaces the previous standalone asyncio loop (`app/workers/document_sync_worker.py`). Two
processes consume this app: `celery -A app.celery_app worker` (executes tasks, see
`app/workers/tasks.py`) and `celery -A app.celery_app beat` (schedules them) — run as separate
`celery-worker`/`celery-beat` containers (docker-compose.*.yml) so the periodic schedule has
exactly one source of truth regardless of how many worker replicas exist.

Reuses the same Redis instance already used by rate_limiter_service.py/redis_cache_service.py as
the broker — no new infrastructure.
"""
from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "campus_virtual_assistant",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.workers.tasks"],
)

celery_app.conf.update(
    task_ignore_result=True,
    timezone="UTC",
    enable_utc=True,
    broker_connection_retry_on_startup=True,
    beat_schedule={
        "sync-documents-periodic": {
            "task": "app.workers.tasks.sync_documents_task",
            "schedule": settings.document_sync_interval_hours * 3600.0,
        },
    },
)
