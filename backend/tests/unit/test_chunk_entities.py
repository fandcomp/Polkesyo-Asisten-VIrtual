"""Unit tests for the chunk_entities feature: materialization idempotency, the
edit/confirm/reject/add transitions in ChunkEntityService, and the reindexing entity-list-
selection logic in GraphService._resolve_chunk_entity_overrides / index_document_entities.

Follows this repo's existing AsyncMock(db)-based unit-test convention (see
test_reindex_on_approve.py) rather than a real async DB session fixture, since no such
fixture exists in this test suite yet.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from app.services.chunk_entity_service import (
    ChunkEntityNotFoundError,
    ChunkEntityService,
    ChunkEntityValidationError,
)
from app.services.graph_service import GraphService


def _make_chunk(chunk_id=None, document_id=None, text="Jalur Mandiri wajib melampirkan ijazah SMA/sederajat."):
    chunk = MagicMock()
    chunk.id = chunk_id or uuid4()
    chunk.document_id = document_id or uuid4()
    chunk.original_text = text
    return chunk


class _FakeAsyncCM:
    """Minimal async context manager stand-in for `driver.session()`."""

    def __init__(self, value):
        self._value = value

    async def __aenter__(self):
        return self._value

    async def __aexit__(self, *exc):
        return False


def _fake_driver():
    driver = MagicMock()
    session = AsyncMock()
    driver.session.return_value = _FakeAsyncCM(session)
    driver.close = AsyncMock()
    return driver, session


@pytest.mark.asyncio
class TestListForChunkMaterialization:
    async def test_materializes_detected_entities_when_none_exist(self):
        db = AsyncMock()
        chunk = _make_chunk()

        chunk_result = MagicMock()
        chunk_result.scalars.return_value.first.return_value = chunk

        empty_rows_result = MagicMock()
        empty_rows_result.scalars.return_value.all.return_value = []

        db.execute = AsyncMock(side_effect=[chunk_result, empty_rows_result])
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        db.add = MagicMock()  # AsyncSession.add() is sync even on an async session

        with patch(
            "app.services.chunk_entity_service.GraphService.extract_entities",
            return_value=[("JalurPendaftaran", "Jalur Mandiri"), ("Persyaratan", "ijazah")],
        ):
            entities = await ChunkEntityService.list_for_chunk(db, chunk.id)

        assert len(entities) == 2
        assert {e.entity_type for e in entities} == {"JalurPendaftaran", "Persyaratan"}
        assert all(e.status == "detected" for e in entities)
        assert all(e.source == "llm_detected" for e in entities)
        db.commit.assert_awaited_once()

    async def test_does_not_rematerialize_when_rows_already_exist(self):
        """Idempotency: a chunk with existing rows is never re-extracted, even if
        extract_entities would now produce a different result."""
        db = AsyncMock()
        chunk = _make_chunk()
        existing_entity = MagicMock(entity_type="Biaya", status="confirmed")

        chunk_result = MagicMock()
        chunk_result.scalars.return_value.first.return_value = chunk

        existing_rows_result = MagicMock()
        existing_rows_result.scalars.return_value.all.return_value = [existing_entity]

        db.execute = AsyncMock(side_effect=[chunk_result, existing_rows_result])

        with patch(
            "app.services.chunk_entity_service.GraphService.extract_entities"
        ) as mock_extract:
            entities = await ChunkEntityService.list_for_chunk(db, chunk.id)

        mock_extract.assert_not_called()
        assert entities == [existing_entity]

    async def test_raises_not_found_for_missing_chunk(self):
        db = AsyncMock()
        chunk_result = MagicMock()
        chunk_result.scalars.return_value.first.return_value = None
        db.execute = AsyncMock(return_value=chunk_result)

        with pytest.raises(ChunkEntityNotFoundError):
            await ChunkEntityService.list_for_chunk(db, uuid4())


@pytest.mark.asyncio
class TestEditConfirmRejectAddTransitions:
    async def test_edit_sets_corrected_fields_and_status_edited(self):
        db = AsyncMock()
        entity = MagicMock(entity_type="ProgramStudi", corrected_text=None, corrected_type=None)
        entity_result = MagicMock()
        entity_result.scalars.return_value.first.return_value = entity
        db.execute = AsyncMock(return_value=entity_result)
        db.commit = AsyncMock()
        db.refresh = AsyncMock()

        result = await ChunkEntityService.edit_entity(
            db, uuid4(), corrected_text="D-III Kebidanan", corrected_type="ProgramStudi"
        )

        assert result.corrected_text == "D-III Kebidanan"
        assert result.corrected_type == "ProgramStudi"
        assert result.status == "edited"
        assert result.reviewed_at is not None

    async def test_edit_rejects_invalid_corrected_type(self):
        db = AsyncMock()

        with pytest.raises(ChunkEntityValidationError):
            await ChunkEntityService.edit_entity(
                db, uuid4(), corrected_text=None, corrected_type="NotARealType"
            )
        db.execute.assert_not_called()

    async def test_confirm_sets_status_confirmed(self):
        db = AsyncMock()
        entity = MagicMock()
        entity_result = MagicMock()
        entity_result.scalars.return_value.first.return_value = entity
        db.execute = AsyncMock(return_value=entity_result)
        db.commit = AsyncMock()
        db.refresh = AsyncMock()

        result = await ChunkEntityService.confirm_entity(db, uuid4())

        assert result.status == "confirmed"
        assert result.reviewed_at is not None

    async def test_reject_sets_status_rejected_never_hard_deletes(self):
        db = AsyncMock()
        entity = MagicMock()
        entity_result = MagicMock()
        entity_result.scalars.return_value.first.return_value = entity
        db.execute = AsyncMock(return_value=entity_result)
        db.commit = AsyncMock()
        db.refresh = AsyncMock()

        result = await ChunkEntityService.reject_entity(db, uuid4())

        assert result.status == "rejected"
        # Rejection is the only "delete" mechanism -- the row itself is never removed.
        assert not db.delete.called

    async def test_add_entity_creates_confirmed_admin_added_row(self):
        db = AsyncMock()
        chunk = _make_chunk()
        chunk_result = MagicMock()
        chunk_result.scalars.return_value.first.return_value = chunk
        db.execute = AsyncMock(return_value=chunk_result)
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        db.add = MagicMock()

        entity = await ChunkEntityService.add_entity(db, chunk.id, "Biaya", "Rp 500.000")

        assert entity.source == "admin_added"
        assert entity.status == "confirmed"
        assert entity.detected_text == "Rp 500.000"
        db.add.assert_called_once()

    async def test_add_entity_rejects_invalid_type(self):
        db = AsyncMock()

        with pytest.raises(ChunkEntityValidationError):
            await ChunkEntityService.add_entity(db, uuid4(), "NotAType", "text")
        db.execute.assert_not_called()


@pytest.mark.asyncio
class TestResolveChunkEntityOverrides:
    """GraphService._resolve_chunk_entity_overrides: the reindex-time selection logic."""

    async def test_confirmed_and_edited_included_detected_and_rejected_excluded(self):
        db = AsyncMock()
        chunk_id = uuid4()

        row_confirmed = MagicMock(
            chunk_id=chunk_id, entity_type="Biaya", detected_text="Rp 300.000",
            corrected_text=None, corrected_type=None, status="confirmed",
        )
        row_edited = MagicMock(
            chunk_id=chunk_id, entity_type="ProgramStudi", detected_text="D3 Kebidanan",
            corrected_text="D-III Kebidanan", corrected_type=None, status="edited",
        )
        row_detected = MagicMock(
            chunk_id=chunk_id, entity_type="Jadwal", detected_text="28 April 2026",
            corrected_text=None, corrected_type=None, status="detected",
        )
        row_rejected = MagicMock(
            chunk_id=chunk_id, entity_type="Persyaratan", detected_text="ijazah",
            corrected_text=None, corrected_type=None, status="rejected",
        )

        entities_result = MagicMock()
        entities_result.scalars.return_value.all.return_value = [
            row_confirmed, row_edited, row_detected, row_rejected,
        ]
        db.execute = AsyncMock(return_value=entities_result)

        overrides = await GraphService._resolve_chunk_entity_overrides(db, [chunk_id])

        assert overrides == [[("Biaya", "Rp 300.000"), ("ProgramStudi", "D-III Kebidanan")]]

    async def test_zero_rows_for_chunk_falls_back_to_none(self):
        db = AsyncMock()
        chunk_id = uuid4()
        entities_result = MagicMock()
        entities_result.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(return_value=entities_result)

        overrides = await GraphService._resolve_chunk_entity_overrides(db, [chunk_id])

        assert overrides == [None]

    async def test_empty_chunk_ids_returns_empty_list_without_query(self):
        db = AsyncMock()

        overrides = await GraphService._resolve_chunk_entity_overrides(db, [])

        assert overrides == []
        db.execute.assert_not_called()

    async def test_mixed_chunks_some_with_rows_some_without(self):
        db = AsyncMock()
        chunk_with_rows = uuid4()
        chunk_without_rows = uuid4()

        row = MagicMock(
            chunk_id=chunk_with_rows, entity_type="Biaya", detected_text="Rp 300.000",
            corrected_text=None, corrected_type=None, status="confirmed",
        )
        entities_result = MagicMock()
        entities_result.scalars.return_value.all.return_value = [row]
        db.execute = AsyncMock(return_value=entities_result)

        overrides = await GraphService._resolve_chunk_entity_overrides(
            db, [chunk_with_rows, chunk_without_rows]
        )

        assert overrides == [[("Biaya", "Rp 300.000")], None]

    async def test_chunk_with_only_unreviewed_rows_contributes_nothing_no_fallback(self):
        """A materialized-but-untouched chunk (all rows still 'detected') is NOT the same as
        a zero-rows chunk: it must contribute an empty list, not trigger the extraction
        fallback -- otherwise a half-reviewed document would silently mix curated and
        freshly-re-extracted entities."""
        db = AsyncMock()
        chunk_id = uuid4()
        row_detected = MagicMock(
            chunk_id=chunk_id, entity_type="Jadwal", detected_text="28 April 2026",
            corrected_text=None, corrected_type=None, status="detected",
        )
        entities_result = MagicMock()
        entities_result.scalars.return_value.all.return_value = [row_detected]
        db.execute = AsyncMock(return_value=entities_result)

        overrides = await GraphService._resolve_chunk_entity_overrides(db, [chunk_id])

        assert overrides == [[]]


@pytest.mark.asyncio
class TestIndexDocumentEntitiesUsesOverrides:
    """GraphService.index_document_entities: override list vs. live-extraction fallback."""

    async def test_uses_override_list_instead_of_live_extraction_when_present(self):
        driver, _session = _fake_driver()

        with patch(
            "app.services.graph_service.GraphService.get_driver", AsyncMock(return_value=driver)
        ), patch("app.services.graph_service.GraphService.extract_entities") as mock_extract:
            result = await GraphService.index_document_entities(
                "doc-1", "Some Document", ["summary text"], [[("Biaya", "Rp 300.000")]]
            )

        mock_extract.assert_not_called()
        assert result["errors"] == []

    async def test_falls_back_to_extraction_when_override_is_none(self):
        driver, _session = _fake_driver()

        with patch(
            "app.services.graph_service.GraphService.get_driver", AsyncMock(return_value=driver)
        ), patch(
            "app.services.graph_service.GraphService.extract_entities",
            return_value=[("Biaya", "Rp 300.000")],
        ) as mock_extract:
            await GraphService.index_document_entities(
                "doc-1", "Some Document", ["summary text"], [None]
            )

        mock_extract.assert_called_once_with("summary text")

    async def test_no_overrides_argument_preserves_legacy_behavior(self):
        """Callers that never pass chunk_entity_overrides (None) must behave exactly as
        before this feature -- always live extraction."""
        driver, _session = _fake_driver()

        with patch(
            "app.services.graph_service.GraphService.get_driver", AsyncMock(return_value=driver)
        ), patch(
            "app.services.graph_service.GraphService.extract_entities",
            return_value=[],
        ) as mock_extract:
            await GraphService.index_document_entities("doc-1", "Some Document", ["summary text"])

        mock_extract.assert_called_once_with("summary text")
