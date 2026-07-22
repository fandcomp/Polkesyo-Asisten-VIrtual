"""Evaluation Layer Phase 1 — safe, best-effort logging for the /chat pipeline.

Populates chat_evaluation_logs, retrieval_evaluation_logs, citation_evaluation_logs,
acif_trace_logs, and graph_consistency_logs for a single chat trace (trace_id).

Non-negotiable: a logging failure here must never break the chat response. The single
public entrypoint (`log_chat_trace`) never raises — any error is caught, logged, and
swallowed. The caller (chat_core.py) still wraps the call in its own try/except as a second
layer of defense, since this is the one place where a bug here must not surface to the user.

ACIF logging rule (CLAUDE.md §11 / Evaluation Layer spec): only safe summaries are ever
accepted into `gate_rows` — no raw system prompt, no scoring formula weights, no raw matched
attack-phrase text, no chain-of-thought. Callers build those safe fields; this module doesn't
inspect gate internals, it only persists what it's given.
"""
import logging
from typing import Any, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import (
    AcifTraceLog,
    ChatEvaluationLog,
    CitationEvaluationLog,
    GraphConsistencyLog,
    RetrievalEvaluationLog,
)
from app.services.acif.text_normalizer import TextNormalizer

logger = logging.getLogger(__name__)

# Ceiling applied when EVALUATION_LOG_FULL_ANSWER/EVALUATION_LOG_FULL_CONTEXT are disabled —
# keeps a short excerpt for admin triage without persisting the full question/answer/context text.
_REDACTED_PREVIEW_CHARS = 200


class EvaluationLogger:
    """Best-effort, non-raising logger for one chat trace's technical/ACIF evaluation data."""

    @staticmethod
    async def log_chat_trace(
        db: AsyncSession,
        *,
        trace_id: str,
        session_id: Optional[UUID],
        user_question: str,
        final_answer: Optional[str],
        fallback_triggered: bool,
        answer_status: str,
        total_latency_ms: int,
        fallback_reason: Optional[str] = None,
        retrieval_latency_ms: Optional[int] = None,
        graph_latency_ms: Optional[int] = None,
        acif_latency_ms: Optional[int] = None,
        llm_latency_ms: Optional[int] = None,
        output_verification_latency_ms: Optional[int] = None,
        model_used: Optional[str] = None,
        input_tokens: Optional[int] = None,
        output_tokens: Optional[int] = None,
        estimated_cost: Optional[float] = None,
        error_message: Optional[str] = None,
        evaluation_mode: bool = False,
        participant_code: Optional[str] = None,
        scenario_code: Optional[str] = None,
        retrieval_rows: Optional[list[dict[str, Any]]] = None,
        citation_rows: Optional[list[dict[str, Any]]] = None,
        gate_rows: Optional[list[dict[str, Any]]] = None,
        graph_consistency_rows: Optional[list[dict[str, Any]]] = None,
        # Query Understanding Layer fields (all optional — omitting them behaves as before)
        normalized_question_override: Optional[str] = None,
        rewritten_queries: Optional[list[str]] = None,
        detected_terms: Optional[list[str]] = None,
        expanded_terms: Optional[list[str]] = None,
        intent: Optional[str] = None,
        intent_confidence: Optional[float] = None,
        clarification_used: bool = False,
    ) -> None:
        """Write one trace's full evaluation footprint. Never raises — logs and swallows."""
        if not settings.evaluation_logging_enabled:
            return

        try:
            if settings.evaluation_log_full_answer:
                stored_question = user_question
                stored_answer = final_answer
            else:
                stored_question = (user_question or "")[:_REDACTED_PREVIEW_CHARS]
                stored_answer = (
                    (final_answer or "")[:_REDACTED_PREVIEW_CHARS] if final_answer else None
                )

            db.add(
                ChatEvaluationLog(
                    trace_id=trace_id,
                    session_id=session_id,
                    participant_code=participant_code,
                    scenario_code=scenario_code,
                    evaluation_mode=evaluation_mode,
                    user_question=stored_question,
                    normalized_question=(
                        normalized_question_override[:2000]
                        if normalized_question_override
                        else TextNormalizer.normalize(user_question)[:2000]
                        if user_question
                        else None
                    ),
                    final_answer=stored_answer,
                    fallback_triggered=fallback_triggered,
                    fallback_reason=fallback_reason,
                    answer_status=answer_status,
                    rewritten_queries=rewritten_queries,
                    detected_terms=detected_terms,
                    expanded_terms=expanded_terms,
                    intent=intent,
                    intent_confidence=intent_confidence,
                    clarification_used=clarification_used,
                    total_latency_ms=total_latency_ms,
                    retrieval_latency_ms=retrieval_latency_ms,
                    graph_latency_ms=graph_latency_ms,
                    acif_latency_ms=acif_latency_ms,
                    llm_latency_ms=llm_latency_ms,
                    output_verification_latency_ms=output_verification_latency_ms,
                    model_used=model_used,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    estimated_cost=estimated_cost,
                    error_message=error_message,
                )
            )

            for row in retrieval_rows or []:
                db.add(
                    RetrievalEvaluationLog(
                        trace_id=trace_id,
                        chunk_id=row.get("chunk_id"),
                        document_id=row.get("document_id"),
                        document_version_id=row.get("document_version_id"),
                        document_title=row.get("document_title"),
                        page_number=row.get("page_number"),
                        chunk_type=row.get("chunk_type"),
                        retrieval_source=row.get("retrieval_source", "vector"),
                        retrieval_rank=row["retrieval_rank"],
                        retrieval_score=row.get("retrieval_score"),
                        selected_for_context=row.get("selected_for_context", False),
                        rejected_reason=row.get("rejected_reason"),
                        metadata_json=(
                            row.get("metadata") if settings.evaluation_log_full_context else None
                        ),
                    )
                )

            for row in citation_rows or []:
                db.add(
                    CitationEvaluationLog(
                        trace_id=trace_id,
                        document_id=row.get("document_id"),
                        chunk_id=row.get("chunk_id"),
                        document_title=row.get("document_title"),
                        page_number=row.get("page_number"),
                        citation_type=row.get("citation_type", "text"),
                        is_visual_source=row.get("is_visual_source", False),
                        is_valid=row.get("is_valid"),
                        validation_notes=row.get("validation_notes"),
                    )
                )

            if settings.acif_observability_enabled:
                for row in gate_rows or []:
                    db.add(
                        AcifTraceLog(
                            trace_id=trace_id,
                            gate_number=row["gate_number"],
                            gate_name=row["gate_name"],
                            gate_status=row["gate_status"],
                            risk_score=row.get("risk_score"),
                            risk_level=row.get("risk_level"),
                            action_taken=row.get("action_taken"),
                            risk_flags=row.get("risk_flags"),
                            public_summary=row.get("public_summary"),
                            admin_summary=row.get("admin_summary"),
                            latency_ms=row.get("latency_ms"),
                        )
                    )

            for row in graph_consistency_rows or []:
                db.add(
                    GraphConsistencyLog(
                        trace_id=trace_id,
                        graph_entity=row.get("graph_entity"),
                        graph_relation=row.get("graph_relation"),
                        supporting_document_id=row.get("supporting_document_id"),
                        supporting_chunk_id=row.get("supporting_chunk_id"),
                        consistency_status=row["consistency_status"],
                        notes=row.get("notes"),
                    )
                )

            await db.commit()

        except Exception as e:
            logger.error(f"EvaluationLogger failed for trace_id={trace_id}: {e}")
            try:
                await db.rollback()
            except Exception:
                pass
