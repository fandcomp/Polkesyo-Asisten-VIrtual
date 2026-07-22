"""Unit tests for ACIF Gate 4 — Prompt Boundary Builder."""
import pytest

from app.services.acif.prompt_boundary_builder import (
    GraphEvidence,
    PromptBoundaryBuilder,
    VectorChunk,
)


def make_chunk(**overrides) -> VectorChunk:
    defaults = dict(
        content="Syarat pendaftaran jalur mandiri D3 Keperawatan.",
        source_document="Panduan SPMB 2026",
        page=3,
        chunk_id="doc1_chunk3",
        approval_status="approved",
    )
    defaults.update(overrides)
    return VectorChunk(**defaults)


class TestPromptBoundaryBuilderHappyPath:
    def test_builds_prompt_with_system_policy_and_domain_boundary(self):
        result = PromptBoundaryBuilder.build(
            user_message="Apa syarat pendaftaran jalur mandiri?",
            vector_chunks=[make_chunk()],
            graph_evidence=[],
        )

        assert "campus virtual assistant for Poltekkes Kemenkes Yogyakarta" in result.final_prompt
        assert "ALLOWED DOMAINS" in result.final_prompt
        assert "Apa syarat pendaftaran jalur mandiri?" in result.final_prompt
        assert result.context_sources == [
            {
                "document_title": "Panduan SPMB 2026",
                "page": 3,
                "chunk_id": "doc1_chunk3",
                "approval_status": "approved",
            }
        ]

    def test_no_approved_chunks_raises_value_error(self):
        with pytest.raises(ValueError, match="No approved context chunks available"):
            PromptBoundaryBuilder.build(
                user_message="test",
                vector_chunks=[make_chunk(approval_status="pending_review")],
                graph_evidence=[],
            )

    def test_unapproved_chunks_are_filtered_out(self):
        approved = make_chunk(chunk_id="approved-1")
        pending = make_chunk(chunk_id="pending-1", approval_status="pending_review")

        result = PromptBoundaryBuilder.build(
            user_message="test",
            vector_chunks=[approved, pending],
            graph_evidence=[],
        )

        chunk_ids = [s["chunk_id"] for s in result.context_sources]
        assert chunk_ids == ["approved-1"]

    def test_verbatim_original_text_included_when_it_differs_from_summary(self):
        chunk = make_chunk(
            content="Biaya pendaftaran jalur mandiri sekitar Rp 350 ribu.",
            original_text="Biaya pendaftaran jalur mandiri sebesar Rp 350.000 dan tidak dapat dikembalikan.",
        )
        result = PromptBoundaryBuilder.build(
            user_message="Berapa biaya pendaftaran jalur mandiri?",
            vector_chunks=[chunk],
            graph_evidence=[],
        )

        assert "VERBATIM ORIGINAL TEXT" in result.vector_context
        assert "Rp 350.000" in result.vector_context

    def test_verbatim_block_omitted_when_original_text_missing(self):
        chunk = make_chunk(original_text=None)
        result = PromptBoundaryBuilder.build(
            user_message="test", vector_chunks=[chunk], graph_evidence=[]
        )

        assert "VERBATIM ORIGINAL TEXT" not in result.vector_context

    def test_verbatim_block_omitted_when_identical_to_summary(self):
        chunk = make_chunk(
            content="Biaya pendaftaran Rp 350.000.",
            original_text="Biaya pendaftaran Rp 350.000.",
        )
        result = PromptBoundaryBuilder.build(
            user_message="test", vector_chunks=[chunk], graph_evidence=[]
        )

        assert "VERBATIM ORIGINAL TEXT" not in result.vector_context

    def test_chunks_capped_at_max_context_chunks_default(self):
        # Default max_context_chunks is 5 (matches settings.max_context_chunks) — a 6th chunk
        # should be dropped.
        chunks = [make_chunk(chunk_id=f"c{i}") for i in range(6)]
        result = PromptBoundaryBuilder.build(
            user_message="test", vector_chunks=chunks, graph_evidence=[]
        )
        assert len(result.context_sources) == 5

    def test_graph_evidence_rendered_with_entities_and_relationships(self):
        evidence = [
            GraphEvidence(
                entity_type="ProgramStudi",
                entity_name="D3 Keperawatan",
                relationships=["MEMILIKI_JALUR"],
                confidence=0.9,
            )
        ]
        result = PromptBoundaryBuilder.build(
            user_message="test", vector_chunks=[make_chunk()], graph_evidence=evidence
        )
        assert "ProgramStudi: D3 Keperawatan" in result.graph_evidence
        assert "MEMILIKI_JALUR" in result.graph_evidence
        assert "90.0%" in result.graph_evidence

    def test_no_graph_evidence_shows_placeholder(self):
        result = PromptBoundaryBuilder.build(
            user_message="test", vector_chunks=[make_chunk()], graph_evidence=[]
        )
        assert result.graph_evidence == "(No graph evidence available)"

    def test_history_truncated_to_last_five_turns(self):
        history = [{"role": "user", "message": f"turn {i}"} for i in range(8)]
        result = PromptBoundaryBuilder.build(
            user_message="test",
            vector_chunks=[make_chunk()],
            graph_evidence=[],
            conversation_history=history,
        )
        assert "turn 0" not in result.conversation_history
        assert "turn 7" in result.conversation_history

    def test_exceeding_token_budget_raises_value_error(self):
        huge_chunk = make_chunk(content="x" * 20000)
        with pytest.raises(ValueError, match="exceeds token budget"):
            PromptBoundaryBuilder.build(
                user_message="test",
                vector_chunks=[huge_chunk],
                graph_evidence=[],
                max_tokens=10,
            )


