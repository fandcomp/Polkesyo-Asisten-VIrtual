"""Admin-only Evaluation Layer observability endpoints (Phase 2).

Read-only over the Phase 1 logging tables (chat_evaluation_logs, retrieval_evaluation_logs,
citation_evaluation_logs, acif_trace_logs, graph_consistency_logs) plus CSV export. Base auth is
applied the same way as every other admin router: via main.py's
`dependencies=[Depends(require_admin_auth)]` on include_router. On top of that, this file (unlike
every other admin router) also tags each route with `Depends(require_evaluation_tab("..."))` —
the second, reviewer-role admin account (`security.py`) is restricted to a fixed subset of this
router's routes, grouped by which Evaluation sub-tab they back (2026-07-21).

CSV export streams rows via a generator (fastapi.responses.StreamingResponse) instead of
building the full response in memory, and every export query is capped by
EVALUATION_EXPORT_MAX_ROWS via SQL LIMIT — never "load everything then truncate."
"""
import csv
import dataclasses
import io
from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import require_evaluation_tab
from app.evaluation.statistical_comparison import compare_runs
from app.db.session import get_db
from app.db.models import (
    AcifTraceLog,
    AsqResponse,
    ChatEvaluationLog,
    CitationEvaluationLog,
    EvaluationResult,
    EvaluationRun,
    EvaluationScenario,
    GraphConsistencyLog,
    RetrievalEvaluationLog,
    SusResponse,
)

router = APIRouter(prefix="/api/admin/evaluation", tags=["admin-evaluation"])

MAX_LIST_LIMIT = 200


def _require_export_enabled() -> None:
    if not settings.evaluation_export_enabled:
        raise HTTPException(status_code=403, detail="Evaluation CSV export is disabled.")


def _serialize_chat_log(row: ChatEvaluationLog) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "trace_id": row.trace_id,
        "session_id": str(row.session_id) if row.session_id else None,
        "participant_code": row.participant_code,
        "scenario_code": row.scenario_code,
        "evaluation_mode": row.evaluation_mode,
        "user_question": row.user_question,
        "normalized_question": row.normalized_question,
        "final_answer": row.final_answer,
        "fallback_triggered": row.fallback_triggered,
        "fallback_reason": row.fallback_reason,
        "answer_status": row.answer_status,
        "rewritten_queries": row.rewritten_queries,
        "detected_terms": row.detected_terms,
        "expanded_terms": row.expanded_terms,
        "intent": row.intent,
        "intent_confidence": row.intent_confidence,
        "clarification_used": row.clarification_used,
        "total_latency_ms": row.total_latency_ms,
        "retrieval_latency_ms": row.retrieval_latency_ms,
        "graph_latency_ms": row.graph_latency_ms,
        "acif_latency_ms": row.acif_latency_ms,
        "llm_latency_ms": row.llm_latency_ms,
        "output_verification_latency_ms": row.output_verification_latency_ms,
        "model_used": row.model_used,
        "input_tokens": row.input_tokens,
        "output_tokens": row.output_tokens,
        "estimated_cost": row.estimated_cost,
        "error_message": row.error_message,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _serialize_retrieval(row: RetrievalEvaluationLog) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "trace_id": row.trace_id,
        "chunk_id": row.chunk_id,
        "document_id": row.document_id,
        "document_version_id": row.document_version_id,
        "document_title": row.document_title,
        "page_number": row.page_number,
        "chunk_type": row.chunk_type,
        "retrieval_source": row.retrieval_source,
        "retrieval_rank": row.retrieval_rank,
        "retrieval_score": row.retrieval_score,
        "selected_for_context": row.selected_for_context,
        "rejected_reason": row.rejected_reason,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _serialize_citation(row: CitationEvaluationLog) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "trace_id": row.trace_id,
        "document_id": row.document_id,
        "chunk_id": row.chunk_id,
        "document_title": row.document_title,
        "page_number": row.page_number,
        "citation_type": row.citation_type,
        "is_visual_source": row.is_visual_source,
        "is_valid": row.is_valid,
        "validation_notes": row.validation_notes,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _serialize_gate(row: AcifTraceLog) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "trace_id": row.trace_id,
        "gate_number": row.gate_number,
        "gate_name": row.gate_name,
        "gate_status": row.gate_status,
        "risk_score": row.risk_score,
        "risk_level": row.risk_level,
        "action_taken": row.action_taken,
        "risk_flags": row.risk_flags,
        "public_summary": row.public_summary,
        "admin_summary": row.admin_summary,
        "latency_ms": row.latency_ms,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _serialize_graph_consistency(row: GraphConsistencyLog) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "trace_id": row.trace_id,
        "graph_entity": row.graph_entity,
        "graph_relation": row.graph_relation,
        "supporting_document_id": row.supporting_document_id,
        "supporting_chunk_id": row.supporting_chunk_id,
        "consistency_status": row.consistency_status,
        "notes": row.notes,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _chat_log_conditions(
    date_from: Optional[datetime],
    date_to: Optional[datetime],
    session_id: Optional[str],
    participant_code: Optional[str],
    scenario_code: Optional[str],
    fallback_triggered: Optional[bool],
    model_used: Optional[str],
    latency_min_ms: Optional[int],
    latency_max_ms: Optional[int],
) -> list:
    conditions = []
    if date_from:
        conditions.append(ChatEvaluationLog.created_at >= date_from)
    if date_to:
        conditions.append(ChatEvaluationLog.created_at <= date_to)
    if session_id:
        try:
            conditions.append(ChatEvaluationLog.session_id == UUID(session_id))
        except ValueError:
            raise HTTPException(status_code=400, detail="session_id must be a valid UUID")
    if participant_code:
        conditions.append(ChatEvaluationLog.participant_code == participant_code)
    if scenario_code:
        conditions.append(ChatEvaluationLog.scenario_code == scenario_code)
    if fallback_triggered is not None:
        conditions.append(ChatEvaluationLog.fallback_triggered == fallback_triggered)
    if model_used:
        conditions.append(ChatEvaluationLog.model_used == model_used)
    if latency_min_ms is not None:
        conditions.append(ChatEvaluationLog.total_latency_ms >= latency_min_ms)
    if latency_max_ms is not None:
        conditions.append(ChatEvaluationLog.total_latency_ms <= latency_max_ms)
    return conditions


