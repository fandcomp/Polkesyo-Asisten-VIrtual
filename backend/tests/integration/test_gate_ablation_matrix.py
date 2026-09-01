"""Integration tests: N-gate ablation (2026-07-24) — per-gate and multi-gate `disabled_gates`
combinations through the real ChatCoreService.process_message pipeline.

Reuses PipelineHarness/SPMB_CHUNK/GROUNDED_ANSWER from test_flexible_questions_pipeline.py
(same I/O-boundary mocking, real ACIF gates in between) rather than building a fresh mock setup.
"""
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.services.acif.schemas import ACIFDecision, ACIFGate1Result
from app.services.chat_core import ChatCoreService
from tests.integration.test_flexible_questions_pipeline import (
    GROUNDED_ANSWER,
    SPMB_CHUNK,
    PipelineHarness,
)

SESSION_ID = uuid4()

# A bare AsyncMock() for InputIntegrityChecker.check would return a MagicMock whose
# `.domain_violation` is truthy by default, short-circuiting the pipeline at the out-of-domain
# check before it ever reaches gates 2-5 — every gate-1-enabled test that needs the pipeline to
# actually proceed past gate 1 must return this explicit ACCEPT result instead.
_GATE1_ACCEPT_RESULT = ACIFGate1Result(
    decision=ACIFDecision.ACCEPT, score=0.0, risk_signals=[], reasoning="accept", domain_violation=False
)


async def _process(harness: PipelineHarness, message: str, disabled_gates: frozenset[int] = frozenset()):
    return await ChatCoreService.process_message(
        db=harness.db,
        session_id=SESSION_ID,
        message=message,
        evaluation_mode=True,
        disabled_gates=disabled_gates,
    )


@pytest.mark.asyncio
async def test_gate1_disabled_skips_input_integrity_check():
    with PipelineHarness(retrieval_results=[SPMB_CHUNK]) as harness, patch(
        "app.services.chat_core.InputIntegrityChecker.check", AsyncMock()
    ) as gate1_mock:
        await _process(harness, "Apa itu SPMB?", disabled_gates=frozenset({1}))
        gate1_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_gate1_enabled_runs_input_integrity_check():
    with PipelineHarness(retrieval_results=[SPMB_CHUNK]) as harness, patch(
        "app.services.chat_core.InputIntegrityChecker.check",
        AsyncMock(return_value=_GATE1_ACCEPT_RESULT),
    ) as gate1_mock:
        await _process(harness, "Apa itu SPMB?", disabled_gates=frozenset())
        gate1_mock.assert_awaited()


@pytest.mark.asyncio
async def test_gate2_disabled_skips_context_integrity_scoring():
    with PipelineHarness(retrieval_results=[SPMB_CHUNK]) as harness, patch(
        "app.services.chat_core.ContextIntegrityScorer.score_context", AsyncMock()
    ) as gate2_mock:
        await _process(harness, "Apa itu SPMB?", disabled_gates=frozenset({2}))
        gate2_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_gate3_disabled_skips_graph_document_consistency():
    with PipelineHarness(retrieval_results=[SPMB_CHUNK]) as harness, patch(
        "app.services.chat_core.GraphDocumentConsistency.check_consistency", AsyncMock()
    ) as gate3_mock:
        await _process(harness, "Apa itu SPMB?", disabled_gates=frozenset({3}))
        gate3_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_gate3_enabled_runs_graph_document_consistency():
    with PipelineHarness(retrieval_results=[SPMB_CHUNK]) as harness, patch(
        "app.services.chat_core.GraphDocumentConsistency.check_consistency",
        AsyncMock(return_value={"decision": "consistent"}),
    ) as gate3_mock:
        await _process(harness, "Apa itu SPMB?", disabled_gates=frozenset())
        gate3_mock.assert_awaited()


