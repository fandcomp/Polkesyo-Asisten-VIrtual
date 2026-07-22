"""Unit tests for app/evaluation/llm_judge.py — RAGAS-style faithfulness/relevance/
hallucination scoring used by the gold-QA runner (Evaluation Layer Phase 5)."""
from unittest.mock import AsyncMock, patch

import pytest

from app.core.config import settings
from app.evaluation import llm_judge
from app.services.openrouter_client import GenerationResult, OpenRouterError


def _generation(text: str) -> GenerationResult:
    return GenerationResult(text=text, model="test-model", prompt_tokens=1, completion_tokens=1, cost_usd=0.0)


@pytest.mark.asyncio
class TestJudgeAnswer:
    async def test_disabled_returns_none_without_calling_llm(self, monkeypatch):
        monkeypatch.setattr(settings, "evaluation_llm_judge_enabled", False)
        with patch(
            "app.evaluation.llm_judge.OpenRouterClient.generate", AsyncMock()
        ) as mock_generate:
            result = await llm_judge.judge_answer("Q?", "some context", "some answer")

        assert result is None
        mock_generate.assert_not_awaited()

    async def test_empty_context_returns_none(self, monkeypatch):
        monkeypatch.setattr(settings, "evaluation_llm_judge_enabled", True)
        result = await llm_judge.judge_answer("Q?", "", "some answer")
        assert result is None

    async def test_empty_answer_returns_none(self, monkeypatch):
        monkeypatch.setattr(settings, "evaluation_llm_judge_enabled", True)
        result = await llm_judge.judge_answer("Q?", "some context", "")
        assert result is None

    async def test_valid_json_response_is_parsed(self, monkeypatch):
        monkeypatch.setattr(settings, "evaluation_llm_judge_enabled", True)
        raw = '{"faithfulness_score": 0.9, "answer_relevance_score": 0.8, "hallucination_detected": false}'
        with patch(
            "app.evaluation.llm_judge.OpenRouterClient.generate",
            AsyncMock(return_value=_generation(raw)),
        ) as mock_generate:
            result = await llm_judge.judge_answer(
                "Berapa biaya pendaftaran?", "Biaya pendaftaran Rp 300.000.", "Biaya pendaftaran adalah Rp 300.000."
            )

        mock_generate.assert_awaited_once()
        assert result.faithfulness_score == pytest.approx(0.9)
        assert result.answer_relevance_score == pytest.approx(0.8)
        assert result.hallucination_detected is False

    async def test_markdown_fenced_json_is_parsed(self, monkeypatch):
        monkeypatch.setattr(settings, "evaluation_llm_judge_enabled", True)
        raw = '```json\n{"faithfulness_score": 0.5, "answer_relevance_score": 0.6, "hallucination_detected": true}\n```'
        with patch(
            "app.evaluation.llm_judge.OpenRouterClient.generate",
            AsyncMock(return_value=_generation(raw)),
        ):
            result = await llm_judge.judge_answer("Q?", "context", "answer")

        assert result.faithfulness_score == pytest.approx(0.5)
        assert result.hallucination_detected is True

    async def test_malformed_json_returns_none(self, monkeypatch):
        monkeypatch.setattr(settings, "evaluation_llm_judge_enabled", True)
        with patch(
            "app.evaluation.llm_judge.OpenRouterClient.generate",
            AsyncMock(return_value=_generation("not json at all")),
        ):
            result = await llm_judge.judge_answer("Q?", "context", "answer")

        assert result is None

    async def test_non_object_json_returns_none(self, monkeypatch):
        monkeypatch.setattr(settings, "evaluation_llm_judge_enabled", True)
        with patch(
            "app.evaluation.llm_judge.OpenRouterClient.generate",
            AsyncMock(return_value=_generation("[1, 2, 3]")),
        ):
            result = await llm_judge.judge_answer("Q?", "context", "answer")

        assert result is None

    async def test_llm_call_failure_returns_none(self, monkeypatch):
        monkeypatch.setattr(settings, "evaluation_llm_judge_enabled", True)
        with patch(
            "app.evaluation.llm_judge.OpenRouterClient.generate",
            AsyncMock(side_effect=OpenRouterError("timeout")),
        ):
            result = await llm_judge.judge_answer("Q?", "context", "answer")

        assert result is None
