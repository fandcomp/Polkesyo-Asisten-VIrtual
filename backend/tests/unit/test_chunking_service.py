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


class TestGetChunkTokenCount:
    def test_counts_words(self):
        assert ChunkingService.get_chunk_token_count("satu dua tiga") == 3

    def test_empty_text_is_zero(self):
        assert ChunkingService.get_chunk_token_count("") == 0