@router.get("/chat-logs", dependencies=[Depends(require_evaluation_tab("technical_logs"))])
async def list_chat_logs(
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    session_id: Optional[str] = None,
    participant_code: Optional[str] = None,
    scenario_code: Optional[str] = None,
    fallback_triggered: Optional[bool] = None,
    model_used: Optional[str] = None,
    latency_min_ms: Optional[int] = None,
    latency_max_ms: Optional[int] = None,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    """Paginated, filterable chat_evaluation_logs list for the admin Technical Logs page."""
    limit = min(limit, MAX_LIST_LIMIT)
    conditions = _chat_log_conditions(
        date_from, date_to, session_id, participant_code, scenario_code,
        fallback_triggered, model_used, latency_min_ms, latency_max_ms,
    )

    stmt = select(ChatEvaluationLog).order_by(ChatEvaluationLog.created_at.desc())
    count_stmt = select(func.count()).select_from(ChatEvaluationLog)
    if conditions:
        stmt = stmt.where(and_(*conditions))
        count_stmt = count_stmt.where(and_(*conditions))

    total = (await db.execute(count_stmt)).scalar() or 0
    rows = (await db.execute(stmt.limit(limit).offset(offset))).scalars().all()

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": [_serialize_chat_log(r) for r in rows],
    }


@router.get("/chat-logs/{trace_id}", dependencies=[Depends(require_evaluation_tab("technical_logs"))])
async def get_chat_log_detail(trace_id: str, db: AsyncSession = Depends(get_db)):
    """Full trace detail — chat log plus every related retrieval/citation/ACIF-gate/graph row.

    Backs the admin trace detail drawer (technical logs page) and doubles as the data source
    for the ACIF gate timeline view for this one trace.
    """
    chat_log = (
        await db.execute(select(ChatEvaluationLog).where(ChatEvaluationLog.trace_id == trace_id))
    ).scalar_one_or_none()
    if not chat_log:
        raise HTTPException(status_code=404, detail="Trace not found")

    retrieval_rows = (
        await db.execute(
            select(RetrievalEvaluationLog)
            .where(RetrievalEvaluationLog.trace_id == trace_id)
            .order_by(RetrievalEvaluationLog.retrieval_rank)
        )
    ).scalars().all()

    citation_rows = (
        await db.execute(select(CitationEvaluationLog).where(CitationEvaluationLog.trace_id == trace_id))
    ).scalars().all()

    gate_rows = (
        await db.execute(
            select(AcifTraceLog)
            .where(AcifTraceLog.trace_id == trace_id)
            .order_by(AcifTraceLog.gate_number)
        )
    ).scalars().all()

    graph_rows = (
        await db.execute(select(GraphConsistencyLog).where(GraphConsistencyLog.trace_id == trace_id))
    ).scalars().all()

    return {
        "chat_log": _serialize_chat_log(chat_log),
        "retrieval": [_serialize_retrieval(r) for r in retrieval_rows],
        "citations": [_serialize_citation(r) for r in citation_rows],
        "acif_gates": [_serialize_gate(r) for r in gate_rows],
        "graph_consistency": [_serialize_graph_consistency(r) for r in graph_rows],
    }


@router.get("/retrieval-logs", dependencies=[Depends(require_evaluation_tab("retrieval"))])
async def list_retrieval_logs(
    trace_id: Optional[str] = None,
    document_id: Optional[str] = None,
    selected_for_context: Optional[bool] = None,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    """Paginated retrieval_evaluation_logs for the admin Retrieval page."""
    limit = min(limit, MAX_LIST_LIMIT)
    conditions = []
    if trace_id:
        conditions.append(RetrievalEvaluationLog.trace_id == trace_id)
    if document_id:
        conditions.append(RetrievalEvaluationLog.document_id == document_id)
    if selected_for_context is not None:
        conditions.append(RetrievalEvaluationLog.selected_for_context == selected_for_context)

    stmt = select(RetrievalEvaluationLog).order_by(RetrievalEvaluationLog.created_at.desc())
    count_stmt = select(func.count()).select_from(RetrievalEvaluationLog)
    if conditions:
        stmt = stmt.where(and_(*conditions))
        count_stmt = count_stmt.where(and_(*conditions))

    total = (await db.execute(count_stmt)).scalar() or 0
    rows = (await db.execute(stmt.limit(limit).offset(offset))).scalars().all()

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": [_serialize_retrieval(r) for r in rows],
    }


@router.get("/citation-logs", dependencies=[Depends(require_evaluation_tab("citations"))])
async def list_citation_logs(
    trace_id: Optional[str] = None,
    document_id: Optional[str] = None,
    is_valid: Optional[bool] = None,
    citation_type: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    """Paginated citation_evaluation_logs for the admin Citations page."""
    limit = min(limit, MAX_LIST_LIMIT)
    conditions = []
    if trace_id:
        conditions.append(CitationEvaluationLog.trace_id == trace_id)
    if document_id:
        conditions.append(CitationEvaluationLog.document_id == document_id)
    if is_valid is not None:
        conditions.append(CitationEvaluationLog.is_valid == is_valid)
    if citation_type:
        conditions.append(CitationEvaluationLog.citation_type == citation_type)

    stmt = select(CitationEvaluationLog).order_by(CitationEvaluationLog.created_at.desc())
    count_stmt = select(func.count()).select_from(CitationEvaluationLog)
    if conditions:
        stmt = stmt.where(and_(*conditions))
        count_stmt = count_stmt.where(and_(*conditions))

    total = (await db.execute(count_stmt)).scalar() or 0
    rows = (await db.execute(stmt.limit(limit).offset(offset))).scalars().all()

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": [_serialize_citation(r) for r in rows],
    }


@router.get("/acif-traces", dependencies=[Depends(require_evaluation_tab("acif_traces"))])
async def list_acif_traces(
    gate_status: Optional[str] = None,
    gate_name: Optional[str] = None,
    risk_level: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    """Paginated acif_trace_logs for the admin ACIF Traces page — one row per gate per trace."""
    limit = min(limit, MAX_LIST_LIMIT)
    conditions = []
    if gate_status:
        conditions.append(AcifTraceLog.gate_status == gate_status)
    if gate_name:
        conditions.append(AcifTraceLog.gate_name == gate_name)
    if risk_level:
        conditions.append(AcifTraceLog.risk_level == risk_level)

    stmt = select(AcifTraceLog).order_by(AcifTraceLog.created_at.desc())
    count_stmt = select(func.count()).select_from(AcifTraceLog)
    if conditions:
        stmt = stmt.where(and_(*conditions))
        count_stmt = count_stmt.where(and_(*conditions))

    total = (await db.execute(count_stmt)).scalar() or 0
    rows = (await db.execute(stmt.limit(limit).offset(offset))).scalars().all()

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": [_serialize_gate(r) for r in rows],
    }


