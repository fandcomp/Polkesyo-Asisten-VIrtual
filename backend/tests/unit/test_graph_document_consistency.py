"""Unit tests for ACIF Gate 3 — Graph-Document Consistency Check."""
import pytest

from app.services.acif.graph_document_consistency import GraphDocumentConsistency


@pytest.mark.asyncio
class TestGraphDocumentConsistency:
    async def test_no_graph_evidence_proceeds_with_caution(self):
        chunk = {"chunk_id": "c1", "content": "syarat pendaftaran D3 Keperawatan"}
        result = await GraphDocumentConsistency.check_consistency(chunk, [])

        assert result["decision"] == "proceed_with_caution"
        assert result["consistency_score"] == 0.5

    async def test_all_entities_present_is_highly_consistent(self):
        chunk = {"chunk_id": "c1", "content": "syarat pendaftaran d3 keperawatan jalur mandiri"}
        graph_entities = [
            {"entity_type": "ProgramStudi", "entity_name": "D3 Keperawatan"},
            {"entity_type": "JalurPendaftaran", "entity_name": "Jalur Mandiri"},
        ]
        result = await GraphDocumentConsistency.check_consistency(chunk, graph_entities)

        assert result["consistency_score"] == 1.0
        assert result["entity_matches"] == 2
        assert result["total_entities"] == 2
        assert result["decision"] == "highly_consistent"

    async def test_partial_entity_match_is_consistent(self):
        chunk = {"chunk_id": "c1", "content": "informasi tentang d3 keperawatan"}
        graph_entities = [
            {"entity_type": "ProgramStudi", "entity_name": "D3 Keperawatan"},
            {"entity_type": "JalurPendaftaran", "entity_name": "Jalur Mandiri"},
        ]
        result = await GraphDocumentConsistency.check_consistency(chunk, graph_entities)

        assert result["consistency_score"] == pytest.approx(0.5)
        assert result["decision"] == "consistent"

    async def test_different_program_flags_inconsistent(self):
        """Mismatched program/pathway (CLAUDE.md §11.4): the chunk identifies itself as
        being about a DIFFERENT study program than the graph evidence supports."""
        chunk = {"chunk_id": "c1", "content": "informasi pendaftaran D-III Gizi tahun ini"}
        graph_entities = [
            {"entity_type": "ProgramStudi", "entity_name": "D-III Keperawatan"},
        ]
        result = await GraphDocumentConsistency.check_consistency(chunk, graph_entities)

        assert result["consistency_score"] == 0.0
        assert result["decision"] == "inconsistent_flag"

    async def test_different_jalur_flags_inconsistent(self):
        chunk = {"chunk_id": "c1", "content": "pengumuman hasil SPMB Prestasi gelombang 2"}
        graph_entities = [
            {"entity_type": "JalurPendaftaran", "entity_name": "Jalur Mandiri"},
        ]
        result = await GraphDocumentConsistency.check_consistency(chunk, graph_entities)

        assert result["decision"] == "inconsistent_flag"

    async def test_zero_mentions_without_conflict_proceeds_with_caution(self):
        """Uncorroborated is not contradicted: a chunk that names no graph entity and no
        competing program/jalur must NOT be rejected (it just gets no graph credit).
        Treating 'no mention' as inconsistent rejected approved on-topic chunks whenever
        the graph was sparse — the false-fallback bug this distinction fixes."""
        chunk = {"chunk_id": "c1", "content": "persyaratan umum calon mahasiswa baru"}
        graph_entities = [
            {"entity_type": "ProgramStudi", "entity_name": "D-III Keperawatan"},
            {"entity_type": "JalurPendaftaran", "entity_name": "Jalur Mandiri"},
        ]
        result = await GraphDocumentConsistency.check_consistency(chunk, graph_entities)

        assert result["entity_matches"] == 0
        assert result["decision"] == "proceed_with_caution"

    async def test_entity_without_name_never_matches_and_never_conflicts(self):
        chunk = {"chunk_id": "c1", "content": "informasi umum kampus"}
        graph_entities = [{"entity_type": "ProgramStudi"}]  # missing "entity_name" key
        result = await GraphDocumentConsistency.check_consistency(chunk, graph_entities)

        assert result["entity_matches"] == 0
        assert result["decision"] == "proceed_with_caution"
