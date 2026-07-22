"""Unit tests for the Celery-based document sync (replaces app/workers/document_sync_worker.py).

Covers the 2026-07-22 migration to Celery + Celery Beat: the periodic schedule must be computed
from settings (not hardcoded), the task must delegate to DocumentMonitorAgent using the shared
AsyncSessionLocal (not a fresh engine), the enabled-flag short-circuit must still hold, and the
worker-startup signal must fire the sync exactly once — the same guarantees the old asyncio-loop
worker provided.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.celery_app import celery_app
from app.core.config import settings
from app.workers import tasks as tasks_module


def test_beat_schedule_computed_from_settings():
    entry = celery_app.conf.beat_schedule["sync-documents-periodic"]
    assert entry["task"] == "app.workers.tasks.sync_documents_task"
    assert entry["schedule"] == settings.document_sync_interval_hours * 3600.0


@pytest.mark.asyncio
async def test_sync_documents_async_delegates_to_document_monitor_agent(monkeypatch):
    monkeypatch.setattr(tasks_module.settings, "document_sync_enabled", True)
    monkeypatch.setattr(tasks_module.settings, "document_sync_source_url", "https://example.test/docs")

    fake_db = MagicMock()
    session_cm = AsyncMock()
    session_cm.__aenter__.return_value = fake_db
    session_cm.__aexit__.return_value = None
    mock_session_local = MagicMock(return_value=session_cm)

    agent_result = MagicMock(output={"total_found": 3, "total_new": 1, "total_updated": 0}, error=None)
    mock_execute = AsyncMock(return_value=agent_result)
    mock_agent_instance = MagicMock(execute=mock_execute)
    mock_agent_cls = MagicMock(return_value=mock_agent_instance)

    with patch.object(tasks_module, "AsyncSessionLocal", mock_session_local), \
         patch.object(tasks_module, "DocumentMonitorAgent", mock_agent_cls):
        await tasks_module._sync_documents_async()

    mock_execute.assert_awaited_once_with(
        {"db": fake_db, "source_url": "https://example.test/docs"},
        db=fake_db,
        task_type="scheduled_sync",
    )


@pytest.mark.asyncio
async def test_sync_documents_async_short_circuits_when_disabled(monkeypatch):
    monkeypatch.setattr(tasks_module.settings, "document_sync_enabled", False)

    mock_agent_cls = MagicMock()

    with patch.object(tasks_module, "DocumentMonitorAgent", mock_agent_cls):
        await tasks_module._sync_documents_async()

    mock_agent_cls.assert_not_called()


def test_worker_ready_signal_triggers_sync_exactly_once():
    with patch.object(tasks_module.sync_documents_task, "delay") as mock_delay:
        tasks_module._trigger_sync_on_startup(sender=MagicMock())

    mock_delay.assert_called_once_with()