@router.get("/acif-traces/{trace_id}", dependencies=[Depends(require_evaluation_tab("acif_traces"))])
async def get_acif_trace_detail(trace_id: str, db: AsyncSession = Depends(get_db)):
    """Gate-by-gate (1-5) timeline for one trace — the ACIF gate timeline view's data source."""
    rows = (
        await db.execute(
            select(AcifTraceLog)
            .where(AcifTraceLog.trace_id == trace_id)
            .order_by(AcifTraceLog.gate_number)
        )
    ).scalars().all()
    if not rows:
        raise HTTPException(status_code=404, detail="No ACIF trace found for this trace_id")

    return {"trace_id": trace_id, "gates": [_serialize_gate(r) for r in rows]}


@router.get("/graph-consistency", dependencies=[Depends(require_evaluation_tab("overview"))])
async def list_graph_consistency(
    trace_id: Optional[str] = None,
    consistency_status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    """Paginated graph_consistency_logs."""
    limit = min(limit, MAX_LIST_LIMIT)
    conditions = []
    if trace_id:
        conditions.append(GraphConsistencyLog.trace_id == trace_id)
    if consistency_status:
        conditions.append(GraphConsistencyLog.consistency_status == consistency_status)

    stmt = select(GraphConsistencyLog).order_by(GraphConsistencyLog.created_at.desc())
    count_stmt = select(func.count()).select_from(GraphConsistencyLog)
    if conditions:
        stmt = stmt.where(and_(*conditions))
        count_stmt = count_stmt.where(and_(*conditions))

    total = (await db.execute(count_stmt)).scalar() or 0
    rows = (await db.execute(stmt.limit(limit).offset(offset))).scalars().all()

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": [_serialize_graph_consistency(r) for r in rows],
    }


def _clean_csv_cell(value: Any) -> Any:
    """Normalize one cell's value before it hits csv.DictWriter.

    Without this, list-typed fields (rewritten_queries, detected_terms, expanded_terms,
    risk_flags) render as Python's repr — e.g. "['a', 'b']" with single quotes — since
    csv.writer just calls str() on non-string values. That's not valid JSON and reads badly
    in Excel/Sheets; a "; "-joined plain string is what a human reviewer actually wants in a
    spreadsheet cell. None becomes an empty cell instead of the literal text "None".
    """
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return "; ".join(str(v) for v in value)
    return value


def _csv_stream(fieldnames: list[str], rows: list[dict[str, Any]]):
    """Yield a CSV file body in chunks — buffer stays small regardless of row count since
    rows are already capped by EVALUATION_EXPORT_MAX_ROWS before this is called.

    Leads with a UTF-8 BOM: Excel (the default open-with-CSV tool on Windows, the primary
    platform this export is consumed on) does not reliably detect plain UTF-8 without one and
    will otherwise silently misrender any non-ASCII character — Indonesian question/answer
    text, curly quotes from PDF-extracted source documents, etc. — as mojibake. The BOM is
    invisible in every other CSV consumer (Python's own csv module, pandas, Google Sheets all
    handle it transparently).
    """
    yield "﻿"
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    yield buffer.getvalue()
    buffer.seek(0)
    buffer.truncate(0)

    for row in rows:
        writer.writerow({k: _clean_csv_cell(v) for k, v in row.items()})
        yield buffer.getvalue()
        buffer.seek(0)
        buffer.truncate(0)


