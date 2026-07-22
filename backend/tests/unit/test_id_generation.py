"""Unit tests for the deterministic chunk-id helper (evaluation-validity fix).

Covers the property the fix depends on: chunk_id_for must be a pure function of
(document_version_id, chunk_index, chunk_kind) so re-ingesting an unchanged document version
reproduces the same chunk ids instead of new random uuid4()s.
"""
from uuid import uuid4

from app.services.id_generation import chunk_id_for


class TestChunkIdFor:
    def test_deterministic_for_same_inputs(self):
        version_id = uuid4()
        assert chunk_id_for(version_id, 0, "text") == chunk_id_for(version_id, 0, "text")

    def test_different_chunk_index_yields_different_id(self):
        version_id = uuid4()
        assert chunk_id_for(version_id, 0, "text") != chunk_id_for(version_id, 1, "text")

    def test_different_document_version_yields_different_id(self):
        assert chunk_id_for(uuid4(), 0, "text") != chunk_id_for(uuid4(), 0, "text")

    def test_text_and_image_do_not_collide_on_same_index(self):
        version_id = uuid4()
        assert chunk_id_for(version_id, 0, "text") != chunk_id_for(version_id, 0, "image")

    def test_accepts_string_document_version_id(self):
        version_id = uuid4()
        assert chunk_id_for(str(version_id), 3, "text") == chunk_id_for(version_id, 3, "text")

    def test_default_chunk_kind_is_text(self):
        version_id = uuid4()
        assert chunk_id_for(version_id, 0) == chunk_id_for(version_id, 0, "text")
