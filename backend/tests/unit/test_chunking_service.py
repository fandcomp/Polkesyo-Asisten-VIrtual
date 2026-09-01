"""Unit tests for ChunkingService.

Pins the infinite-loop regression: text shorter than chunk_size used to make
chunk_text() loop forever re-appending the tail chunk (start = end - overlap
never advanced past the end), blocking the whole event loop during ingestion.
"""
import pytest

from app.services.chunking_service import ChunkingService


def _words(n: int) -> str:
    return " ".join(f"w{i}" for i in range(n))


class TestChunkText:
    def test_empty_text_returns_no_chunks(self):
        assert ChunkingService.chunk_text("", chunk_size_tokens=500, overlap_tokens=100) == []

    def test_text_shorter_than_chunk_size_returns_single_chunk(self):
        # Regression: this input previously never terminated.
        text = _words(120)
        chunks = ChunkingService.chunk_text(text, chunk_size_tokens=500, overlap_tokens=100)
        assert chunks == [text]

    def test_text_exactly_chunk_size_returns_single_chunk(self):
        text = _words(500)
        chunks = ChunkingService.chunk_text(text, chunk_size_tokens=500, overlap_tokens=100)
        assert chunks == [text]

    def test_longer_text_produces_overlapping_chunks(self):
        chunks = ChunkingService.chunk_text(_words(900), chunk_size_tokens=500, overlap_tokens=100)
        assert len(chunks) == 2
        first_tokens = chunks[0].split()
        second_tokens = chunks[1].split()
        assert len(first_tokens) == 500
        # Second chunk starts at token 400 (500 - 100 overlap) and runs to the end
        assert second_tokens[0] == "w400"
        assert second_tokens[-1] == "w899"

    def test_all_tokens_covered_without_duplicate_tail(self):
        chunks = ChunkingService.chunk_text(_words(1300), chunk_size_tokens=500, overlap_tokens=100)
        assert chunks[-1].split()[-1] == "w1299"
        # Tail chunk must appear exactly once
        assert chunks.count(chunks[-1]) == 1

    def test_overlap_greater_than_chunk_size_still_terminates(self):
        chunks = ChunkingService.chunk_text(_words(50), chunk_size_tokens=10, overlap_tokens=20)
        assert len(chunks) > 0
        assert chunks[-1].split()[-1] == "w49"


class TestChunkTextStructuredSectionBoundary:
    """Regression tests for the 2026-07-25 fix: the greedy merge in chunk_text_structured
    used to only stop on token budget, silently folding multiple unrelated lettered sections
    into one chunk when each was individually small (found via gold-QA evaluation, Q002
    "biaya pendaftaran" retrieval -- a chunk covering 5 unrelated sections at once loses the
    rerank to a topically-focused chunk for any single specific query)."""

    def test_different_small_sections_are_not_merged(self):
        # chunk_size_tokens deliberately small so _recursive_split's paragraph-level split
        # engages (it only descends past the whole-text budget check when the combined text
        # exceeds it; real documents are long enough that this always happens) while each
        # individual heading+body pair stays comfortably under budget on its own -- isolating
        # section-crossing (not token budget) as the only reason two sections would split.
        text = (
            "B. Persyaratan Kelas Internasional\n\n"
            "Peserta wajib WNI atau WNA.\n\n"
            "C. Mekanisme Pendaftaran\n\n"
            "Pendaftar memilih 1 program studi.\n\n"
            "F. Biaya\n\n"
            "Biaya pendaftaran Rp 300000."
        )
        chunks = ChunkingService.chunk_text_structured(text, chunk_size_tokens=20, overlap_tokens=0)

        sections = [c["section"] for c in chunks]
        assert "B. Persyaratan Kelas Internasional" in sections
        assert "C. Mekanisme Pendaftaran" in sections
        assert "F. Biaya" in sections
        # Core invariant: no single chunk's text spans two different sections' body content --
        # whichever chunk holds the fee figure must not also hold the other sections' text.
        fee_chunks = [c for c in chunks if "Rp 300000" in c["text"]]
        assert fee_chunks, "expected the fee figure to survive in some chunk"
        for c in fee_chunks:
            assert "Mekanisme Pendaftaran" not in c["text"]
            assert "Persyaratan Kelas Internasional" not in c["text"]

    def test_single_section_repeated_pieces_still_merge_up_to_budget(self):
        """No section change -> existing token-budget-only merge behavior is unchanged."""
        text = "C. Mekanisme Pendaftaran\n\n" + "\n\n".join(
            f"Langkah {i}: lakukan sesuatu." for i in range(1, 6)
        )
        chunks = ChunkingService.chunk_text_structured(text, chunk_size_tokens=500, overlap_tokens=0)

        assert len(chunks) == 1
        assert chunks[0]["section"] == "C. Mekanisme Pendaftaran"

    def test_pieces_with_no_heading_do_not_force_a_split(self):
        text = "Paragraf pertama tanpa judul.\n\nParagraf kedua juga tanpa judul apa pun."
        chunks = ChunkingService.chunk_text_structured(text, chunk_size_tokens=500, overlap_tokens=0)

        assert len(chunks) == 1
        assert chunks[0]["section"] is None

    def test_section_still_forces_split_over_budget_as_before(self):
        """Token-budget boundary keeps working even when both pieces share the same section."""
        text = "C. Mekanisme Pendaftaran\n\n" + _words(600)
        chunks = ChunkingService.chunk_text_structured(text, chunk_size_tokens=500, overlap_tokens=0)

        assert len(chunks) >= 2


class TestGetChunkTokenCount:
    def test_counts_words(self):
        assert ChunkingService.get_chunk_token_count("satu dua tiga") == 3

    def test_empty_text_is_zero(self):
        assert ChunkingService.get_chunk_token_count("") == 0
