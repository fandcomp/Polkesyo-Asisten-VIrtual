"""The Chroma HttpClient must be created once per process and reused.

Regression test for the 2026-07-10 production incident: a fresh HttpClient per call
(every /health heartbeat, every chat search) leaked its TCP connections until workers
hit the 1024-fd ulimit, and the resulting pipeline failures surfaced to users as bogus
"Sesi Anda tidak ditemukan atau sudah berakhir" chat errors.
"""
from unittest.mock import MagicMock

import pytest

import app.services.vector_index_service as vis
from app.services.vector_index_service import VectorIndexService


@pytest.fixture(autouse=True)
def _reset_cached_client():
    vis._chroma_client = None
    yield
    vis._chroma_client = None


def test_get_chroma_client_creates_only_one_instance(monkeypatch):
    instances = []

    def fake_http_client(**kwargs):
        client = MagicMock(name="chroma_http_client")
        instances.append(client)
        return client

    monkeypatch.setattr(vis.chromadb, "HttpClient", fake_http_client)

    first = VectorIndexService.get_chroma_client()
    second = VectorIndexService.get_chroma_client()

    assert first is second
    assert len(instances) == 1


def test_health_heartbeat_reuses_cached_client(monkeypatch):
    from app.api import routes_health

    instances = []

    def fake_http_client(**kwargs):
        client = MagicMock(name="chroma_http_client")
        instances.append(client)
        return client

    monkeypatch.setattr(vis.chromadb, "HttpClient", fake_http_client)

    routes_health._chroma_heartbeat_sync()
    routes_health._chroma_heartbeat_sync()

    assert len(instances) == 1
    assert instances[0].heartbeat.call_count == 2