@router.get("/export/chat-logs.csv", dependencies=[Depends(require_evaluation_tab("technical_logs"))])
async def export_chat_logs_csv(
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    participant_code: Optional[str] = None,
    scenario_code: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """Stream chat_evaluation_logs as CSV — no secrets, no raw prompts (this table never
    stores them in the first place, see EvaluationLogger/AcifTraceLog docstrings)."""
    _require_export_enabled()
    conditions = _chat_log_conditions(
        date_from, date_to, None, participant_code, scenario_code, None, None, None, None
    )
    stmt = select(ChatEvaluationLog).order_by(ChatEvaluationLog.created_at.desc())
    if conditions:
        stmt = stmt.where(and_(*conditions))
    stmt = stmt.limit(settings.evaluation_export_max_rows)

    rows = [_serialize_chat_log(r) for r in (await db.execute(stmt)).scalars().all()]
    fieldnames = list(rows[0].keys()) if rows else [
        "id", "trace_id", "session_id", "participant_code", "scenario_code", "evaluation_mode",
        "user_question", "normalized_question", "final_answer", "fallback_triggered",
        "fallback_reason", "answer_status", "rewritten_queries", "detected_terms",
        "expanded_terms", "intent", "intent_confidence", "clarification_used",
        "total_latency_ms", "retrieval_latency_ms", "graph_latency_ms", "acif_latency_ms",
        "llm_latency_ms", "output_verification_latency_ms", "model_used", "input_tokens",
        "output_tokens", "estimated_cost", "error_message", "created_at",
    ]
    return StreamingResponse(
        _csv_stream(fieldnames, rows),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=chat_evaluation_logs.csv"},
    )


@router.get("/export/retrieval.csv", dependencies=[Depends(require_evaluation_tab("retrieval"))])
async def export_retrieval_csv(
    trace_id: Optional[str] = None,
    document_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """Stream retrieval_evaluation_logs as CSV."""
    _require_export_enabled()
    conditions = []
    if trace_id:
        conditions.append(RetrievalEvaluationLog.trace_id == trace_id)
    if document_id:
        conditions.append(RetrievalEvaluationLog.document_id == document_id)

    stmt = select(RetrievalEvaluationLog).order_by(RetrievalEvaluationLog.created_at.desc())
    if conditions:
        stmt = stmt.where(and_(*conditions))
    stmt = stmt.limit(settings.evaluation_export_max_rows)

    rows = [_serialize_retrieval(r) for r in (await db.execute(stmt)).scalars().all()]
    fieldnames = list(rows[0].keys()) if rows else [
        "id", "trace_id", "chunk_id", "document_id", "document_version_id", "document_title",
        "page_number", "chunk_type", "retrieval_source", "retrieval_rank", "retrieval_score",
        "selected_for_context", "rejected_reason", "created_at",
    ]
    return StreamingResponse(
        _csv_stream(fieldnames, rows),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=retrieval_evaluation_logs.csv"},
    )


@router.get("/export/citations.csv", dependencies=[Depends(require_evaluation_tab("citations"))])
async def export_citations_csv(
    trace_id: Optional[str] = None,
    document_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """Stream citation_evaluation_logs as CSV."""
    _require_export_enabled()
    conditions = []
    if trace_id:
        conditions.append(CitationEvaluationLog.trace_id == trace_id)
    if document_id:
        conditions.append(CitationEvaluationLog.document_id == document_id)

    stmt = select(CitationEvaluationLog).order_by(CitationEvaluationLog.created_at.desc())
    if conditions:
        stmt = stmt.where(and_(*conditions))
    stmt = stmt.limit(settings.evaluation_export_max_rows)

    rows = [_serialize_citation(r) for r in (await db.execute(stmt)).scalars().all()]
    fieldnames = list(rows[0].keys()) if rows else [
        "id", "trace_id", "document_id", "chunk_id", "document_title", "page_number",
        "citation_type", "is_visual_source", "is_valid", "validation_notes", "created_at",
    ]
    return StreamingResponse(
        _csv_stream(fieldnames, rows),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=citation_evaluation_logs.csv"},
    )


@router.get("/export/acif.csv", dependencies=[Depends(require_evaluation_tab("acif_traces"))])
async def export_acif_csv(
    gate_status: Optional[str] = None,
    gate_name: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """Stream acif_trace_logs as CSV — safe summaries only, matches what's stored (never a
    raw prompt, formula, or attack-phrase text — see AcifTraceLog's model docstring)."""
    _require_export_enabled()
    conditions = []
    if gate_status:
        conditions.append(AcifTraceLog.gate_status == gate_status)
    if gate_name:
        conditions.append(AcifTraceLog.gate_name == gate_name)

    stmt = select(AcifTraceLog).order_by(AcifTraceLog.created_at.desc())
    if conditions:
        stmt = stmt.where(and_(*conditions))
    stmt = stmt.limit(settings.evaluation_export_max_rows)

    rows = [_serialize_gate(r) for r in (await db.execute(stmt)).scalars().all()]
    fieldnames = list(rows[0].keys()) if rows else [
        "id", "trace_id", "gate_number", "gate_name", "gate_status", "risk_score", "risk_level",
        "action_taken", "risk_flags", "public_summary", "admin_summary", "latency_ms", "created_at",
    ]
    return StreamingResponse(
        _csv_stream(fieldnames, rows),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=acif_trace_logs.csv"},
    )


def _serialize_run(row: EvaluationRun) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "run_name": row.run_name,
        "config_name": row.config_name,
        "run_type": row.run_type,
        "total_questions": row.total_questions,
        "completed_questions": row.completed_questions,
        "status": row.status,
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "finished_at": row.finished_at.isoformat() if row.finished_at else None,
        "created_by": row.created_by,
        "notes": row.notes,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _serialize_result(row: EvaluationResult) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "evaluation_run_id": str(row.evaluation_run_id),
        "question_id": row.question_id,
        "trace_id": row.trace_id,
        "category": row.category,
        "expected_behavior": row.expected_behavior,
        "precision_at_3": row.precision_at_3,
        "recall_at_3": row.recall_at_3,
        "hit_rate_at_3": row.hit_rate_at_3,
        "citation_present": row.citation_present,
        "citation_correct": row.citation_correct,
        "fallback_correct": row.fallback_correct,
        "answer_relevance_score": row.answer_relevance_score,
        "faithfulness_score": row.faithfulness_score,
        "hallucination_detected": row.hallucination_detected,
        "attack_success": row.attack_success,
        "total_latency_ms": row.total_latency_ms,
        "retrieval_latency_ms": row.retrieval_latency_ms,
        "llm_latency_ms": row.llm_latency_ms,
        "notes": row.notes,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


@router.get("/runs", dependencies=[Depends(require_evaluation_tab("runs"))])
async def list_evaluation_runs(limit: int = 50, offset: int = 0, db: AsyncSession = Depends(get_db)):
    """List evaluation_runs for the admin Evaluation Runs page."""
    limit = min(limit, MAX_LIST_LIMIT)
    total = (await db.execute(select(func.count()).select_from(EvaluationRun))).scalar() or 0
    rows = (
        await db.execute(
            select(EvaluationRun).order_by(EvaluationRun.created_at.desc()).limit(limit).offset(offset)
        )
    ).scalars().all()
    return {"total": total, "limit": limit, "offset": offset, "items": [_serialize_run(r) for r in rows]}


class TriggerRunRequest(BaseModel):
    run_name: str = "gold_qa_run"
    # Thesis with/without-ACIF comparison (Evaluation Layer Phase 5): tag this run's
    # EvaluationRun.config_name and, when ablation_disable_acif=True, bypass all 5 ACIF gates
    # for every question (see chat_core.py's ablation_disable_acif docstring). Run once with
    # each combination against the same dataset to produce a paired comparison — see
    # GET /compare.
    config_name: str = "with_acif"
    ablation_disable_acif: bool = False


@router.post("/runs", dependencies=[Depends(require_evaluation_tab("runs"))])
async def trigger_evaluation_run(request: TriggerRunRequest, background_tasks: BackgroundTasks):
    """Kick off the gold-QA evaluation runner in the background.

    Not run automatically anywhere else (CLAUDE.md/spec principle 9 — "do not run evaluation
    runner automatically on server startup") — this admin-only, explicitly-triggered endpoint
    is the only way it starts besides the manual `python -m app.evaluation.run_evaluation` CLI.
    Returns immediately; poll GET /runs/{run_id} (once the run row exists) for progress.
    """
    if not settings.evaluation_runner_enabled:
        raise HTTPException(status_code=403, detail="Evaluation runner is disabled (EVALUATION_RUNNER_ENABLED=false).")

    from app.evaluation.run_evaluation import run_evaluation

    # Pass the async callable itself (Starlette awaits it on the SAME running loop after the
    # response is sent). The previous `add_task(asyncio.run, run_evaluation(...))` executed the
    # runner on a second event loop in a worker thread, where the shared Redis/cache/DB clients
    # (all bound to the main uvicorn loop) fail with "got Future attached to a different loop" —
    # found live on 2026-07-08, the first time this button was actually clicked in production.
    background_tasks.add_task(
        run_evaluation,
        request.run_name,
        config_name=request.config_name,
        ablation_disable_acif=request.ablation_disable_acif,
    )
    return {"status": "started", "run_name": request.run_name, "config_name": request.config_name}


@router.get("/runs/{run_id}", dependencies=[Depends(require_evaluation_tab("runs"))])
async def get_evaluation_run_detail(run_id: str, db: AsyncSession = Depends(get_db)):
    """Run detail: status/progress plus every per-question evaluation_results row."""
    run = (await db.execute(select(EvaluationRun).where(EvaluationRun.id == run_id))).scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=404, detail="Evaluation run not found")

    results = (
        await db.execute(
            select(EvaluationResult)
            .where(EvaluationResult.evaluation_run_id == run_id)
            .order_by(EvaluationResult.question_id)
        )
    ).scalars().all()

    return {"run": _serialize_run(run), "results": [_serialize_result(r) for r in results]}


async def _fetch_run_and_results(db: AsyncSession, run_id: str) -> tuple[EvaluationRun, list[EvaluationResult]]:
    run = (await db.execute(select(EvaluationRun).where(EvaluationRun.id == run_id))).scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=404, detail=f"Evaluation run not found: {run_id}")
    results = (
        await db.execute(select(EvaluationResult).where(EvaluationResult.evaluation_run_id == run_id))
    ).scalars().all()
    return run, results


@router.get("/compare", dependencies=[Depends(require_evaluation_tab("compare"))])
async def compare_evaluation_runs(
    run_id_a: str,
    run_id_b: str,
    db: AsyncSession = Depends(get_db),
):
    """Paired statistical comparison between two evaluation_runs — the thesis with/without-ACIF
    rumusan masalah endpoint (Evaluation Layer Phase 5). Both runs should have been produced
    from the same gold-QA dataset (e.g. config_name="with_acif" vs "without_acif", see
    run_evaluation.py) so questions pair up by question_id. See statistical_comparison.py for
    the Wilcoxon/McNemar test methodology.
    """
    run_a, results_a = await _fetch_run_and_results(db, run_id_a)
    run_b, results_b = await _fetch_run_and_results(db, run_id_b)

    report = compare_runs(
        results_a,
        results_b,
        run_id_a=str(run_a.id),
        run_id_b=str(run_b.id),
        config_name_a=run_a.config_name,
        config_name_b=run_b.config_name,
    )
    return dataclasses.asdict(report)


_COMPARE_CSV_FIELDS = [
    "metric", "n_pairs", "mean_a", "mean_b", "mean_delta", "median_delta",
    "percent_change", "test_name", "statistic", "p_value", "significant", "note",
]


@router.get("/export/compare.csv", dependencies=[Depends(require_evaluation_tab("compare"))])
async def export_compare_csv(
    run_id_a: str,
    run_id_b: str,
    db: AsyncSession = Depends(get_db),
):
    """Stream the with/without-ACIF comparison as CSV — one row per metric (plus the
    Security-only attack_success row), for direct inclusion in the thesis results chapter."""
    _require_export_enabled()
    run_a, results_a = await _fetch_run_and_results(db, run_id_a)
    run_b, results_b = await _fetch_run_and_results(db, run_id_b)

    report = compare_runs(
        results_a,
        results_b,
        run_id_a=str(run_a.id),
        run_id_b=str(run_b.id),
        config_name_a=run_a.config_name,
        config_name_b=run_b.config_name,
    )
    rows = [dataclasses.asdict(m) for m in report.metrics]
    if report.attack_success:
        rows.append(dataclasses.asdict(report.attack_success))

    return StreamingResponse(
        _csv_stream(_COMPARE_CSV_FIELDS, rows),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=acif_comparison.csv"},
    )


@router.get("/gold-qa-dataset", dependencies=[Depends(require_evaluation_tab("dataset"))])
async def get_gold_qa_dataset() -> dict[str, Any]:
    """The gold-QA question set (question text, category, expected_behavior, and pinned
    ground-truth chunk/document ids) keyed by question_id — read-only, for the admin Run
    Detail page to show retrieved-vs-expected side by side. Not stored in evaluation_results
    (that table only has the *computed* precision/recall outcome, not the raw ground truth
    used to compute it), so this reads the same JSONL file run_evaluation.py evaluates
    against, kept as the single source of truth for the dataset."""
    from app.evaluation.run_evaluation import load_gold_qa_dataset

    try:
        questions = load_gold_qa_dataset()
    except FileNotFoundError:
        return {"questions": {}}
    return {"questions": {q["id"]: q for q in questions}}


@router.get("/results", dependencies=[Depends(require_evaluation_tab("runs"))])
async def list_evaluation_results(
    evaluation_run_id: Optional[str] = None,
    category: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    """Flat, filterable evaluation_results list (across runs if evaluation_run_id is omitted)."""
    limit = min(limit, MAX_LIST_LIMIT)
    conditions = []
    if evaluation_run_id:
        conditions.append(EvaluationResult.evaluation_run_id == evaluation_run_id)
    if category:
        conditions.append(EvaluationResult.category == category)

    stmt = select(EvaluationResult).order_by(EvaluationResult.created_at.desc())
    count_stmt = select(func.count()).select_from(EvaluationResult)
    if conditions:
        stmt = stmt.where(and_(*conditions))
        count_stmt = count_stmt.where(and_(*conditions))

    total = (await db.execute(count_stmt)).scalar() or 0
    rows = (await db.execute(stmt.limit(limit).offset(offset))).scalars().all()
    return {"total": total, "limit": limit, "offset": offset, "items": [_serialize_result(r) for r in rows]}


def _serialize_asq(row: AsqResponse) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "participant_code": row.participant_code,
        "scenario_code": row.scenario_code,
        "session_id": row.session_id,
        "trace_id": row.trace_id,
        "asq_1": row.asq_1,
        "asq_2": row.asq_2,
        "asq_3": row.asq_3,
        "average_score": row.average_score,
        "notes": row.notes,
        "condition_code": row.condition_code,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _serialize_sus(row: SusResponse) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "participant_code": row.participant_code,
        "session_id": row.session_id,
        "sus_1": row.sus_1, "sus_2": row.sus_2, "sus_3": row.sus_3, "sus_4": row.sus_4, "sus_5": row.sus_5,
        "sus_6": row.sus_6, "sus_7": row.sus_7, "sus_8": row.sus_8, "sus_9": row.sus_9, "sus_10": row.sus_10,
        "sus_score": row.sus_score,
        "notes": row.notes,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


@router.get("/asq-summary", dependencies=[Depends(require_evaluation_tab("asq"))])
async def get_asq_summary(db: AsyncSession = Depends(get_db)):
    """Average ASQ per scenario/participant, item-level averages, for the admin ASQ Results page."""
    total = (await db.execute(select(func.count()).select_from(AsqResponse))).scalar() or 0
    if total == 0:
        return {
            "total_responses": 0,
            "overall_average": None,
            "by_scenario": [],
            "by_participant": [],
            "item_averages": {"asq_1": None, "asq_2": None, "asq_3": None},
        }

    overall_avg = (await db.execute(select(func.avg(AsqResponse.average_score)))).scalar()

    by_scenario = (
        await db.execute(
            select(AsqResponse.scenario_code, func.avg(AsqResponse.average_score), func.count())
            .group_by(AsqResponse.scenario_code)
        )
    ).all()
    by_participant = (
        await db.execute(
            select(AsqResponse.participant_code, func.avg(AsqResponse.average_score), func.count())
            .group_by(AsqResponse.participant_code)
        )
    ).all()
    item_avgs = (
        await db.execute(
            select(func.avg(AsqResponse.asq_1), func.avg(AsqResponse.asq_2), func.avg(AsqResponse.asq_3))
        )
    ).one()

    return {
        "total_responses": total,
        "overall_average": float(overall_avg) if overall_avg is not None else None,
        "by_scenario": [
            {"scenario_code": s, "average_score": float(a), "count": c} for s, a, c in by_scenario
        ],
        "by_participant": [
            {"participant_code": p, "average_score": float(a), "count": c} for p, a, c in by_participant
        ],
        "item_averages": {
            "asq_1": float(item_avgs[0]) if item_avgs[0] is not None else None,
            "asq_2": float(item_avgs[1]) if item_avgs[1] is not None else None,
            "asq_3": float(item_avgs[2]) if item_avgs[2] is not None else None,
        },
    }


@router.get("/asq-responses", dependencies=[Depends(require_evaluation_tab("asq"))])
async def list_asq_responses(
    participant_code: Optional[str] = None,
    scenario_code: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    """Paginated raw ASQ responses (notes table) for the admin ASQ Results page."""
    limit = min(limit, MAX_LIST_LIMIT)
    conditions = []
    if participant_code:
        conditions.append(AsqResponse.participant_code == participant_code)
    if scenario_code:
        conditions.append(AsqResponse.scenario_code == scenario_code)

    stmt = select(AsqResponse).order_by(AsqResponse.created_at.desc())
    count_stmt = select(func.count()).select_from(AsqResponse)
    if conditions:
        stmt = stmt.where(and_(*conditions))
        count_stmt = count_stmt.where(and_(*conditions))

    total = (await db.execute(count_stmt)).scalar() or 0
    rows = (await db.execute(stmt.limit(limit).offset(offset))).scalars().all()
    return {"total": total, "limit": limit, "offset": offset, "items": [_serialize_asq(r) for r in rows]}


@router.get("/sus-summary", dependencies=[Depends(require_evaluation_tab("sus"))])
async def get_sus_summary(db: AsyncSession = Depends(get_db)):
    """Average SUS score, item-level averages, for the admin SUS Results page."""
    total = (await db.execute(select(func.count()).select_from(SusResponse))).scalar() or 0
    if total == 0:
        return {
            "total_responses": 0,
            "overall_average": None,
            "by_participant": [],
            "item_averages": {f"sus_{i}": None for i in range(1, 11)},
        }

    overall_avg = (await db.execute(select(func.avg(SusResponse.sus_score)))).scalar()
    by_participant = (
        await db.execute(
            select(SusResponse.participant_code, func.avg(SusResponse.sus_score), func.count())
            .group_by(SusResponse.participant_code)
        )
    ).all()

    item_columns = [getattr(SusResponse, f"sus_{i}") for i in range(1, 11)]
    item_avgs = (await db.execute(select(*[func.avg(c) for c in item_columns]))).one()

    return {
        "total_responses": total,
        "overall_average": float(overall_avg) if overall_avg is not None else None,
        "by_participant": [
            {"participant_code": p, "average_score": float(a), "count": c} for p, a, c in by_participant
        ],
        "item_averages": {
            f"sus_{i}": (float(item_avgs[i - 1]) if item_avgs[i - 1] is not None else None)
            for i in range(1, 11)
        },
    }


@router.get("/sus-responses", dependencies=[Depends(require_evaluation_tab("sus"))])
async def list_sus_responses(
    participant_code: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    """Paginated raw SUS responses (notes table) for the admin SUS Results page."""
    limit = min(limit, MAX_LIST_LIMIT)
    conditions = []
    if participant_code:
        conditions.append(SusResponse.participant_code == participant_code)

    stmt = select(SusResponse).order_by(SusResponse.created_at.desc())
    count_stmt = select(func.count()).select_from(SusResponse)
    if conditions:
        stmt = stmt.where(and_(*conditions))
        count_stmt = count_stmt.where(and_(*conditions))

    total = (await db.execute(count_stmt)).scalar() or 0
    rows = (await db.execute(stmt.limit(limit).offset(offset))).scalars().all()
    return {"total": total, "limit": limit, "offset": offset, "items": [_serialize_sus(r) for r in rows]}


@router.get("/export/asq.csv", dependencies=[Depends(require_evaluation_tab("asq"))])
async def export_asq_csv(participant_code: Optional[str] = None, db: AsyncSession = Depends(get_db)):
    """Stream asq_responses as CSV."""
    _require_export_enabled()
    stmt = select(AsqResponse).order_by(AsqResponse.created_at.desc())
    if participant_code:
        stmt = stmt.where(AsqResponse.participant_code == participant_code)
    stmt = stmt.limit(settings.evaluation_export_max_rows)

    rows = [_serialize_asq(r) for r in (await db.execute(stmt)).scalars().all()]
    fieldnames = list(rows[0].keys()) if rows else [
        "id", "participant_code", "scenario_code", "session_id", "trace_id",
        "asq_1", "asq_2", "asq_3", "average_score", "notes", "condition_code", "created_at",
    ]
    return StreamingResponse(
        _csv_stream(fieldnames, rows),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=asq_responses.csv"},
    )


@router.get("/export/sus.csv", dependencies=[Depends(require_evaluation_tab("sus"))])
async def export_sus_csv(participant_code: Optional[str] = None, db: AsyncSession = Depends(get_db)):
    """Stream sus_responses as CSV."""
    _require_export_enabled()
    stmt = select(SusResponse).order_by(SusResponse.created_at.desc())
    if participant_code:
        stmt = stmt.where(SusResponse.participant_code == participant_code)
    stmt = stmt.limit(settings.evaluation_export_max_rows)

    rows = [_serialize_sus(r) for r in (await db.execute(stmt)).scalars().all()]
    fieldnames = list(rows[0].keys()) if rows else [
        "id", "participant_code", "session_id", "sus_1", "sus_2", "sus_3", "sus_4", "sus_5",
        "sus_6", "sus_7", "sus_8", "sus_9", "sus_10", "sus_score", "notes", "created_at",
    ]
    return StreamingResponse(
        _csv_stream(fieldnames, rows),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=sus_responses.csv"},
    )


@router.get("/overview", dependencies=[Depends(require_evaluation_tab("overview"))])
async def get_overview(db: AsyncSession = Depends(get_db)):
    """Summary cards for the admin Evaluation Overview page — every figure is a single
    SQL aggregate (count/avg/percentile_cont), never a full-table row fetch, so this stays
    cheap regardless of how many chat turns have been logged."""
    total_chat_logs = (await db.execute(select(func.count()).select_from(ChatEvaluationLog))).scalar() or 0

    avg_latency = (await db.execute(select(func.avg(ChatEvaluationLog.total_latency_ms)))).scalar()
    p95_latency = (
        await db.execute(
            select(
                func.percentile_cont(0.95).within_group(ChatEvaluationLog.total_latency_ms)
            )
        )
    ).scalar()

    fallback_count = (
        await db.execute(select(func.count()).select_from(ChatEvaluationLog).where(ChatEvaluationLog.fallback_triggered.is_(True)))
    ).scalar() or 0
    fallback_rate = (fallback_count / total_chat_logs) if total_chat_logs else None

    traces_with_citation = (
        await db.execute(select(func.count(func.distinct(CitationEvaluationLog.trace_id))))
    ).scalar() or 0
    citation_coverage = (traces_with_citation / total_chat_logs) if total_chat_logs else None

    avg_precision = (await db.execute(select(func.avg(EvaluationResult.precision_at_3)))).scalar()
    avg_recall = (await db.execute(select(func.avg(EvaluationResult.recall_at_3)))).scalar()
    avg_hit_rate = (await db.execute(select(func.avg(EvaluationResult.hit_rate_at_3)))).scalar()

    attack_total = (
        await db.execute(select(func.count()).select_from(EvaluationResult).where(EvaluationResult.attack_success.isnot(None)))
    ).scalar() or 0
    attack_success_count = (
        await db.execute(select(func.count()).select_from(EvaluationResult).where(EvaluationResult.attack_success.is_(True)))
    ).scalar() or 0
    attack_success_rate = (attack_success_count / attack_total) if attack_total else None

    avg_asq = (await db.execute(select(func.avg(AsqResponse.average_score)))).scalar()
    avg_sus = (await db.execute(select(func.avg(SusResponse.sus_score)))).scalar()

    acif_block_count = (
        await db.execute(select(func.count()).select_from(AcifTraceLog).where(AcifTraceLog.gate_status == "block"))
    ).scalar() or 0
    acif_warn_count = (
        await db.execute(select(func.count()).select_from(AcifTraceLog).where(AcifTraceLog.gate_status == "warn"))
    ).scalar() or 0

    def _f(v: Any) -> Optional[float]:
        return float(v) if v is not None else None

    return {
        "total_chat_logs": total_chat_logs,
        "average_latency_ms": _f(avg_latency),
        "p95_latency_ms": _f(p95_latency),
        "citation_coverage": _f(citation_coverage),
        "fallback_rate": _f(fallback_rate),
        "average_precision_at_3": _f(avg_precision),
        "average_recall_at_3": _f(avg_recall),
        "average_hit_rate_at_3": _f(avg_hit_rate),
        "attack_success_rate": _f(attack_success_rate),
        "average_asq_score": _f(avg_asq),
        "average_sus_score": _f(avg_sus),
        "acif_block_count": acif_block_count,
        "acif_warning_count": acif_warn_count,
    }


_COMBINED_REPORT_FIELDS = [
    "trace_id", "participant_code", "scenario_code", "question", "answer_status",
    "fallback_triggered", "fallback_reason", "citation_present", "citation_count",
    "retrieved_chunk_count", "selected_context_count",
    "acif_gate_1_status", "acif_gate_2_status", "acif_gate_3_status",
    "acif_gate_4_status", "acif_gate_5_status",
    "total_latency_ms", "retrieval_latency_ms", "graph_latency_ms", "llm_latency_ms",
    "model_used", "created_at",
]


@router.get("/export/combined-report.csv", dependencies=[Depends(require_evaluation_tab("export"))])
async def export_combined_report_csv(
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    participant_code: Optional[str] = None,
    scenario_code: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """Stream the combined academic-report CSV (Part 10) — one row per trace, joining chat,
    retrieval, citation, and ACIF-gate summaries by trace_id. This is the primary export for
    the thesis report; every other export is a narrower slice of the same underlying data."""
    _require_export_enabled()
    conditions = _chat_log_conditions(
        date_from, date_to, None, participant_code, scenario_code, None, None, None, None
    )
    stmt = select(ChatEvaluationLog).order_by(ChatEvaluationLog.created_at.desc())
    if conditions:
        stmt = stmt.where(and_(*conditions))
    stmt = stmt.limit(settings.evaluation_export_max_rows)

    chat_logs = (await db.execute(stmt)).scalars().all()
    trace_ids = [c.trace_id for c in chat_logs]

    if not trace_ids:
        return StreamingResponse(
            _csv_stream(_COMBINED_REPORT_FIELDS, []),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": "attachment; filename=combined_report.csv"},
        )

    retrieval_counts = dict(
        (
            await db.execute(
                select(RetrievalEvaluationLog.trace_id, func.count())
                .where(RetrievalEvaluationLog.trace_id.in_(trace_ids))
                .group_by(RetrievalEvaluationLog.trace_id)
            )
        ).all()
    )
    selected_counts = dict(
        (
            await db.execute(
                select(RetrievalEvaluationLog.trace_id, func.count())
                .where(
                    RetrievalEvaluationLog.trace_id.in_(trace_ids),
                    RetrievalEvaluationLog.selected_for_context.is_(True),
                )
                .group_by(RetrievalEvaluationLog.trace_id)
            )
        ).all()
    )
    citation_counts = dict(
        (
            await db.execute(
                select(CitationEvaluationLog.trace_id, func.count())
                .where(CitationEvaluationLog.trace_id.in_(trace_ids))
                .group_by(CitationEvaluationLog.trace_id)
            )
        ).all()
    )
    gate_rows = (
        await db.execute(
            select(AcifTraceLog.trace_id, AcifTraceLog.gate_number, AcifTraceLog.gate_status).where(
                AcifTraceLog.trace_id.in_(trace_ids)
            )
        )
    ).all()
    gate_status_by_trace: dict[str, dict[int, str]] = {}
    for tid, gate_num, status in gate_rows:
        gate_status_by_trace.setdefault(tid, {})[gate_num] = status

    rows = []
    for c in chat_logs:
        gates = gate_status_by_trace.get(c.trace_id, {})
        citation_count = citation_counts.get(c.trace_id, 0)
        rows.append(
            {
                "trace_id": c.trace_id,
                "participant_code": c.participant_code,
                "scenario_code": c.scenario_code,
                "question": c.user_question,
                "answer_status": c.answer_status,
                "fallback_triggered": c.fallback_triggered,
                "fallback_reason": c.fallback_reason,
                "citation_present": citation_count > 0,
                "citation_count": citation_count,
                "retrieved_chunk_count": retrieval_counts.get(c.trace_id, 0),
                "selected_context_count": selected_counts.get(c.trace_id, 0),
                "acif_gate_1_status": gates.get(1),
                "acif_gate_2_status": gates.get(2),
                "acif_gate_3_status": gates.get(3),
                "acif_gate_4_status": gates.get(4),
                "acif_gate_5_status": gates.get(5),
                "total_latency_ms": c.total_latency_ms,
                "retrieval_latency_ms": c.retrieval_latency_ms,
                "graph_latency_ms": c.graph_latency_ms,
                "llm_latency_ms": c.llm_latency_ms,
                "model_used": c.model_used,
                "created_at": c.created_at.isoformat() if c.created_at else None,
            }
        )

    return StreamingResponse(
        _csv_stream(_COMBINED_REPORT_FIELDS, rows),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=combined_report.csv"},
    )


# ---------------------------------------------------------------------------
# Scenario management (admin CRUD for the /evaluation participant flow)
# ---------------------------------------------------------------------------
# The participant flow reads only is_active=true scenarios via the public
# GET /api/evaluation/scenarios; these endpoints are how an admin populates and
# maintains them (previously the only way was a throwaway seed script). No hard
# delete: asq_responses rows reference scenario_id, so retiring a scenario is a
# soft-deactivate to keep collected study data intact.


class ScenarioCreate(BaseModel):
    code: str = Field(..., min_length=1, max_length=100)
    title: str = Field(..., min_length=1, max_length=255)
    instruction: str = Field(..., min_length=1)
    expected_task: Optional[str] = None
    order_index: int = 0
    is_active: bool = True


class ScenarioUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    instruction: Optional[str] = Field(None, min_length=1)
    expected_task: Optional[str] = None
    order_index: Optional[int] = None
    is_active: Optional[bool] = None


def _scenario_payload(s: EvaluationScenario) -> dict:
    return {
        "id": str(s.id),
        "code": s.code,
        "title": s.title,
        "instruction": s.instruction,
        "expected_task": s.expected_task,
        "order_index": s.order_index,
        "is_active": s.is_active,
        "created_at": s.created_at.isoformat() if s.created_at else None,
    }


@router.get("/scenarios", dependencies=[Depends(require_evaluation_tab("scenarios"))])
async def list_scenarios_admin(db: AsyncSession = Depends(get_db)):
    """All scenarios including inactive ones (the public endpoint hides inactive)."""
    rows = (
        await db.execute(
            select(EvaluationScenario).order_by(EvaluationScenario.order_index)
        )
    ).scalars().all()
    return {"scenarios": [_scenario_payload(s) for s in rows]}


@router.post("/scenarios", status_code=201, dependencies=[Depends(require_evaluation_tab("scenarios"))])
async def create_scenario(payload: ScenarioCreate, db: AsyncSession = Depends(get_db)):
    """Create a participant scenario. `code` must be unique (e.g. S1, S2)."""
    existing = (
        await db.execute(
            select(EvaluationScenario).where(EvaluationScenario.code == payload.code)
        )
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail=f"Scenario code already exists: {payload.code}")

    scenario = EvaluationScenario(
        code=payload.code,
        title=payload.title,
        instruction=payload.instruction,
        expected_task=payload.expected_task,
        order_index=payload.order_index,
        is_active=payload.is_active,
    )
    db.add(scenario)
    await db.commit()
    await db.refresh(scenario)
    return _scenario_payload(scenario)


@router.patch("/scenarios/{scenario_id}", dependencies=[Depends(require_evaluation_tab("scenarios"))])
async def update_scenario(
    scenario_id: UUID, payload: ScenarioUpdate, db: AsyncSession = Depends(get_db)
):
    """Partial update — `code` is immutable (ASQ rows store scenario_code denormalized)."""
    scenario = (
        await db.execute(
            select(EvaluationScenario).where(EvaluationScenario.id == scenario_id)
        )
    ).scalar_one_or_none()
    if not scenario:
        raise HTTPException(status_code=404, detail="Scenario not found")

    changes = payload.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(scenario, field, value)
    await db.commit()
    await db.refresh(scenario)
    return _scenario_payload(scenario)
