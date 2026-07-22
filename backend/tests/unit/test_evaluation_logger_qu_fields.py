"""Tests for Query Understanding fields in the Evaluation Layer logging path."""
import pytest
from unittest.mock import AsyncMock, MagicMock

from app.api.routes_evaluation_admin import _serialize_chat_log
from app.db.models import ChatEvaluationLog
from app.services.evaluation_logger import EvaluationLogger


def _mock_db() -> MagicMock:
    db = MagicMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    return db


@pytest.mark.asyncio
async def test_logger_persists_qu_fields():
    db = _mock_db()
    await EvaluationLogger.log_chat_trace(
        db,
        trace_id="t-qu-1",
        session_id=None,
        user_question="apa itu spmb?",
        final_answer="jawaban",
        fallback_triggered=False,
        answer_status="verified",
        total_latency_ms=100,
        normalized_question_override="apa itu spmb",
        rewritten_queries=["apa itu spmb", "apa itu spmb seleksi penerimaan mahasiswa baru"],
        detected_terms=["spmb"],
        expanded_terms=["seleksi penerimaan mahasiswa baru"],
        intent="definition",
        intent_confidence=0.9,
        clarification_used=False,
    )

    chat_rows = [a.args[0] for a in db.add.call_args_list if isinstance(a.args[0], ChatEvaluationLog)]
    assert len(chat_rows) == 1
    row = chat_rows[0]
    assert row.normalized_question == "apa itu spmb"
    assert row.rewritten_queries == [
        "apa itu spmb", "apa itu spmb seleksi penerimaan mahasiswa baru"
    ]
    assert row.detected_terms == ["spmb"]
    assert row.intent == "definition"
    assert row.intent_confidence == 0.9
    assert row.clarification_used is False
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_logger_back_compat_without_qu_kwargs():
    """Existing call sites that don't pass the new kwargs must keep working unchanged."""
    db = _mock_db()
    await EvaluationLogger.log_chat_trace(
        db,
        trace_id="t-qu-2",
        session_id=None,
        user_question="pertanyaan lama",
        final_answer=None,
        fallback_triggered=True,
        answer_status="insufficient_context",
        total_latency_ms=50,
    )

    chat_rows = [a.args[0] for a in db.add.call_args_list if isinstance(a.args[0], ChatEvaluationLog)]
    assert len(chat_rows) == 1
    row = chat_rows[0]
    assert row.rewritten_queries is None
    assert row.intent is None
    assert row.clarification_used is False
    # normalized_question falls back to the internal TextNormalizer path
    assert row.normalized_question == "pertanyaan lama"


def test_serializer_includes_qu_fields():
    row = ChatEvaluationLog(
        trace_id="t-qu-3",
        user_question="apa itu spmb?",
        normalized_question="apa itu spmb",
        answer_status="verified",
        fallback_triggered=False,
        rewritten_queries=["q1", "q2"],
        detected_terms=["spmb"],
        expanded_terms=["seleksi penerimaan mahasiswa baru"],
        intent="definition",
        intent_confidence=0.9,
        clarification_used=True,
    )
    serialized = _serialize_chat_log(row)
    assert serialized["normalized_question"] == "apa itu spmb"
    assert serialized["rewritten_queries"] == ["q1", "q2"]
    assert serialized["intent"] == "definition"
    assert serialized["intent_confidence"] == 0.9
    assert serialized["clarification_used"] is True
