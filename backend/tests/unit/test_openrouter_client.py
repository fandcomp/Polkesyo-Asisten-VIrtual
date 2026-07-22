"""Unit tests for OpenRouterClient's concurrency cap.

Covers the 2026-07-22 fix: settings.llm_max_concurrency (CLAUDE.md §9.5/§25) was declared
but never enforced anywhere (the project's request_queue_service.py existed but was never
wired in). generate() now bounds concurrent in-flight calls via a module-level
asyncio.Semaphore — these tests verify that bound actually holds, not just that the code runs.
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import openrouter_client as orc_module
from app.services.openrouter_client import OpenRouterClient


def _make_response(delay: float, in_flight: list[int], max_in_flight: list[int]):
    """Build a fake httpx response whose retrieval tracks concurrent in-flight calls."""

    async def _post(*args, **kwargs):
        in_flight[0] += 1
        max_in_flight[0] = max(max_in_flight[0], in_flight[0])
        await asyncio.sleep(delay)
        in_flight[0] -= 1

        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {
            "choices": [{"message": {"content": "jawaban"}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_cost": 0.001},
        }
        return response

    return _post


@pytest.mark.asyncio
async def test_concurrent_calls_never_exceed_llm_max_concurrency(monkeypatch):
    monkeypatch.setattr(orc_module.settings, "openrouter_api_key", "test-key")
    # Cap at 2 for a fast, deterministic test regardless of the real configured value.
    monkeypatch.setattr(orc_module, "_llm_semaphore", asyncio.Semaphore(2))

    in_flight = [0]
    max_in_flight = [0]

    mock_client = AsyncMock()
    mock_client.post.side_effect = _make_response(0.05, in_flight, max_in_flight)
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None

    with patch("httpx.AsyncClient", return_value=mock_client):
        # 5 concurrent callers, but the semaphore is capped at 2.
        await asyncio.gather(*(OpenRouterClient.generate(f"prompt {i}") for i in range(5)))

    assert max_in_flight[0] <= 2


@pytest.mark.asyncio
async def test_generate_still_succeeds_under_the_cap(monkeypatch):
    monkeypatch.setattr(orc_module.settings, "openrouter_api_key", "test-key")
    monkeypatch.setattr(orc_module, "_llm_semaphore", asyncio.Semaphore(5))

    in_flight = [0]
    max_in_flight = [0]

    mock_client = AsyncMock()
    mock_client.post.side_effect = _make_response(0.0, in_flight, max_in_flight)
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await OpenRouterClient.generate("prompt")

    assert result.text == "jawaban"
    assert result.prompt_tokens == 10
    assert result.completion_tokens == 5
