"""Unit tests for the read-only Knowledge Graph query methods (CLAUDE.md §11A.4) backing
GET /api/admin/kg/documents/{id} and GET /api/admin/kg/graph — the admin panel's KG viewer.
Mocks the Neo4j async driver/session so these run without a real database.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.graph_service import GraphService


def make_async_result(records: list[dict]):
    """Build a mock Neo4j result object that supports `async for record in result`
    and `.single()`, matching how GraphService consumes `session.run(...)`."""
    result = MagicMock()

    async def _aiter():
        for r in records:
            yield r

    result.__aiter__ = lambda self=result: _aiter()

    async def _single():
        return records[0] if records else None

    result.single = _single
    return result


def make_mock_session(run_results: list):
    """`run_results` is consumed in call order — one entry per `session.run(...)` call."""
    session = AsyncMock()
    session.run = AsyncMock(side_effect=run_results)
    return session


def patch_driver(session):
    """`driver.session()` (a sync call returning an async context manager) is what the real
    neo4j driver exposes — must not be an AsyncMock method itself, or calling it returns an
    (unawaited) coroutine instead of the context-manager object."""
    session_ctx = MagicMock()
    session_ctx.__aenter__ = AsyncMock(return_value=session)
    session_ctx.__aexit__ = AsyncMock(return_value=False)

    driver = MagicMock()
    driver.session = MagicMock(return_value=session_ctx)
    driver.close = AsyncMock()
    return patch.object(GraphService, "get_driver", AsyncMock(return_value=driver))


@pytest.mark.asyncio
class TestGetGraphForDocument:
    async def test_unknown_document_returns_empty_graph(self):
        session = make_mock_session([make_async_result([])])
        with patch_driver(session):
            result = await GraphService.get_graph_for_document("missing-doc")

        assert result == {"nodes": [], "edges": []}

    async def test_document_with_mentions_and_relation_between_them(self):
        doc_result = make_async_result([{"title": "Pedoman SPMB Jalur Mandiri"}])
        mentions_result = make_async_result(
            [
                {"labels": ["JalurPendaftaran"], "name": "Jalur Mandiri"},
                {"labels": ["Biaya"], "name": "Biaya pendaftaran Rp 350.000"},
            ]
        )
        relations_result = make_async_result(
            [
                {
                    "e1_labels": ["JalurPendaftaran"],
                    "e1_name": "Jalur Mandiri",
                    "rel_type": "MEMILIKI_BIAYA",
                    "e2_labels": ["Biaya"],
                    "e2_name": "Biaya pendaftaran Rp 350.000",
                }
            ]
        )
        session = make_mock_session([doc_result, mentions_result, relations_result])

        with patch_driver(session):
            result = await GraphService.get_graph_for_document("doc-1")

        node_ids = {n["id"] for n in result["nodes"]}
        assert "doc-1" in node_ids
        assert "JalurPendaftaran:Jalur Mandiri" in node_ids
        assert "Biaya:Biaya pendaftaran Rp 350.000" in node_ids

        edge_types = {(e["source"], e["target"], e["type"]) for e in result["edges"]}
        assert ("doc-1", "JalurPendaftaran:Jalur Mandiri", "MENTIONS") in edge_types
        assert (
            "JalurPendaftaran:Jalur Mandiri",
            "Biaya:Biaya pendaftaran Rp 350.000",
            "MEMILIKI_BIAYA",
        ) in edge_types


@pytest.mark.asyncio
class TestGetGraphGlobal:
    async def test_no_nodes_skips_edge_query(self):
        session = make_mock_session([make_async_result([])])
        with patch_driver(session):
            result = await GraphService.get_graph_global(limit=50)

        assert result == {"nodes": [], "edges": []}
        assert session.run.await_count == 1

    async def test_edges_referencing_uncollected_nodes_are_dropped(self):
        """An edge query capped independently of the node query can reference a node that
        didn't make the (also capped) node list — must not emit a dangling edge reference."""
        nodes_result = make_async_result([{"labels": ["JalurPendaftaran"], "name": "Jalur Mandiri"}])
        edges_result = make_async_result(
            [
                {
                    "e1_labels": ["JalurPendaftaran"],
                    "e1_name": "Jalur Mandiri",
                    "rel_type": "MEMILIKI_BIAYA",
                    "e2_labels": ["Biaya"],
                    "e2_name": "Biaya yang tidak ter-load",
                }
            ]
        )
        session = make_mock_session([nodes_result, edges_result])

        with patch_driver(session):
            result = await GraphService.get_graph_global(limit=1)

        assert len(result["nodes"]) == 1
        assert result["edges"] == []
