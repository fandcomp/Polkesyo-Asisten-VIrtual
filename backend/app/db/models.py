"""Database models for Campus Virtual Assistant."""
from datetime import datetime
from uuid import UUID, uuid4
from sqlalchemy import Column, UUID as SQLA_UUID, DateTime, String, ForeignKey, Integer, Text, JSON, Float, Boolean, CheckConstraint, func
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

Base = declarative_base()


class Session(Base):
    """Anonymous user session."""
    __tablename__ = "sessions"

    id = Column(SQLA_UUID(as_uuid=True), primary_key=True, default=uuid4)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    last_active_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    status = Column(String(50), nullable=False, default="active")
    user_agent_hash = Column(String(64), nullable=True)

    consent_logs = relationship("ConsentLog", back_populates="session", cascade="all, delete-orphan")
    chat_history = relationship("ChatHistory", back_populates="session", cascade="all, delete-orphan")
    security_events = relationship("SecurityEvent", back_populates="session", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Session {self.id}>"


class ConsentLog(Base):
    """Consent tracking for sessions."""
    __tablename__ = "consent_log"

    id = Column(SQLA_UUID(as_uuid=True), primary_key=True, default=uuid4)
    session_id = Column(SQLA_UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False)
    consent_value = Column(String(50), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    source = Column(String(100), nullable=True)

    session = relationship("Session", back_populates="consent_logs")

    def __repr__(self) -> str:
        return f"<ConsentLog {self.id}>"


class ChatHistory(Base):
    """Chat message history."""
    __tablename__ = "chat_history"

    id = Column(SQLA_UUID(as_uuid=True), primary_key=True, default=uuid4)
    session_id = Column(SQLA_UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False)
    turn_index = Column(Integer(), nullable=False)
    role = Column(String(10), nullable=False)
    message = Column(Text(), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    metadata_json = Column(JSON(), nullable=True)

    session = relationship("Session", back_populates="chat_history")

    def __repr__(self) -> str:
        return f"<ChatHistory {self.id}>"


class SecurityEvent(Base):
    """Security events log."""
    __tablename__ = "security_events"

    id = Column(SQLA_UUID(as_uuid=True), primary_key=True, default=uuid4)
    session_id = Column(SQLA_UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False)
    event_type = Column(String(50), nullable=False)
    severity = Column(String(50), nullable=False)
    message = Column(Text(), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    metadata_json = Column(JSON(), nullable=True)

    session = relationship("Session", back_populates="security_events")

    def __repr__(self) -> str:
        return f"<SecurityEvent {self.id}>"


class Document(Base):
    """Official source documents."""
    __tablename__ = "documents"

    id = Column(SQLA_UUID(as_uuid=True), primary_key=True, default=uuid4)
    title = Column(String(255), nullable=False)
    document_type = Column(String(50), nullable=False)
    source_url = Column(String(1024), nullable=True)
    source_type = Column(String(50), nullable=False)
    status = Column(String(50), nullable=False, default="discovered")
    year = Column(Integer(), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    versions = relationship("DocumentVersion", back_populates="document", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Document {self.id}>"


class DocumentVersion(Base):
    """Document versions with checksums."""
    __tablename__ = "document_versions"

    id = Column(SQLA_UUID(as_uuid=True), primary_key=True, default=uuid4)
    document_id = Column(SQLA_UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    version = Column(Integer(), nullable=False)
    checksum = Column(String(64), nullable=False)
    source_url = Column(String(1024), nullable=True)
    raw_file_path = Column(String(1024), nullable=True)
    status = Column(String(50), nullable=False, default="created")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    document = relationship("Document", back_populates="versions")
    chunks = relationship("DocumentChunk", back_populates="document_version", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<DocumentVersion {self.id}>"


class DocumentChunk(Base):
    """Immutable original document chunks (text and visual)."""
    __tablename__ = "document_chunks"

    id = Column(SQLA_UUID(as_uuid=True), primary_key=True, default=uuid4)
    chunk_id = Column(String(255), nullable=False)
    document_id = Column(SQLA_UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    document_version_id = Column(SQLA_UUID(as_uuid=True), ForeignKey("document_versions.id", ondelete="CASCADE"), nullable=False)
    chunk_index = Column(Integer(), nullable=False)
    page = Column(Integer(), nullable=True)
    section = Column(String(255), nullable=True)
    original_text = Column(Text(), nullable=False)
    token_count = Column(Integer(), nullable=True)
    status = Column(String(50), nullable=False, default="created")
    active = Column(Integer(), nullable=False, server_default="0")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    # Visual chunk fields
    chunk_type = Column(String(50), nullable=False, default="text")
    image_artifact_path = Column(String(1024), nullable=True)
    image_hash = Column(String(64), nullable=True)
    bounding_box = Column(JSON(), nullable=True)
    extraction_method = Column(String(100), nullable=True)
    vision_model = Column(String(255), nullable=True)
    vision_prompt_version = Column(Integer(), nullable=True)
    raw_visual_description = Column(Text(), nullable=True)
    visible_text_draft = Column(Text(), nullable=True)
    uncertainty_notes = Column(Text(), nullable=True)
    confidence_score = Column(Float(), nullable=True)
    risk_flags = Column(JSON(), nullable=True, server_default="[]")
    admin_status = Column(String(50), nullable=False, default="pending_review")
    reviewed_by = Column(String(100), nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    admin_notes = Column(Text(), nullable=True)

    document = relationship("Document")
    document_version = relationship("DocumentVersion", back_populates="chunks")
    summaries = relationship("ChunkSummary", back_populates="chunk", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<DocumentChunk {self.id}>"


class ChunkSummary(Base):
    """LLM draft and admin-approved summaries for chunks."""
    __tablename__ = "chunk_summaries"

    id = Column(SQLA_UUID(as_uuid=True), primary_key=True, default=uuid4)
    chunk_id = Column(SQLA_UUID(as_uuid=True), ForeignKey("document_chunks.id", ondelete="CASCADE"), nullable=False)
    llm_summary_draft = Column(Text(), nullable=True)
    admin_edited_summary = Column(Text(), nullable=True)
    approved_summary = Column(Text(), nullable=True)
    summary_model = Column(String(100), nullable=True)
    summary_status = Column(String(50), nullable=False, default="created")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    chunk = relationship("DocumentChunk", back_populates="summaries")

    def __repr__(self) -> str:
        return f"<ChunkSummary {self.id}>"


class ChunkReview(Base):
    """Chunk review audit trail."""
    __tablename__ = "chunk_reviews"

    id = Column(SQLA_UUID(as_uuid=True), primary_key=True, default=uuid4)
    chunk_id = Column(SQLA_UUID(as_uuid=True), ForeignKey("document_chunks.id", ondelete="CASCADE"), nullable=False)
    reviewer_id = Column(String(100), nullable=True)
    decision = Column(String(50), nullable=False)
    admin_notes = Column(Text(), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    chunk = relationship("DocumentChunk")

    def __repr__(self) -> str:
        return f"<ChunkReview {self.id}>"


class ChunkEntity(Base):
    """Durable, per-chunk, admin-editable entity record (CLAUDE.md graph-safety constraint).

    Replaces the previous ephemeral behavior where `GraphService.extract_entities` ran live
    on every `GET /admin/documents/{id}/chunks` request with no persistence, no id, and no
    way to correct terminology. Mirrors `ChunkSummary`'s draft -> edited -> confirmed shape:
    `detected_text`/`entity_type` are the immutable original detection (or the admin-typed
    values when `source == "admin_added"`); `corrected_text`/`corrected_type` are the optional
    admin override. Never hard-deleted — `status == "rejected"` is the only "delete"
    mechanism, matching `ChunkReview`'s append-only audit-trail convention.

    Editing a row here never renames or mutates an existing Neo4j entity node in place — Neo4j
    nodes are MERGE'd globally by (label, name) and shared across every document that mentions
    them (see graph_service.py). A correction only changes which node this chunk's contribution
    resolves to on the next reindex (MERGE-or-create), never an in-place SET/rename of a node
    another document still references.
    """
    __tablename__ = "chunk_entities"

    id = Column(SQLA_UUID(as_uuid=True), primary_key=True, default=uuid4)
    chunk_id = Column(SQLA_UUID(as_uuid=True), ForeignKey("document_chunks.id", ondelete="CASCADE"), nullable=False)
    document_id = Column(SQLA_UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    # allowed: ProgramStudi, JalurPendaftaran, TahapSeleksi, Persyaratan, Jadwal, Biaya
    # (GraphService.ALLOWED_ENTITY_TYPES is the single source of truth, validated at the route)
    entity_type = Column(String(50), nullable=False)
    detected_text = Column(String(500), nullable=False)
    corrected_text = Column(String(500), nullable=True)
    corrected_type = Column(String(50), nullable=True)
    # allowed: llm_detected, admin_added
    source = Column(String(20), nullable=False, default="llm_detected")
    # allowed: detected, confirmed, edited, rejected
    status = Column(String(20), nullable=False, default="detected")
    reviewed_by = Column(String(100), nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    chunk = relationship("DocumentChunk")
    document = relationship("Document")

    def __repr__(self) -> str:
        return f"<ChunkEntity {self.id} {self.entity_type} {self.status}>"


class DocumentSource(Base):
    """Official document sources monitored by DocumentMonitorAgent (CLAUDE.md §11A.3/§23.1)."""
    __tablename__ = "document_sources"

    id = Column(SQLA_UUID(as_uuid=True), primary_key=True, default=uuid4)
    source_name = Column(String(255), nullable=False)
    source_url = Column(String(1024), nullable=False)
    source_type = Column(String(50), nullable=False, default="official_sync")
    is_active = Column(Boolean(), nullable=False, default=True)
    last_checked_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    def __repr__(self) -> str:
        return f"<DocumentSource {self.id}>"


class DocumentFormExtract(Base):
    """Standalone form/attachment .docx extracted from a `form_text`/`form_vision` zone
    (structure-aware document extraction plan) — deliberately NOT a `DocumentChunk` row:
    these pages are excluded from chunking/vector retrieval entirely, never indexed, never
    used as RAG context (CLAUDE.md §4.7). Same admin-approval lifecycle convention as
    `document_chunks`/visual chunks (CLAUDE.md §21.6): a generated `.docx` is never servable
    to end users until `status == "active"`.
    """
    __tablename__ = "document_form_extracts"

    id = Column(SQLA_UUID(as_uuid=True), primary_key=True, default=uuid4)
    document_id = Column(SQLA_UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    document_version_id = Column(SQLA_UUID(as_uuid=True), ForeignKey("document_versions.id", ondelete="CASCADE"), nullable=False)
    # allowed: form_text, form_vision
    zone_type = Column(String(20), nullable=False)
    form_title = Column(String(255), nullable=False)
    source_page_start = Column(Integer(), nullable=False)
    source_page_end = Column(Integer(), nullable=False)
    # allowed: text, vision
    extraction_method = Column(String(20), nullable=False)
    # Internal filesystem path only (mirrors DocumentChunk.image_artifact_path) — never
    # exposed directly; served via the admin/public download routes' FileResponse.
    docx_artifact_path = Column(String(1024), nullable=True)
    # allowed: pending_review, approved, rejected, needs_revision, active, archived
    status = Column(String(50), nullable=False, default="pending_review")
    reviewed_by = Column(String(100), nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    admin_notes = Column(Text(), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    document = relationship("Document")
    document_version = relationship("DocumentVersion")

    def __repr__(self) -> str:
        return f"<DocumentFormExtract {self.id} {self.status}>"


class AgentRunLog(Base):
    """Per-agent execution log (CLAUDE.md §11A.5) — every agent invocation writes one row here."""
    __tablename__ = "agent_run_logs"

    id = Column(SQLA_UUID(as_uuid=True), primary_key=True, default=uuid4)
    agent_name = Column(String(100), nullable=False)
    task_type = Column(String(100), nullable=True)
    input_summary = Column(Text(), nullable=True)
    output_summary = Column(Text(), nullable=True)
    status = Column(String(50), nullable=False)
    latency_ms = Column(Float(), nullable=True)
    error_message = Column(Text(), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    def __repr__(self) -> str:
        return f"<AgentRunLog {self.agent_name} {self.status}>"


class AcifDecisionLog(Base):
    """Structured per-turn ACIF decision (CLAUDE.md §11A.2), written by ACIFAgent."""
    __tablename__ = "acif_decision_logs"

    id = Column(SQLA_UUID(as_uuid=True), primary_key=True, default=uuid4)
    query_id = Column(SQLA_UUID(as_uuid=True), nullable=True)
    document_id = Column(SQLA_UUID(as_uuid=True), nullable=True)
    chunk_id = Column(SQLA_UUID(as_uuid=True), nullable=True)
    agent_run_id = Column(SQLA_UUID(as_uuid=True), ForeignKey("agent_run_logs.id", ondelete="SET NULL"), nullable=True)
    risk_level = Column(String(20), nullable=False)
    filtering_mode = Column(String(20), nullable=False)
    context_integrity_score = Column(Float(), nullable=True)
    source_integrity_score = Column(Float(), nullable=True)
    graph_integrity_score = Column(Float(), nullable=True)
    decision = Column(String(50), nullable=False)
    rejection_reason = Column(Text(), nullable=True)
    fallback_required = Column(Boolean(), nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    def __repr__(self) -> str:
        return f"<AcifDecisionLog {self.id} {self.decision}>"


class OpenRouterUsageLog(Base):
    """OpenRouter API usage logging for cost tracking."""
    __tablename__ = "openrouter_usage_logs"

    id = Column(SQLA_UUID(as_uuid=True), primary_key=True, default=uuid4)
    model = Column(String(255), nullable=False)
    prompt_tokens = Column(Integer(), nullable=False, default=0)
    completion_tokens = Column(Integer(), nullable=False, default=0)
    total_tokens = Column(Integer(), nullable=False, default=0)
    cost_usd = Column(Float(), nullable=False, default=0.0)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    def __repr__(self) -> str:
        return f"<OpenRouterUsageLog {self.id}>"


class ChatEvaluationLog(Base):
    """Per-trace technical evaluation log for the /chat pipeline (Evaluation Layer Phase 1).

    One row per chat turn processed by ChatCoreService.process_message, keyed by trace_id.
    Populated by EvaluationLogger; a logging failure here must never break the chat response
    (see chat_core.py's try/except around the EvaluationLogger call).
    """
    __tablename__ = "chat_evaluation_logs"

    id = Column(SQLA_UUID(as_uuid=True), primary_key=True, default=uuid4)
    trace_id = Column(String(64), nullable=False, unique=True)
    session_id = Column(SQLA_UUID(as_uuid=True), nullable=True)
    participant_code = Column(String(100), nullable=True)
    scenario_code = Column(String(100), nullable=True)
    evaluation_mode = Column(Boolean(), nullable=False, default=False)
    user_question = Column(Text(), nullable=False)
    normalized_question = Column(Text(), nullable=True)
    final_answer = Column(Text(), nullable=True)
    fallback_triggered = Column(Boolean(), nullable=False, default=False)
    fallback_reason = Column(Text(), nullable=True)
    answer_status = Column(String(50), nullable=False)
    # Query Understanding Layer fields — how the question was interpreted before retrieval.
    rewritten_queries = Column(JSON(), nullable=True)
    detected_terms = Column(JSON(), nullable=True)
    expanded_terms = Column(JSON(), nullable=True)
    intent = Column(String(50), nullable=True)
    intent_confidence = Column(Float(), nullable=True)
    clarification_used = Column(Boolean(), nullable=False, default=False, server_default="false")
    total_latency_ms = Column(Integer(), nullable=True)
    retrieval_latency_ms = Column(Integer(), nullable=True)
    graph_latency_ms = Column(Integer(), nullable=True)
    acif_latency_ms = Column(Integer(), nullable=True)
    llm_latency_ms = Column(Integer(), nullable=True)
    output_verification_latency_ms = Column(Integer(), nullable=True)
    model_used = Column(String(255), nullable=True)
    input_tokens = Column(Integer(), nullable=True)
    output_tokens = Column(Integer(), nullable=True)
    estimated_cost = Column(Float(), nullable=True)
    error_message = Column(Text(), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    def __repr__(self) -> str:
        return f"<ChatEvaluationLog {self.trace_id} {self.answer_status}>"


class RetrievalEvaluationLog(Base):
    """Per-chunk retrieval evaluation log — one row per chunk considered for a trace_id."""
    __tablename__ = "retrieval_evaluation_logs"

    id = Column(SQLA_UUID(as_uuid=True), primary_key=True, default=uuid4)
    trace_id = Column(String(64), nullable=False)
    chunk_id = Column(String(255), nullable=True)
    document_id = Column(String(255), nullable=True)
    document_version_id = Column(String(255), nullable=True)
    document_title = Column(Text(), nullable=True)
    page_number = Column(Integer(), nullable=True)
    chunk_type = Column(String(50), nullable=True)
    # allowed: vector, graph, hybrid, visual_chunk, cache
    retrieval_source = Column(String(20), nullable=False, default="vector")
    retrieval_rank = Column(Integer(), nullable=False)
    retrieval_score = Column(Float(), nullable=True)
    selected_for_context = Column(Boolean(), nullable=False, default=False)
    rejected_reason = Column(Text(), nullable=True)
    metadata_json = Column(JSON(), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    def __repr__(self) -> str:
        return f"<RetrievalEvaluationLog {self.trace_id} rank={self.retrieval_rank}>"


class CitationEvaluationLog(Base):
    """Per-citation evaluation log — one row per source actually cited in a trace's final answer."""
    __tablename__ = "citation_evaluation_logs"

    id = Column(SQLA_UUID(as_uuid=True), primary_key=True, default=uuid4)
    trace_id = Column(String(64), nullable=False)
    document_id = Column(String(255), nullable=True)
    chunk_id = Column(String(255), nullable=True)
    document_title = Column(Text(), nullable=True)
    page_number = Column(Integer(), nullable=True)
    # allowed: text, graph, visual_chunk, table, mixed
    citation_type = Column(String(20), nullable=False, default="text")
    is_visual_source = Column(Boolean(), nullable=False, default=False)
    is_valid = Column(Boolean(), nullable=True)
    validation_notes = Column(Text(), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    def __repr__(self) -> str:
        return f"<CitationEvaluationLog {self.trace_id} {self.document_title}>"


class AcifTraceLog(Base):
    """One row per ACIF gate per trace — the safe, admin-facing audit trail (CLAUDE.md §11).

    Deliberately has no column that could ever hold a raw prompt, scoring formula, or matched
    attack-phrase text — only decision/score/summary fields. This is structurally separate from
    the pre-existing `acif_decision_logs` (agentic /api/chat/agentic path, gates 1-3 only, one
    denormalized row per decision); this table covers all 5 gates for the /chat pipeline.
    """
    __tablename__ = "acif_trace_logs"

    id = Column(SQLA_UUID(as_uuid=True), primary_key=True, default=uuid4)
    trace_id = Column(String(64), nullable=False)
    gate_number = Column(Integer(), nullable=False)
    gate_name = Column(String(100), nullable=False)
    # allowed: pass, warn, block, fallback, error
    gate_status = Column(String(20), nullable=False)
    risk_score = Column(Float(), nullable=True)
    # allowed: low, medium, high, critical
    risk_level = Column(String(20), nullable=True)
    action_taken = Column(String(255), nullable=True)
    risk_flags = Column(JSON(), nullable=True)
    public_summary = Column(Text(), nullable=True)
    admin_summary = Column(Text(), nullable=True)
    latency_ms = Column(Integer(), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    def __repr__(self) -> str:
        return f"<AcifTraceLog {self.trace_id} gate{self.gate_number} {self.gate_status}>"


class GraphConsistencyLog(Base):
    """Per-entity graph-document consistency log (ACIF Gate 3 detail)."""
    __tablename__ = "graph_consistency_logs"

    id = Column(SQLA_UUID(as_uuid=True), primary_key=True, default=uuid4)
    trace_id = Column(String(64), nullable=False)
    graph_entity = Column(Text(), nullable=True)
    graph_relation = Column(Text(), nullable=True)
    supporting_document_id = Column(String(255), nullable=True)
    supporting_chunk_id = Column(String(255), nullable=True)
    # allowed: supported, weakly_supported, unsupported, conflict, skipped
    consistency_status = Column(String(30), nullable=False)
    notes = Column(Text(), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    def __repr__(self) -> str:
        return f"<GraphConsistencyLog {self.trace_id} {self.consistency_status}>"


class EvaluationRun(Base):
    """One gold-QA-dataset run (Evaluation Layer Phase 3), triggered manually via
    `python -m app.evaluation.run_evaluation` — never automatically on server startup."""
    __tablename__ = "evaluation_runs"

    id = Column(SQLA_UUID(as_uuid=True), primary_key=True, default=uuid4)
    run_name = Column(String(255), nullable=False)
    config_name = Column(String(100), nullable=True)
    # allowed: technical, retrieval, security, performance, usability, full
    run_type = Column(String(20), nullable=False, default="full")
    total_questions = Column(Integer(), nullable=False, default=0)
    completed_questions = Column(Integer(), nullable=False, default=0)
    # allowed: pending, running, completed, failed, cancelled
    status = Column(String(20), nullable=False, default="pending")
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    created_by = Column(String(100), nullable=True)
    notes = Column(Text(), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    def __repr__(self) -> str:
        return f"<EvaluationRun {self.run_name} {self.status}>"


class EvaluationResult(Base):
    """Per-question metrics for one evaluation_runs row (precision/recall/citation/fallback/
    attack-success/latency) — computed by run_evaluation.py from the Phase 1 logging tables."""
    __tablename__ = "evaluation_results"

    id = Column(SQLA_UUID(as_uuid=True), primary_key=True, default=uuid4)
    evaluation_run_id = Column(SQLA_UUID(as_uuid=True), ForeignKey("evaluation_runs.id", ondelete="CASCADE"), nullable=False)
    question_id = Column(String(64), nullable=False)
    trace_id = Column(String(64), nullable=True)
    category = Column(String(100), nullable=True)
    # allowed: answer, fallback, block_or_fallback
    expected_behavior = Column(String(30), nullable=False)
    precision_at_3 = Column(Float(), nullable=True)
    recall_at_3 = Column(Float(), nullable=True)
    hit_rate_at_3 = Column(Float(), nullable=True)
    citation_present = Column(Boolean(), nullable=True)
    citation_correct = Column(Boolean(), nullable=True)
    fallback_correct = Column(Boolean(), nullable=True)
    answer_relevance_score = Column(Float(), nullable=True)
    faithfulness_score = Column(Float(), nullable=True)
    hallucination_detected = Column(Boolean(), nullable=True)
    attack_success = Column(Boolean(), nullable=True)
    total_latency_ms = Column(Integer(), nullable=True)
    retrieval_latency_ms = Column(Integer(), nullable=True)
    llm_latency_ms = Column(Integer(), nullable=True)
    notes = Column(Text(), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    def __repr__(self) -> str:
        return f"<EvaluationResult {self.question_id} run={self.evaluation_run_id}>"


class EvaluationScenario(Base):
    """A task scenario shown in the /evaluation participant flow (Phase 4), followed by an
    ASQ form after completion."""
    __tablename__ = "evaluation_scenarios"

    id = Column(SQLA_UUID(as_uuid=True), primary_key=True, default=uuid4)
    code = Column(String(100), nullable=False, unique=True)
    title = Column(String(255), nullable=False)
    instruction = Column(Text(), nullable=False)
    expected_task = Column(Text(), nullable=True)
    order_index = Column(Integer(), nullable=False, default=0)
    is_active = Column(Boolean(), nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    def __repr__(self) -> str:
        return f"<EvaluationScenario {self.code}>"


class AsqResponse(Base):
    """After-Scenario Questionnaire response — 3 items, 1-7 scale, shown after each scenario
    (not after every normal chat turn)."""
    __tablename__ = "asq_responses"

    id = Column(SQLA_UUID(as_uuid=True), primary_key=True, default=uuid4)
    participant_code = Column(String(100), nullable=False)
    scenario_id = Column(SQLA_UUID(as_uuid=True), ForeignKey("evaluation_scenarios.id", ondelete="CASCADE"), nullable=False)
    scenario_code = Column(String(100), nullable=False)
    session_id = Column(String(64), nullable=True)
    trace_id = Column(String(64), nullable=True)
    asq_1 = Column(Integer(), nullable=False)
    asq_2 = Column(Integer(), nullable=False)
    asq_3 = Column(Integer(), nullable=False)
    average_score = Column(Float(), nullable=False)
    notes = Column(Text(), nullable=True)
    # Nullable hook for a future within-subject ACIF-on/off usability study (Evaluation Layer
    # Phase 5) — e.g. "with_acif" / "without_acif". No participant flow sets this yet; existing
    # and production rows stay NULL.
    condition_code = Column(String(50), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        CheckConstraint("asq_1 BETWEEN 1 AND 7", name="ck_asq_responses_asq_1_range"),
        CheckConstraint("asq_2 BETWEEN 1 AND 7", name="ck_asq_responses_asq_2_range"),
        CheckConstraint("asq_3 BETWEEN 1 AND 7", name="ck_asq_responses_asq_3_range"),
    )

    def __repr__(self) -> str:
        return f"<AsqResponse {self.participant_code} {self.scenario_code}>"


class SusResponse(Base):
    """System Usability Scale response — 10 items, 1-5 scale, shown once after all scenarios
    are completed."""
    __tablename__ = "sus_responses"

    id = Column(SQLA_UUID(as_uuid=True), primary_key=True, default=uuid4)
    participant_code = Column(String(100), nullable=False)
    session_id = Column(String(64), nullable=True)
    sus_1 = Column(Integer(), nullable=False)
    sus_2 = Column(Integer(), nullable=False)
    sus_3 = Column(Integer(), nullable=False)
    sus_4 = Column(Integer(), nullable=False)
    sus_5 = Column(Integer(), nullable=False)
    sus_6 = Column(Integer(), nullable=False)
    sus_7 = Column(Integer(), nullable=False)
    sus_8 = Column(Integer(), nullable=False)
    sus_9 = Column(Integer(), nullable=False)
    sus_10 = Column(Integer(), nullable=False)
    sus_score = Column(Float(), nullable=False)
    notes = Column(Text(), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = tuple(
        CheckConstraint(f"sus_{i} BETWEEN 1 AND 5", name=f"ck_sus_responses_sus_{i}_range") for i in range(1, 11)
    )

    def __repr__(self) -> str:
        return f"<SusResponse {self.participant_code} score={self.sus_score}>"