@pytest.mark.asyncio
async def test_gate4_disabled_uses_naive_prompt_builder():
    with PipelineHarness(retrieval_results=[SPMB_CHUNK], llm_answer=GROUNDED_ANSWER) as harness:
        await _process(harness, "Apa itu SPMB?", disabled_gates=frozenset({4}))
        prompt_used = harness.generate_with_fallback_mock.await_args.kwargs.get("prompt") or (
            harness.generate_with_fallback_mock.await_args.args[0]
            if harness.generate_with_fallback_mock.await_args.args
            else ""
        )
        # build_naive() never includes a graph-evidence section or the untrusted-input marker
        # (see prompt_boundary_builder.py's build() vs build_naive()) — real, verified marker.
        assert "STRUCTURED GRAPH EVIDENCE" not in prompt_used
        assert "USER QUESTION (untrusted input)" not in prompt_used


@pytest.mark.asyncio
async def test_gate4_enabled_uses_bounded_prompt_builder():
    with PipelineHarness(retrieval_results=[SPMB_CHUNK], llm_answer=GROUNDED_ANSWER) as harness:
        await _process(harness, "Apa itu SPMB?", disabled_gates=frozenset())
        prompt_used = harness.generate_with_fallback_mock.await_args.kwargs.get("prompt") or (
            harness.generate_with_fallback_mock.await_args.args[0]
            if harness.generate_with_fallback_mock.await_args.args
            else ""
        )
        assert "STRUCTURED GRAPH EVIDENCE" in prompt_used
        assert "USER QUESTION (untrusted input)" in prompt_used


@pytest.mark.asyncio
async def test_gate5_disabled_skips_output_claim_verification():
    with PipelineHarness(retrieval_results=[SPMB_CHUNK], llm_answer=GROUNDED_ANSWER) as harness, patch(
        "app.services.chat_core.OutputClaimVerifier.verify", AsyncMock()
    ) as gate5_mock:
        response = await _process(harness, "Apa itu SPMB?", disabled_gates=frozenset({5}))
        gate5_mock.assert_not_called()
        assert response.status == "answered"


@pytest.mark.asyncio
async def test_cumulative_gates_1_2_disables_only_first_two():
    """gates_1_2 config: gates 1 and 2 disabled, gates 3/4/5 still run."""
    with PipelineHarness(retrieval_results=[SPMB_CHUNK]) as harness, patch(
        "app.services.chat_core.InputIntegrityChecker.check", AsyncMock()
    ) as gate1_mock, patch(
        "app.services.chat_core.ContextIntegrityScorer.score_context", AsyncMock()
    ) as gate2_mock, patch(
        "app.services.chat_core.GraphDocumentConsistency.check_consistency",
        AsyncMock(return_value={"decision": "consistent"}),
    ) as gate3_mock:
        await _process(harness, "Apa itu SPMB?", disabled_gates=frozenset({1, 2}))
        gate1_mock.assert_not_awaited()
        gate2_mock.assert_not_awaited()
        gate3_mock.assert_awaited()


@pytest.mark.asyncio
async def test_leave_one_out_gates_all_minus_3_disables_only_gate3():
    """gates_all_minus_3 config: only gate 3 disabled, gates 1/2/4/5 still run."""
    with PipelineHarness(retrieval_results=[SPMB_CHUNK]) as harness, patch(
        "app.services.chat_core.InputIntegrityChecker.check",
        AsyncMock(return_value=_GATE1_ACCEPT_RESULT),
    ) as gate1_mock, patch(
        "app.services.chat_core.GraphDocumentConsistency.check_consistency", AsyncMock()
    ) as gate3_mock:
        await _process(harness, "Apa itu SPMB?", disabled_gates=frozenset({3}))
        gate1_mock.assert_awaited()
        gate3_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_disabled_gates_requires_evaluation_mode():
    with PipelineHarness(retrieval_results=[SPMB_CHUNK]) as harness:
        with pytest.raises(AssertionError):
            await ChatCoreService.process_message(
                db=harness.db,
                session_id=SESSION_ID,
                message="Apa itu SPMB?",
                evaluation_mode=False,
                disabled_gates=frozenset({1}),
            )


@pytest.mark.asyncio
async def test_disabled_gates_out_of_range_raises_value_error():
    with PipelineHarness(retrieval_results=[SPMB_CHUNK]) as harness:
        with pytest.raises(ValueError):
            await ChatCoreService.process_message(
                db=harness.db,
                session_id=SESSION_ID,
                message="Apa itu SPMB?",
                evaluation_mode=True,
                disabled_gates=frozenset({6}),
            )
