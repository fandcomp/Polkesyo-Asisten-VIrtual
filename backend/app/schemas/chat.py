"""Chat request/response schemas."""
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any


class MessageMetadata(BaseModel):
    """Optional metadata for messages."""
    source_page: Optional[str] = None
    page_url: Optional[str] = None
    user_agent: Optional[str] = None


class ChatRequest(BaseModel):
    """Chat message request."""
    message: str = Field(..., min_length=1, max_length=5000)
    metadata: Optional[MessageMetadata] = None
    # Evaluation Layer — set by the /evaluation participant flow (Phase 4) and the gold-QA
    # runner (Phase 3), never by the normal public widget. Omitted (default) behaves exactly
    # as before this field existed.
    evaluation_mode: bool = False
    participant_code: Optional[str] = None
    scenario_code: Optional[str] = None


class SourceReference(BaseModel):
    """Source citation for answer."""
    document_title: Optional[str] = None
    document_id: Optional[str] = None
    section: Optional[str] = None
    page: Optional[int] = None
    chunk_id: Optional[str] = None


class AttachmentReference(BaseModel):
    """Downloadable form/attachment produced by the structure-aware document extraction
    pipeline (form_text/form_vision zones -> document_form_extracts). Only admin-approved
    (`status == "active"`) extracts ever reach this schema (CLAUDE.md §4.7/§21.6)."""
    form_title: str
    document_id: str
    download_url: str


class ChatResponse(BaseModel):
    """Chat message response."""
    answer: str
    sources: list[SourceReference] = []
    attachments: list[AttachmentReference] = []
    status: str = "answered"
    session_id: UUID
    created_at: datetime
    # Evaluation Layer Phase 1 — correlates this turn across chat_evaluation_logs,
    # retrieval_evaluation_logs, citation_evaluation_logs, acif_trace_logs, graph_consistency_logs.
    trace_id: Optional[str] = None
    latency_ms: Optional[int] = None
    # Set when status == "needs_clarification": the follow-up question the assistant asks
    # to disambiguate an elliptical/too-general question (the same text is also in answer).
    clarification_question: Optional[str] = None


class ChatTurn(BaseModel):
    """Single chat message turn."""
    role: str  # "user" or "assistant"
    message: str
    timestamp: datetime


class ErrorResponse(BaseModel):
    """Structured transport-level error (non-2xx responses).

    ``message`` is a user-displayable Indonesian sentence — never a stack trace or
    internal detail. ``error_type`` is one of: session_not_found, timeout, rate_limit,
    retrieval_error, llm_error, network_error, internal_error, unknown.
    """
    trace_id: str
    error_type: str
    message: str
    fallback: bool = True