class TestPromptBoundaryBuilderBudgetDegradation:
    """When real chunks are long, the builder must trim context to fit the token
    budget instead of failing the whole request (production incident 2026-07-09:
    5 chunks + verbatim originals = 4711 tokens > 4500 budget → every /chat on
    that topic returned status=error)."""

    def test_drops_verbatim_originals_before_failing(self):
        # 5 chunks × (1500 summary + 1500 original) chars ≈ 3800+ tokens of context;
        # with prompt overhead this exceeds 4500 — dropping originals makes it fit.
        chunks = [
            make_chunk(
                chunk_id=f"c{i}",
                content=f"ringkasan {i} " + "isi dokumen resmi " * 83,
                original_text=f"teks asli {i} " + "naskah verbatim dokumen " * 62,
            )
            for i in range(5)
        ]
        result = PromptBoundaryBuilder.build(
            user_message="Apa syarat pendaftaran?",
            vector_chunks=chunks,
            graph_evidence=[],
            max_tokens=4500,
        )
        assert result.token_count <= 4500
        assert "VERBATIM ORIGINAL TEXT" not in result.vector_context
        # All 5 summaries survive — only the originals were sacrificed.
        assert len(result.context_sources) == 5

    def test_drops_lowest_ranked_chunks_when_originals_alone_not_enough(self):
        # Even without originals, 5 max-length summaries overflow a small budget —
        # the builder must shed trailing (lowest-ranked) chunks, not raise.
        chunks = [
            make_chunk(chunk_id=f"c{i}", content=f"chunk {i} " + "x" * 1590)
            for i in range(5)
        ]
        result = PromptBoundaryBuilder.build(
            user_message="test",
            vector_chunks=chunks,
            graph_evidence=[],
            max_tokens=2000,
        )
        assert result.token_count <= 2000
        assert len(result.context_sources) < 5
        # Best-ranked chunk is always kept.
        assert result.context_sources[0]["chunk_id"] == "c0"


class TestPromptBoundaryBuilderRejectsRawDicts:
    """build()'s graph_evidence parameter is typed list[GraphEvidence] and
    _build_graph_section accesses item.entity_type / item.entity_name as
    attributes — Python doesn't enforce this at the call site, so a raw dict
    would blow up on attribute access. chat_core.py used to pass
    GraphRetrieverService's raw dicts straight through here, which crashed on
    any non-empty GraphRAG result; it now converts them to GraphEvidence
    objects before calling build() (see ChatCoreService.process_message).
    This test keeps the module's own type contract honest regardless of how
    callers behave."""

    def test_raw_dict_graph_evidence_still_raises(self):
        graph_results_from_retriever = [{"entity_type": "ProgramStudi", "entity_name": "D3 Keperawatan"}]

        with pytest.raises(AttributeError):
            PromptBoundaryBuilder.build(
                user_message="test",
                vector_chunks=[make_chunk()],
                graph_evidence=graph_results_from_retriever,
            )

    def test_chat_core_conversion_pattern_prevents_the_crash(self):
        """Mirrors the exact conversion chat_core.ChatCoreService.process_message
        now applies to GraphRetrieverService's raw output before calling
        build() — pins that the fix actually resolves the crash above."""
        graph_results_from_retriever = [
            {"entity_type": "ProgramStudi", "entity_name": "D3 Keperawatan"},
            {"entity_type": "JalurPendaftaran"},  # missing entity_name, as chat_core defensively handles
        ]

        graph_evidence = [
            GraphEvidence(
                entity_type=g.get("entity_type", "Unknown"),
                entity_name=g.get("entity_name", ""),
            )
            for g in graph_results_from_retriever
        ]

        result = PromptBoundaryBuilder.build(
            user_message="test",
            vector_chunks=[make_chunk()],
            graph_evidence=graph_evidence,
        )

        assert "ProgramStudi: D3 Keperawatan" in result.graph_evidence
        assert "JalurPendaftaran:" in result.graph_evidence


class TestBuildNaiveAblationBaseline:
    """build_naive() is the without-ACIF ablation condition's prompt path (Evaluation Layer
    Phase 5) — a plain "stuff the context into the prompt" baseline, deliberately without the
    NON-NEGOTIABLE POLICY / DOMAIN BOUNDARY separation that build() applies."""

    def test_omits_policy_and_domain_boundary_sections(self):
        result = PromptBoundaryBuilder.build_naive(
            user_message="Apa syarat pendaftaran jalur mandiri?",
            vector_chunks=[make_chunk()],
        )

        assert "NON-NEGOTIABLE" not in result.final_prompt
        assert "ALLOWED DOMAINS" not in result.final_prompt
        assert "Apa syarat pendaftaran jalur mandiri?" in result.final_prompt
        assert "Syarat pendaftaran jalur mandiri D3 Keperawatan." in result.final_prompt

    def test_context_sources_match_build(self):
        chunk = make_chunk()
        result = PromptBoundaryBuilder.build_naive(
            user_message="test",
            vector_chunks=[chunk],
        )
        assert result.context_sources == [
            {
                "document_title": "Panduan SPMB 2026",
                "page": 3,
                "chunk_id": "doc1_chunk3",
                "approval_status": "approved",
            }
        ]

    def test_respects_max_context_chunks(self):
        chunks = [make_chunk(chunk_id=f"c{i}", content=f"content {i}") for i in range(5)]
        result = PromptBoundaryBuilder.build_naive(
            user_message="test", vector_chunks=chunks, max_context_chunks=2
        )
        assert len(result.context_sources) == 2

    def test_raises_when_no_chunks_available(self):
        with pytest.raises(ValueError):
            PromptBoundaryBuilder.build_naive(user_message="test", vector_chunks=[])
