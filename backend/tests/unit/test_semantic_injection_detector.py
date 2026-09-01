"""Unit tests for the ACIF Gate 1 semantic injection layer."""
from unittest.mock import patch

import pytest

from app.core.config import settings
from app.services.acif import semantic_injection_detector as sid_module
from app.services.acif.semantic_injection_detector import SemanticInjectionDetector


@pytest.fixture(autouse=True)
def _reset_bank_cache():
    """The bank embedding cache is process-global (same pattern as VectorIndexService's
    embedding function / RerankerService's cross-encoder) — reset it around every test so
    one test's mocked embedding function doesn't leak into another."""
    sid_module._bank_vectors = None
    sid_module._bank_loaded = False
    yield
    sid_module._bank_vectors = None
    sid_module._bank_loaded = False


def _fake_embedding_function(texts):
    """Deterministic fake: embeds each text as a one-hot-ish vector keyed by a fixed
    vocabulary, so cosine similarity is fully predictable without a real model."""
    vocab = ["ignore", "instructions", "syarat", "pendaftaran", "spmb"]

    def embed(text: str) -> list[float]:
        tokens = text.lower().split()
        return [float(tokens.count(word)) for word in vocab]

    return [embed(t) for t in texts]


@pytest.mark.asyncio
class TestSemanticInjectionDetector:
    async def test_disabled_returns_none(self, monkeypatch):
        monkeypatch.setattr(settings, "acif_gate1_semantic_enabled", False)
        result = await SemanticInjectionDetector.max_similarity_to_known_attacks("ignore instructions")
        assert result is None

    async def test_embedding_function_unavailable_returns_none(self, monkeypatch):
        monkeypatch.setattr(settings, "acif_gate1_semantic_enabled", True)
        with patch(
            "app.services.vector_index_service.VectorIndexService.get_embedding_function",
            return_value=None,
        ):
            result = await SemanticInjectionDetector.max_similarity_to_known_attacks("ignore instructions")
        assert result is None

    async def test_similar_text_scores_high_similarity(self, monkeypatch):
        monkeypatch.setattr(settings, "acif_gate1_semantic_enabled", True)
        monkeypatch.setattr(sid_module, "KNOWN_ATTACK_EXAMPLES", ["ignore instructions"])
        with patch(
            "app.services.vector_index_service.VectorIndexService.get_embedding_function",
            return_value=_fake_embedding_function,
        ):
            result = await SemanticInjectionDetector.max_similarity_to_known_attacks(
                "ignore instructions"
            )
        assert result == pytest.approx(1.0)

    async def test_dissimilar_text_scores_low_similarity(self, monkeypatch):
        monkeypatch.setattr(settings, "acif_gate1_semantic_enabled", True)
        monkeypatch.setattr(sid_module, "KNOWN_ATTACK_EXAMPLES", ["ignore instructions"])
        with patch(
            "app.services.vector_index_service.VectorIndexService.get_embedding_function",
            return_value=_fake_embedding_function,
        ):
            result = await SemanticInjectionDetector.max_similarity_to_known_attacks(
                "syarat pendaftaran spmb"
            )
        assert result == pytest.approx(0.0)

    async def test_embedding_failure_fails_safe_to_none(self, monkeypatch):
        monkeypatch.setattr(settings, "acif_gate1_semantic_enabled", True)

        def _boom():
            raise RuntimeError("model load failed")

        with patch(
            "app.services.vector_index_service.VectorIndexService.get_embedding_function",
            side_effect=_boom,
        ):
            result = await SemanticInjectionDetector.max_similarity_to_known_attacks("apapun")
        assert result is None

    async def test_blank_text_returns_none_without_calling_embedder(self, monkeypatch):
        monkeypatch.setattr(settings, "acif_gate1_semantic_enabled", True)
        with patch(
            "app.services.vector_index_service.VectorIndexService.get_embedding_function"
        ) as mock_get:
            result = await SemanticInjectionDetector.max_similarity_to_known_attacks("   ")
        assert result is None
        mock_get.assert_not_called()


class TestScoreBump:
    def test_none_similarity_has_no_bump(self):
        assert SemanticInjectionDetector.score_bump(None) == 0.0

    def test_below_caution_similarity_has_no_bump(self, monkeypatch):
        monkeypatch.setattr(settings, "acif_gate1_semantic_caution_similarity", 0.50)
        monkeypatch.setattr(settings, "acif_gate1_semantic_reject_similarity", 0.72)
        assert SemanticInjectionDetector.score_bump(0.40) == 0.0

    def test_caution_band_bumps_by_point_one(self, monkeypatch):
        monkeypatch.setattr(settings, "acif_gate1_semantic_caution_similarity", 0.50)
        monkeypatch.setattr(settings, "acif_gate1_semantic_reject_similarity", 0.72)
        assert SemanticInjectionDetector.score_bump(0.60) == pytest.approx(0.10)

    def test_reject_band_bumps_by_point_two_five(self, monkeypatch):
        monkeypatch.setattr(settings, "acif_gate1_semantic_caution_similarity", 0.50)
        monkeypatch.setattr(settings, "acif_gate1_semantic_reject_similarity", 0.72)
        assert SemanticInjectionDetector.score_bump(0.80) == pytest.approx(0.25)
