"""Unit tests for the auto-index-on-approve orchestration added to routes_chunk_review.py.

Approving a chunk used to only update Postgres — a chunk stayed unsearchable in chat until an
admin separately called POST /admin/indexing/run and POST /admin/graph/index-document. These
tests cover the new `_reindex_document` helper that calls both automatically, plus
GraphService.index_document_by_id, which it (and the manual endpoint) both now share.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.api.routes_chunk_review import _reindex_document
from app.services.graph_service import GraphService


@pytest.mark.asyncio
class TestReindexDocumentHelper:
    async def test_calls_vector_index_graph_index_and_cache_invalidation(self):
        db = AsyncMock()
        fake_cache = AsyncMock()

        with patch(
            "app.api.routes_chunk_review.VectorIndexService.index_approved_chunks",
            AsyncMock(return_value={"status": "completed", "indexed_count": 1}),
        ) as mock_vector, patch(
            "app.api.routes_chunk_review.GraphService.index_document_by_id",
            AsyncMock(return_value={"created_nodes": 2, "created_relationships": 1}),
        ) as mock_graph, patch(
            "app.api.routes_chunk_review.get_cache_service",
            AsyncMock(return_value=fake_cache),
        ):
            result = await _reindex_document(db, "doc-123")

        mock_vector.assert_awaited_once_with(db, "doc-123")
        mock_graph.assert_awaited_once_with(db, "doc-123")
        fake_cache.invalidate_retrieval_cache.assert_awaited_once()
        assert result["vector_index"]["indexed_count"] == 1
        assert result["graph_index"]["created_nodes"] == 2


@pytest.mark.asyncio
class TestGraphServiceIndexDocumentById:
    async def test_returns_none_when_document_not_found(self):
        db = AsyncMock()
        doc_result = MagicMock()
        doc_result.scalars.return_value.first.return_value = None
        db.execute = AsyncMock(return_value=doc_result)

        result = await GraphService.index_document_by_id(db, "missing-doc")

        assert result is None

    async def test_looks_up_document_and_summaries_then_indexes(self):
        db = AsyncMock()
        doc = MagicMock(title="SOP Registrasi Ulang")

        doc_result = MagicMock()
        doc_result.scalars.return_value.first.return_value = doc

        chunk_id_1, chunk_id_2, chunk_id_3 = "chunk-1", "chunk-2", "chunk-3"
        rows_result = MagicMock()
        rows_result.all.return_value = [
            (chunk_id_1, "Ringkasan chunk 1"),
            (chunk_id_2, None),
            (chunk_id_3, "Ringkasan chunk 2"),
        ]

        # No chunk_entities rows exist yet for either chunk -> _resolve_chunk_entity_overrides
        # falls back to None for both, so index_document_entities falls back to live extraction.
        entities_result = MagicMock()
        entities_result.scalars.return_value.all.return_value = []

        db.execute = AsyncMock(side_effect=[doc_result, rows_result, entities_result])

        with patch(
            "app.services.graph_service.GraphService.index_document_entities",
            AsyncMock(return_value={"created_nodes": 3, "created_relationships": 2}),
        ) as mock_index:
            result = await GraphService.index_document_by_id(db, "doc-456")

        # None summaries are filtered out before being passed to the indexer; entity
        # overrides are index-aligned with the remaining (chunk-1, chunk-3) summaries.
        mock_index.assert_awaited_once_with(
            "doc-456",
            "SOP Registrasi Ulang",
            ["Ringkasan chunk 1", "Ringkasan chunk 2"],
            [None, None],
        )
        assert result["created_nodes"] == 3
