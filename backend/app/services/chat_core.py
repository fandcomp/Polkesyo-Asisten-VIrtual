"""Chat core service — orchestrates the full pipeline."""
import hashlib
import time
from datetime import datetime
from uuid import UUID, uuid4
from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncSession
import logging

from app.core.config import settings
from app.core.errors import SessionNotFoundError
from app.db.models import ChatHistory, SecurityEvent
from app.schemas.chat import AttachmentReference, ChatRequest, ChatResponse, SourceReference, MessageMetadata
from app.agents.answer_composer_agent import AnswerComposerAgent
from app.services.session_service import SessionService, ConsentService
from app.services.acif.input_integrity_checker import InputIntegrityChecker
from app.services.acif.schemas import ACIFDecision, ACIFGate1Result
from app.services.vector_retriever import VectorRetrieverService
from app.services.multi_query_retriever import MultiQueryRetriever
from app.services.query_understanding import QueryUnderstandingService
from app.services.graph_retriever import GraphRetrieverService
from app.services.acif.context_integrity_scorer import ContextIntegrityScorer
from app.services.acif.graph_document_consistency import GraphDocumentConsistency
from app.services.acif.prompt_boundary_builder import (
    PromptBoundaryBuilder,
    VectorChunk,
    GraphEvidence,
)
from app.services.openrouter_client import OpenRouterClient, OpenRouterError, check_openrouter_budget
from app.services.acif.output_claim_verifier import OutputClaimVerifier, FallbackResponse
from app.services.rate_limiter_service import get_rate_limiter
from app.services.redis_cache_service import get_cache_service
from app.services.evaluation_logger import EvaluationLogger


logger = logging.getLogger(__name__)


class ChatCoreService:
    """Orchestrate chat request processing."""

    @staticmethod
    async def process_message(
        db: AsyncSession,
        session_id: UUID,
        message: str,
        metadata: MessageMetadata | None = None,
        evaluation_mode: bool = False,
        participant_code: str | None = None,
        scenario_code: str | None = None,
        ablation_disable_acif: bool = False,
        disabled_gates: frozenset[int] | None = None,
        disable_graph_rag: bool = False,
    ) -> ChatResponse:
        """Process user message through full pipeline.

        `evaluation_mode`/`participant_code`/`scenario_code` are Evaluation Layer metadata
        (Phase 3's gold-QA runner and Phase 4's ASQ/SUS participant flow both pass these) —
        purely additive: when omitted (every existing/public caller), behavior is identical
        to before this parameter existed.

        `ablation_disable_acif` is the original thesis with/without-ACIF comparison switch
        (Evaluation Layer Phase 5) — shorthand for "disable all 5 gates." `disabled_gates` is
        the N-gate ablation study generalization (2026-07-24): an explicit subset of {1..5} to
        bypass, enabling any of the 11 cumulative/leave-one-out configs in
        `run_evaluation.ABLATION_GATE_MATRIX` rather than only the all-or-nothing case. Both
        params only ever take effect when `evaluation_mode=True` — asserted below — so no real
        `/chat` request can end up bypassing any gate. Gate 4 specifically switches to
        `PromptBoundaryBuilder.build_naive` (a plain "stuff the context into the prompt"
        baseline, rather than a no-op) whenever Gate 4 is in the disabled set, regardless of
        which other gates are also disabled. See CLAUDE.md §4.4/§33.11: ACIF must never be
        bypassed for production answers.

        `disable_graph_rag` (GraphRAG-isolation experiment, 2026-07-25): short-circuits
        GraphRAG retrieval to an empty result set, so a "Vector RAG only" condition can be
        compared against "Vector RAG + GraphRAG" while ACIF gates stay fixed. Same
        evaluation-mode-only-effect discipline as `disabled_gates`. Not a perfectly clean
        control: Gate 2's `no_contradiction` bonus becomes structurally unawardable and Gate 3
        always returns `proceed_with_caution` without graph evidence — both gates already have
        tested graceful-empty behavior for this (`context_integrity_scorer.py`,
        `graph_document_consistency.py`), but report this caveat alongside any comparison.
        """
        _disabled_gates: frozenset[int] = (
            frozenset({1, 2, 3, 4, 5}) if ablation_disable_acif
            else frozenset(disabled_gates or ())
        )
        if not _disabled_gates.issubset({1, 2, 3, 4, 5}):
            raise ValueError(f"disabled_gates must be a subset of {{1,2,3,4,5}}, got {_disabled_gates}")
        assert not (_disabled_gates and not evaluation_mode), (
            "disabled_gates/ablation_disable_acif may only be used with evaluation_mode=True"
        )
        assert not (disable_graph_rag and not evaluation_mode), (
            "disable_graph_rag may only be used with evaluation_mode=True"
        )
        gate1_disabled = 1 in _disabled_gates
        gate2_disabled = 2 in _disabled_gates
        gate3_disabled = 3 in _disabled_gates
        gate4_disabled = 4 in _disabled_gates
        gate5_disabled = 5 in _disabled_gates

        # Evaluation Layer Phase 1 — trace_id correlates this turn across chat_evaluation_logs,
        # retrieval_evaluation_logs, citation_evaluation_logs, acif_trace_logs, and
        # graph_consistency_logs. Collected below as the pipeline runs, then persisted once at
        # the end via EvaluationLogger — never raises, never delays/breaks the chat response
        # (see `_finalize`'s try/except).
        trace_id = str(uuid4())
        _start = time.perf_counter()
        gate_rows: list[dict] = []
        retrieval_rows: list[dict] = []
        citation_rows: list[dict] = []
        graph_consistency_rows: list[dict] = []
        timings: dict[str, int] = {}
        generation_usage: dict | None = None
        # Query Understanding result — None until the QU step runs, so early _finalize
        # calls (no_consent, rate_limited, Gate 1 reject) log without QU fields.
        analysis = None

        async def _finalize(
            answer: str,
            status: str,
            sources: list[SourceReference],
            fallback_triggered: bool = False,
            fallback_reason: str | None = None,
            error_message: str | None = None,
            clarification_question: str | None = None,
            attachments: list[AttachmentReference] | None = None,
        ) -> ChatResponse:
            """Build the final ChatResponse and, as a best-effort side effect, persist this
            trace's evaluation data. A logging failure here is caught and swallowed — it must
            never prevent the already-computed answer from being returned (principle: "if
            evaluation logging fails, normal chat must still work")."""
            total_latency_ms = int((time.perf_counter() - _start) * 1000)
            try:
                await EvaluationLogger.log_chat_trace(
                    db,
                    trace_id=trace_id,
                    session_id=session_id,
                    user_question=message,
                    final_answer=answer,
                    fallback_triggered=fallback_triggered,
                    fallback_reason=fallback_reason,
                    answer_status=status,
                    total_latency_ms=total_latency_ms,
                    retrieval_latency_ms=timings.get("retrieval"),
                    graph_latency_ms=timings.get("graph"),
                    acif_latency_ms=timings.get("acif"),
                    llm_latency_ms=timings.get("llm"),
                    output_verification_latency_ms=timings.get("gate5"),
                    model_used=(generation_usage or {}).get("model"),
                    input_tokens=(generation_usage or {}).get("prompt_tokens"),
                    output_tokens=(generation_usage or {}).get("completion_tokens"),
                    estimated_cost=(generation_usage or {}).get("cost_usd"),
                    error_message=error_message,
                    evaluation_mode=evaluation_mode,
                    participant_code=participant_code,
                    scenario_code=scenario_code,
                    retrieval_rows=retrieval_rows,
                    citation_rows=citation_rows,
                    gate_rows=gate_rows,
                    graph_consistency_rows=graph_consistency_rows,
                    normalized_question_override=(
                        analysis.normalized_question if analysis else None
                    ),
                    rewritten_queries=analysis.rewritten_queries if analysis else None,
                    detected_terms=analysis.detected_terms if analysis else None,
                    expanded_terms=analysis.expanded_terms if analysis else None,
                    intent=analysis.intent if analysis else None,
                    intent_confidence=analysis.intent_confidence if analysis else None,
                    clarification_used=status == "needs_clarification",
                )
            except Exception as e:
                logger.error(f"Evaluation logging failed for trace_id={trace_id}: {e}")

            return ChatResponse(
                answer=answer,
                status=status,
                session_id=session_id,
                sources=sources,
                attachments=attachments or [],
                created_at=datetime.utcnow(),
                trace_id=trace_id,
                latency_ms=total_latency_ms,
                clarification_question=clarification_question,
            )

        # Verify session exists
        session = await SessionService.get_session(db, session_id)
        if not session:
            raise SessionNotFoundError("Session not found")

        # Update last active time
        await SessionService.update_last_active(db, session_id)

        # Check consent
        has_consent = await ConsentService.has_consent(db, session_id)
        if not has_consent:
            return await _finalize(
                "Mohon berikan persetujuan (consent) terlebih dahulu sebelum melanjutkan.",
                "no_consent",
                [],
            )

        # Phase 19: Rate Limiting Check
        try:
            rate_limiter = await get_rate_limiter()

            # Check session-level rate limit
            session_ok = await rate_limiter.check_session_limit(str(session_id))
            if not session_ok:
                remaining = await rate_limiter.get_session_remaining(str(session_id))
                logger.warning(f"Session rate limit exceeded: {session_id}")
                return await _finalize(
                    "Anda mengirim permintaan terlalu cepat. Mohon tunggu sebentar sebelum mencoba lagi.",
                    "rate_limited",
                    [],
                )

            # Check global rate limit
            global_ok = await rate_limiter.check_global_limit()
            if not global_ok:
                logger.warning("Global rate limit exceeded")
                return await _finalize(
                    "Layanan sedang mengalami lonjakan permintaan yang tinggi. Silakan coba lagi sesaat lagi.",
                    "service_busy",
                    [],
                )

        except Exception as e:
            logger.error(f"Rate limiter check failed: {e}")
            # Continue on rate limiter error (don't block user)

        # ACIF Gate 1: Input Integrity Check
        #
        # `disabled_gates`/`ablation_disable_acif` intentionally do NOT gate real user traffic —
        # asserted above to only ever apply when `evaluation_mode=True` (the gold-QA evaluation
        # runner's N-gate ablation study), so a real /chat request always runs Gate 1. See
        # CLAUDE.md §4.4/§33.11: ACIF must never be bypassed for production answers.
        _gate_t0 = time.perf_counter()
        if gate1_disabled:
            gate1_result = ACIFGate1Result(
                decision=ACIFDecision.ACCEPT,
                score=0.0,
                risk_signals=[],
                reasoning="Gate 1 bypassed — N-gate ablation run (evaluation_mode only)",
            )
        else:
            gate1_result = await InputIntegrityChecker.check(message)
        gate1_latency_ms = int((time.perf_counter() - _gate_t0) * 1000)
        timings["acif"] = timings.get("acif", 0) + gate1_latency_ms

        gate_rows.append({
            "gate_number": 1,
            "gate_name": "Gate 1 - Input Intent Integrity Check",
            "gate_status": "bypassed" if gate1_disabled else ChatCoreService._gate1_status(gate1_result.decision),
            "risk_score": gate1_result.score,
            "risk_level": ChatCoreService._gate1_risk_level(gate1_result.score),
            "action_taken": (
                "Bypassed for N-gate ablation" if gate1_disabled
                else "Blocked request" if gate1_result.decision == ACIFDecision.REJECT
                else "Blocked request (out-of-domain topic)" if gate1_result.domain_violation
                else "Proceeded with caution" if gate1_result.decision == ACIFDecision.CAUTION
                else "Allowed"
            ),
            # Only the count of matched signals is stored — never the literal matched phrases
            # (CLAUDE.md ACIF logging rule: safe summaries only, no detection-wordlist leakage).
            "risk_flags": {"matched_signal_count": len(gate1_result.risk_signals)},
            "public_summary": (
                "Permintaan Anda tidak dapat diproses karena terindikasi melanggar kebijakan."
                if gate1_result.decision == ACIFDecision.REJECT
                else "Input Anda telah diperiksa dan aman untuk diproses."
            ),
            # `reasoning` is already a safe, formula-free summary (e.g. "Input contains 3 risk
            # signals exceeding reject threshold") — no raw phrase text or scoring weights.
            "admin_summary": gate1_result.reasoning,
            "latency_ms": gate1_latency_ms,
        })

        if gate1_result.decision == ACIFDecision.REJECT:
            # Log security event
            await ChatCoreService._log_security_event(
                db,
                session_id,
                "input_injection_detected",
                "critical",
                f"Blocked: {', '.join(gate1_result.risk_signals)}"
            )
            return await _finalize(
                "Permintaan Anda tidak dapat diproses. Silakan coba ajukan pertanyaan dengan kalimat yang berbeda.",
                "rejected_by_input_filter",
                [],
                fallback_triggered=True,
                fallback_reason="input_rejected_by_gate1",
            )

        # CLAUDE.md §12 domain validation: a topical out-of-domain question short-circuits
        # here — no retrieval, no OpenRouter call. Uses the same canonical refusal wording
        # as the LLM's own policy refusal (_OOD_REFUSAL_PHRASE) so the Evaluation Layer's
        # fallback-correctness metric treats both paths identically.
        if gate1_result.domain_violation:
            return await _finalize(
                ChatCoreService.OUT_OF_DOMAIN_RESPONSE,
                "out_of_domain",
                [],
                fallback_triggered=True,
                fallback_reason="domain_validation_gate1",
            )

        # Query Understanding Layer — runs strictly AFTER Gate 1 (which judged the
        # ORIGINAL input above) and only shapes retrieval. Conversation history is used
        # for follow-up resolution only under history_and_analytics consent.
        _qu_t0 = time.perf_counter()
        latest_consent = await ConsentService.get_latest_consent(db, session_id)
        history_allowed = bool(
            latest_consent and latest_consent.consent_value == "history_and_analytics"
        )
        qu_history = None
        if history_allowed:
            qu_history = await ChatCoreService._get_recent_history(db, session_id, limit=5)
        analysis = await QueryUnderstandingService.analyze(
            message, history=qu_history, history_allowed=history_allowed
        )
        timings["query_understanding"] = int((time.perf_counter() - _qu_t0) * 1000)

        # Store user message in chat_history
        user_turn_index = await ChatCoreService._get_next_turn_index(db, session_id)
        await ChatCoreService._store_message(
            db,
            session_id,
            user_turn_index,
            "user",
            message,
            metadata,
        )

        # Elliptical question with no resolvable topic — ask a clarification question
        # instead of guessing or hard-falling-back (grounding is preserved: nothing is
        # answered, no retrieval context is claimed).
        if analysis.needs_clarification and analysis.clarification_question:
            await ChatCoreService._store_message(
                db,
                session_id,
                user_turn_index + 1,
                "assistant",
                analysis.clarification_question,
            )
            return await _finalize(
                analysis.clarification_question,
                "needs_clarification",
                [],
                clarification_question=analysis.clarification_question,
            )

        # Phase 15: Retrieve from Vector RAG + GraphRAG (with caching)
        try:
            cache_service = await get_cache_service()
        except Exception as e:
            logger.warning(f"Cache service unavailable: {e}")
            cache_service = None

        # Graph retrieval first so the multi-query reranker can use graph support.
        # Called with the resolved question + expansions so an acronym like "spmb"
        # triggers the retriever's keyword branches via its expansion.
        _graph_t0 = time.perf_counter()
        if disable_graph_rag:
            graph_results = []
        else:
            graph_query = " ".join([analysis.resolved_question, *analysis.expanded_terms]).strip() or message
            graph_results = await GraphRetrieverService.retrieve_by_intent(graph_query)
        timings["graph"] = int((time.perf_counter() - _graph_t0) * 1000)

        # Log graph retrieval results alongside vector results (2026-07-23) — previously
        # retrieval_rows only ever logged vector_results (retrieval_source hardcoded "vector"
        # a few lines below), so the admin Retrieval evaluation tab/export never showed what
        # GraphRAG actually contributed even though it's used for reranking (multi_query_
        # retriever's graph_results= param), ACIF Gate 2/3 context, and the LLM prompt's
        # STRUCTURED GRAPH EVIDENCE section (all further down this method). `selected_for_context`
        # mirrors PromptBoundaryBuilder._build_graph_section's own `evidence[:5]` cap — the first
        # 5 results are what the LLM actually sees; anything past that is retrieved but unused.
        _GRAPH_EVIDENCE_LIMIT = 5
        for rank, g in enumerate(graph_results, start=1):
            entity_label = f"{g.get('entity_type')}: {g.get('entity_name')}"
            if g.get("relation"):
                entity_label = f"{g.get('related_to')} -{g['relation']}-> {g.get('entity_name')}"
                if g.get("program_studi"):
                    entity_label = f"{g['program_studi']} -TERSEDIA_PADA-> {entity_label}"
            retrieval_rows.append({
                "chunk_id": None,
                "document_id": None,
                "document_title": entity_label,
                "page_number": None,
                "chunk_type": "graph",
                "retrieval_source": "graph",
                "retrieval_rank": rank,
                "retrieval_score": None,
                "selected_for_context": rank <= _GRAPH_EVIDENCE_LIMIT,
                "rejected_reason": None if rank <= _GRAPH_EVIDENCE_LIMIT else "graph_evidence_limit",
                "metadata": g,
            })

        # Multi-query vector retrieval over all rewritten queries (per-query cache inside).
        _retrieval_t0 = time.perf_counter()
        retrieval_source = "vector"
        vector_results = await MultiQueryRetriever.retrieve(
            analysis, db, cache_service, graph_results=graph_results
        )
        timings["retrieval"] = int((time.perf_counter() - _retrieval_t0) * 1000)

        # Phase 16: ACIF Gate 2 - Context Integrity Scoring (with cache)
        _gate2_t0 = time.perf_counter()
        query_context = {
            "term_expansions": analysis.term_expansions,
            "detected_terms": analysis.detected_terms,
            "exact_term_matched": analysis.exact_term_matched,
            "graph_results_present": bool(graph_results),
            "graph_entities": [g.get("entity_name") for g in graph_results],
        }
        # Gate 2 scores are query-dependent — key the cache by chunk AND query.
        query_hash = hashlib.md5(analysis.resolved_question.encode()).hexdigest()[:12]
        scored_chunks = []
        for rank, result in enumerate(vector_results, start=1):
            chunk_id = result.get("chunk_id")

            if gate2_disabled:
                # Gate 2 bypassed for this ablation condition — every retrieved chunk is kept
                # unscored (see process_message's disabled_gates docstring).
                score_result = {"decision": "keep", "score": None}
            else:
                # Try to get cached score
                score_result = None
                if cache_service and chunk_id:
                    score_result = await cache_service.get_acif_score(chunk_id, query_hash=query_hash)

                # If not cached, compute score
                if not score_result:
                    score_result = await ContextIntegrityScorer.score_context(
                        result, analysis.resolved_question, query_context=query_context
                    )
                    # Cache the score
                    if cache_service and chunk_id:
                        await cache_service.set_acif_score(
                            chunk_id, score_result, query_hash=query_hash
                        )

            result_metadata = result.get("metadata", {}) or {}
            page = result_metadata.get("page")
            retrieval_rows.append({
                "chunk_id": chunk_id,
                "document_id": result_metadata.get("document_id"),
                "document_title": result_metadata.get("document_title"),
                "page_number": page if (page is not None and page >= 0) else None,
                "chunk_type": result_metadata.get("chunk_type", "text"),
                "retrieval_source": retrieval_source,
                "retrieval_rank": rank,
                "retrieval_score": result.get("similarity_score"),
                "selected_for_context": False,  # updated below if it survives to final context
                "rejected_reason": (
                    None if score_result["decision"] != "reject" else f"gate2:{score_result['decision']}"
                ),
                # `content` rides along inside `metadata` (only persisted when
                # EVALUATION_LOG_FULL_CONTEXT=true, per EvaluationLogger) so the gold-QA
                # runner's LLM judge (llm_judge.py) can reconstruct the exact context a chunk
                # contributed, without a separate schema change.
                "metadata": {**result_metadata, "content": result.get("content", "")},
            })

            if score_result["decision"] != "reject":
                scored_chunks.append((result, score_result))
        gate2_latency_ms = int((time.perf_counter() - _gate2_t0) * 1000)
        timings["acif"] += gate2_latency_ms

        gate2_rejected = len(vector_results) - len(scored_chunks)
        gate_rows.append({
            "gate_number": 2,
            "gate_name": "Gate 2 - Retrieval Context Integrity Scoring",
            "gate_status": "bypassed" if gate2_disabled else ("warn" if gate2_rejected else "pass"),
            "risk_score": None,
            "risk_level": "medium" if gate2_rejected else "low",
            "action_taken": (
                "Bypassed for N-gate ablation" if gate2_disabled
                else f"Kept {len(scored_chunks)} of {len(vector_results)} retrieved chunks; "
                f"rejected {gate2_rejected}."
            ),
            "risk_flags": None,
            "public_summary": "Konteks yang diambil telah diverifikasi sebelum digunakan.",
            "admin_summary": (
                f"Sistem memilih {len(scored_chunks)} chunk dan menolak {gate2_rejected} chunk "
                "karena tidak memenuhi ambang batas integritas konteks."
            ),
            "latency_ms": gate2_latency_ms,
        })

        # Phase 16: ACIF Gate 3 - Graph-Document Consistency
        _gate3_t0 = time.perf_counter()
        consistent_chunks = []
        for result, score in scored_chunks:
            if gate3_disabled:
                # Gate 3 bypassed for this ablation condition — no chunk is rejected on
                # graph-consistency grounds.
                consistency = {"decision": "bypassed"}
            else:
                consistency = await GraphDocumentConsistency.check_consistency(result, graph_results)
            if consistency["decision"] != "inconsistent_flag":
                consistent_chunks.append((result, score, consistency))
            else:
                chunk_id = result.get("chunk_id")
                for row in retrieval_rows:
                    if row["chunk_id"] == chunk_id:
                        row["rejected_reason"] = f"gate3:{consistency['decision']}"
                        break
        gate3_latency_ms = int((time.perf_counter() - _gate3_t0) * 1000)
        timings["acif"] += gate3_latency_ms

        gate3_rejected = len(scored_chunks) - len(consistent_chunks)
        gate_rows.append({
            "gate_number": 3,
            "gate_name": "Gate 3 - Graph-Document Consistency Check",
            "gate_status": "bypassed" if gate3_disabled else ("warn" if gate3_rejected else "pass"),
            "risk_score": None,
            "risk_level": "medium" if gate3_rejected else "low",
            "action_taken": (
                "Bypassed for N-gate ablation" if gate3_disabled
                else f"{len(consistent_chunks)} of {len(scored_chunks)} chunks passed graph "
                f"consistency check; {gate3_rejected} flagged inconsistent."
            ),
            "risk_flags": None,
            "public_summary": "Konteks telah dicocokkan dengan basis pengetahuan graf.",
            "admin_summary": (
                f"{len(consistent_chunks)} chunk konsisten dengan graph evidence, "
                f"{gate3_rejected} chunk ditandai tidak konsisten."
            ),
            "latency_ms": gate3_latency_ms,
        })

        # Graph-consistency detail rows — Gate 3 above scores per-chunk aggregate consistency,
        # not per-entity, so this is a best-effort per-entity view derived from the same
        # accepted-chunk set for the admin graph_consistency_logs page.
        if graph_results:
            accepted_text = " ".join(
                (r.get("content", "") or "").lower() for r, _, _ in consistent_chunks
            )
            for g in graph_results:
                entity_name = (g.get("entity_name") or "").lower()
                if entity_name and entity_name in accepted_text:
                    status = "supported"
                elif consistent_chunks:
                    status = "weakly_supported"
                else:
                    status = "unsupported"
                graph_consistency_rows.append({
                    "graph_entity": f"{g.get('entity_type', 'Unknown')}: {g.get('entity_name', '')}",
                    "graph_relation": g.get("relation"),
                    "supporting_document_id": None,
                    "supporting_chunk_id": None,
                    "consistency_status": status,
                    "notes": None,
                })

        # Build final context from approved chunks
        sources = []
        vector_chunks = []

        for result, score, consistency in consistent_chunks[:settings.max_context_chunks]:
            result_metadata = result.get("metadata", {})
            # Index metadata uses sentinel values (Chroma rejects None):
            # page=-1 means unknown, section="" means unknown.
            title = result_metadata.get("document_title") or result_metadata.get("document_id")
            page = result_metadata.get("page")
            if page is not None and page < 0:
                page = None
            section = result_metadata.get("section") or None

            sources.append(SourceReference(
                document_title=title,
                document_id=result_metadata.get("document_id"),
                section=section,
                page=page,
                chunk_id=result.get("chunk_id"),
            ))

            # Convert to VectorChunk for prompt builder
            vector_chunks.append(VectorChunk(
                content=result.get("content", ""),
                original_text=result.get("original_text"),
                source_document=title or "Unknown",
                page=page,
                chunk_id=result.get("chunk_id"),
                approval_status="approved",
            ))

            chunk_id_val = result.get("chunk_id")
            for row in retrieval_rows:
                if row["chunk_id"] == chunk_id_val:
                    row["selected_for_context"] = True
                    break

        # If no approved context, return fallback. Distinguish "retrieval found nothing"
        # from "everything retrieved was rejected by Gates 2/3" for admin diagnostics.
        if not vector_chunks:
            specific_reason = "no_context" if not vector_results else "insufficient_context"
            fallback_answer = FallbackResponse.get_fallback(specific_reason)

            assistant_turn_index = user_turn_index + 1
            await ChatCoreService._store_message(
                db,
                session_id,
                assistant_turn_index,
                "assistant",
                fallback_answer,
            )

            return await _finalize(
                fallback_answer,
                "insufficient_context",
                [],
                fallback_triggered=True,
                fallback_reason=f"no_approved_context_survived_acif_gates_2_3:{specific_reason}",
            )

        # ACIF Gate 4: Prompt Boundary Builder
        try:
            # Get recent conversation history
            history = await ChatCoreService._get_recent_history(db, session_id, limit=5)

            # Convert raw graph_results dicts ({"entity_type", "entity_name"})
            # into the typed GraphEvidence model the prompt builder expects.
            graph_evidence = [
                GraphEvidence(
                    entity_type=g.get("entity_type", "Unknown"),
                    entity_name=g.get("entity_name", ""),
                )
                for g in (graph_results or [])
            ]

            # Build bounded prompt (or the naive ablation-only baseline — see
            # process_message's disabled_gates docstring)
            _gate4_t0 = time.perf_counter()
            if gate4_disabled:
                prompt_result = PromptBoundaryBuilder.build_naive(
                    user_message=message,
                    vector_chunks=vector_chunks,
                    max_context_chunks=settings.max_context_chunks,
                )
            else:
                prompt_result = PromptBoundaryBuilder.build(
                    user_message=message,
                    vector_chunks=vector_chunks,
                    graph_evidence=graph_evidence,
                    conversation_history=history,
                    max_tokens=settings.acif_max_prompt_input_tokens,
                    max_context_chunks=settings.max_context_chunks,
                )
            gate4_latency_ms = int((time.perf_counter() - _gate4_t0) * 1000)
            timings["acif"] += gate4_latency_ms

            gate_rows.append({
                "gate_number": 4,
                "gate_name": "Gate 4 - Prompt Boundary Construction",
                "gate_status": "bypassed" if gate4_disabled else "pass",
                "risk_score": None,
                "risk_level": "low",
                "action_taken": (
                    "Bypassed for N-gate ablation — naive prompt built"
                    if gate4_disabled
                    else "Built bounded prompt separating policy, context, and user input."
                ),
                "risk_flags": None,
                "public_summary": "Prompt disusun dengan batas yang aman antara kebijakan sistem dan input pengguna.",
                # Structural summary only — never final_prompt/system_policy/vector_context.
                "admin_summary": (
                    f"Prompt boundary applied: policy/context/user-input separated. "
                    f"Token count: {prompt_result.token_count}. Sources used: {len(prompt_result.context_sources)}."
                ),
                "latency_ms": gate4_latency_ms,
            })

            logger.debug(
                f"Prompt built. Token count: {prompt_result.token_count}, "
                f"Sources: {len(prompt_result.context_sources)}"
            )

        except ValueError as e:
            logger.error(f"Prompt boundary building failed: {e}")
            gate_rows.append({
                "gate_number": 4,
                "gate_name": "Gate 4 - Prompt Boundary Construction",
                "gate_status": "error",
                "risk_score": None,
                "risk_level": "high",
                "action_taken": "Request rejected — prompt could not be safely constructed.",
                "risk_flags": None,
                "public_summary": "Permintaan tidak dapat diproses saat ini.",
                "admin_summary": f"Prompt boundary construction failed: {e}",
                "latency_ms": None,
            })
            return await _finalize(
                "Permintaan Anda tidak dapat diproses saat ini.",
                "error",
                [],
                error_message=str(e),
            )

        # Check OpenRouter budget
        try:
            budget_ok = await check_openrouter_budget(db)
            if not budget_ok:
                logger.warning("OpenRouter budget exceeded")
                return await _finalize(
                    "Layanan sementara tidak tersedia karena keterbatasan sumber daya.",
                    "service_unavailable",
                    [],
                )
        except Exception as e:
            logger.error(f"Budget check failed: {e}")

        # OpenRouter LLM Call (with fallback support)
        try:
            _llm_t0 = time.perf_counter()
            generation = await OpenRouterClient.generate_with_fallback(
                prompt=prompt_result.final_prompt,
                db=db,
                max_tokens=settings.llm_max_tokens,
                temperature=settings.llm_temperature,
            )
            timings["llm"] = int((time.perf_counter() - _llm_t0) * 1000)
            answer = generation.text
            generation_usage = {
                "model": generation.model,
                "prompt_tokens": generation.prompt_tokens,
                "completion_tokens": generation.completion_tokens,
                "cost_usd": generation.cost_usd,
            }

            logger.info(f"LLM generated answer for session {session_id}")

        except OpenRouterError as e:
            logger.error(f"OpenRouter LLM call failed: {e}")
            return await _finalize(
                FallbackResponse.get_fallback("llm_error"),
                "service_unavailable",
                [],
                error_message=str(e),
            )

        # ACIF Gate 5: Output Claim Verification (skipped entirely when gate 5 is disabled for
        # this ablation condition — the LLM's raw answer is returned with no claim verification,
        # no fallback-on-unsupported-claim, and no regeneration attempt)
        if gate5_disabled:
            fallback_status = "answered"
            gate_rows.append({
                "gate_number": 5,
                "gate_name": "Gate 5 - Output Claim Verification",
                "gate_status": "bypassed",
                "risk_score": None,
                "risk_level": "low",
                "action_taken": "Bypassed for N-gate ablation",
                "risk_flags": None,
                "public_summary": "Jawaban tidak diverifikasi (mode ablasi tanpa ACIF).",
                "admin_summary": "Gate 5 bypassed — N-gate ablation run (evaluation_mode only).",
                "latency_ms": 0,
            })
        else:
            try:
                # Convert vector chunks to dict format for verifier
                chunk_dicts = [
                    {
                        "content": chunk.content,
                        "original_text": chunk.original_text,
                        "approval_status": chunk.approval_status,
                    }
                    for chunk in vector_chunks
                ]

                _gate5_t0 = time.perf_counter()
                verification_result = await OutputClaimVerifier.verify(
                    answer=answer,
                    approved_chunks=chunk_dicts,
                    graph_evidence=graph_results if graph_results else [],
                    strict_mode=True,
                    db=db,
                    use_llm=True,
                )
                timings["gate5"] = int((time.perf_counter() - _gate5_t0) * 1000)

                logger.info(
                    f"Output verification: {verification_result.supported_claims}/"
                    f"{verification_result.total_claims} claims supported, "
                    f"confidence: {verification_result.overall_confidence:.1%}"
                )

                # CLAUDE.md §11.6: a strongly-grounded answer with a few unsupported critical
                # claims gets a corrective regeneration (drop the failing claims) and a full
                # re-verification, instead of discarding 90%+ verified content outright. Up to
                # 2 attempts (raised from 1, 2026-07-23): both answer generation and claim
                # verification are separate LLM calls, each with its own sampling variance, so a
                # single retry sometimes lands on a fresh borderline claim rather than resolving
                # the original one — live production traces showed a mostly-verified (~91%
                # confidence) answer still falling back after exactly one regeneration attempt.
                # A regeneration that still fails after all attempts falls back exactly as
                # before. Each attempt is a real, billed OpenRouter call — bounded at 2 to keep
                # worst-case latency/cost for this already-rare path (~4% of traffic) in check.
                regenerated = False
                _MAX_REGEN_ATTEMPTS = 2
                for _regen_attempt in range(1, _MAX_REGEN_ATTEMPTS + 1):
                    if not OutputClaimVerifier.should_attempt_regeneration(verification_result):
                        break
                    failing_texts = OutputClaimVerifier.unsupported_critical_texts(verification_result)
                    logger.info(
                        f"Gate 5 regeneration attempt {_regen_attempt}/{_MAX_REGEN_ATTEMPTS}: "
                        f"{len(failing_texts)} unsupported critical claim(s) at "
                        f"{verification_result.overall_confidence:.0%} confidence"
                    )
                    # 2026-07-23 temporary debug logging: log the actual claim text (not just
                    # count) so a persistently-failing claim across multiple regeneration
                    # attempts can be diagnosed from production logs instead of only reproduced
                    # locally. Safe to log: this is the LLM's OWN generated answer text, not
                    # user input, retrieved-document content, or a secret.
                    for _ft in failing_texts:
                        logger.warning(f"Gate 5 unsupported claim text: {_ft!r}")
                    try:
                        _regen_t0 = time.perf_counter()
                        regen = await OpenRouterClient.generate_with_fallback(
                            prompt=OutputClaimVerifier.build_regeneration_prompt(
                                prompt_result.final_prompt, failing_texts
                            ),
                            db=db,
                            max_tokens=settings.llm_max_tokens,
                            temperature=settings.llm_temperature,
                        )
                        reverification = await OutputClaimVerifier.verify(
                            answer=regen.text,
                            approved_chunks=chunk_dicts,
                            graph_evidence=graph_results if graph_results else [],
                            strict_mode=True,
                            db=db,
                            use_llm=True,
                        )
                        timings["gate5"] += int((time.perf_counter() - _regen_t0) * 1000)
                        answer = regen.text
                        verification_result = reverification
                        generation_usage = {
                            "model": regen.model,
                            "prompt_tokens": (generation_usage or {}).get("prompt_tokens", 0)
                            + (regen.prompt_tokens or 0),
                            "completion_tokens": (generation_usage or {}).get("completion_tokens", 0)
                            + (regen.completion_tokens or 0),
                            "cost_usd": ((generation_usage or {}).get("cost_usd") or 0)
                            + (regen.cost_usd or 0),
                        }
                        if not reverification.should_enforce_fallback:
                            regenerated = True
                            logger.info(
                                f"Gate 5 regeneration verified successfully on attempt {_regen_attempt}"
                            )
                            break
                        else:
                            logger.warning(
                                f"Gate 5 regeneration attempt {_regen_attempt} still unverified "
                                f"({reverification.fallback_reason})"
                            )
                    except Exception as regen_exc:
                        # Regeneration is best-effort — any failure keeps the last verification
                        # result (answer/verification_result untouched by this attempt) and
                        # stops retrying rather than looping on a persistently failing call.
                        logger.warning(f"Gate 5 regeneration attempt {_regen_attempt} failed: {regen_exc}")
                        break

                # Enforce fallback if verification fails
                if verification_result.should_enforce_fallback:
                    logger.warning(
                        f"Fallback enforced: {verification_result.fallback_reason}"
                    )
                    answer = FallbackResponse.get_fallback(verification_result.fallback_reason)
                    fallback_status = "fallback_enforced"
                else:
                    fallback_status = "verified"

                gate_rows.append({
                    "gate_number": 5,
                    "gate_name": "Gate 5 - Output Claim Verification",
                    "gate_status": "fallback" if verification_result.should_enforce_fallback else "pass",
                    "risk_score": round(1 - verification_result.overall_confidence, 2),
                    "risk_level": "high" if verification_result.should_enforce_fallback else "low",
                    "action_taken": (
                        verification_result.fallback_reason if verification_result.should_enforce_fallback
                        else "Answer verified against approved context."
                    ),
                    "risk_flags": {
                        "unsupported_claims": verification_result.unsupported_claims,
                        # Admin-only diagnostic (acif_trace_logs.risk_flags): which claims failed,
                        # so systematic verifier misfires are visible without a code change.
                        "unsupported_claim_texts": [
                            detail.claim.text[:180]
                            for detail in verification_result.claim_details
                            if not detail.is_supported
                        ][:6],
                        "regenerated": regenerated,
                    },
                    "public_summary": (
                        "Jawaban tidak dapat diverifikasi sepenuhnya sehingga digantikan dengan pesan aman."
                        if verification_result.should_enforce_fallback
                        else "Jawaban telah diverifikasi terhadap sumber resmi."
                    ),
                    "admin_summary": (
                        f"{verification_result.supported_claims}/{verification_result.total_claims} klaim "
                        f"didukung sumber (confidence {verification_result.overall_confidence:.0%})."
                        + (" Jawaban hasil satu kali regenerasi korektif (§11.6)." if regenerated else "")
                    ),
                    "latency_ms": timings.get("gate5"),
                })

            except Exception as e:
                logger.error(f"Output claim verification failed: {e}")
                # On verification error, fall back to safe response
                logger.info(f"Fallback enforced: verification error: {e}")
                answer = FallbackResponse.get_fallback("llm_error")
                fallback_status = "verification_error"
                gate_rows.append({
                    "gate_number": 5,
                    "gate_name": "Gate 5 - Output Claim Verification",
                    "gate_status": "error",
                    "risk_score": None,
                    "risk_level": "high",
                    "action_taken": "Verification failed; safe fallback returned.",
                    "risk_flags": None,
                    "public_summary": "Jawaban tidak dapat diverifikasi; pesan aman diberikan.",
                    "admin_summary": f"Output verification raised an error: {e}",
                    "latency_ms": None,
                })

        # Only cite sources the final answer actually drew on -- a chunk surviving retrieval
        # and ACIF Gates 2/3 doesn't mean the LLM's answer ended up relying on it, and if
        # verification replaced the answer with a fallback message, none of them did.
        # Overlap is checked against BOTH the summary (content) and the verbatim
        # original_text — the prompt includes both, and answers grounded in the original
        # text were losing their citations when only the summary was compared.
        if fallback_status in ("fallback_enforced", "verification_error"):
            # The answer WAS replaced by a fallback message — citing sources under it
            # would imply the refusal text is grounded in those documents.
            relevant_sources = []
        else:
            relevant_sources = [
                source
                for source, chunk in zip(sources, vector_chunks)
                if OutputClaimVerifier.is_source_cited_in_answer(answer, source.document_title)
                or any(
                    OutputClaimVerifier.is_content_relevant_to_answer(answer, text)
                    for text in (chunk.content, chunk.original_text)
                    if text
                )
            ]

        for source in relevant_sources:
            citation_rows.append({
                "document_id": source.document_id,
                "chunk_id": source.chunk_id,
                "document_title": source.document_title,
                "page_number": source.page,
                "citation_type": "text",
                "is_visual_source": False,
                "is_valid": True,
                "validation_notes": None,
            })

        # Store assistant response with sources
        assistant_turn_index = user_turn_index + 1
        await ChatCoreService._store_message(
            db,
            session_id,
            assistant_turn_index,
            "assistant",
            answer,
        )

        final_status = fallback_status if 'fallback_status' in locals() else "answered"

        # The LLM itself can issue a policy refusal (out-of-domain question) or a
        # not-in-sources statement, per the prompt rules in PromptBoundaryBuilder. Those
        # answers contain no verifiable claims, so Gate 5 passes them as "verified" — but
        # CLAUDE.md §8.3 defines distinct statuses for these outcomes, and the Evaluation
        # Layer's fallback-correctness metric needs them to recognize a correct safe
        # non-answer (found via gold-QA run test_run_2: Q004/Q008 were correct refusals
        # scored as failures because their status stayed "verified").
        llm_refusal_status = ChatCoreService._detect_llm_refusal_status(answer)
        llm_refusal_reason = None
        if final_status == "verified" and llm_refusal_status:
            final_status = llm_refusal_status
            llm_refusal_reason = (
                "llm_declined_out_of_domain" if llm_refusal_status == "out_of_domain"
                else "llm_stated_not_in_sources"
            )

        # Attachment lookup mirrors AnswerComposerAgent.lookup_attachments (the /api/chat/
        # agentic path) so both endpoints offer identical downloadable-form behavior for the
        # same cited documents (CLAUDE.md §8 parity requirement). Skipped when the answer was
        # replaced by a fallback message — same reasoning as relevant_sources above.
        attachments = (
            await AnswerComposerAgent.lookup_attachments(
                db, [s.document_id for s in relevant_sources if s.document_id]
            )
            if relevant_sources
            else []
        )

        return await _finalize(
            answer,
            final_status,
            relevant_sources,
            fallback_triggered=final_status in (
                "fallback_enforced", "verification_error", "out_of_domain", "insufficient_context",
            ),
            fallback_reason=(
                llm_refusal_reason
                if llm_refusal_reason
                else verification_result.fallback_reason
                if 'verification_result' in locals() and verification_result.should_enforce_fallback
                else None
            ),
            attachments=attachments,
        )

    # Sentinel phrases the prompt rules instruct the LLM to use verbatim — see
    # PromptBoundaryBuilder.SYSTEM_POLICY rule 2 and DOMAIN_BOUNDARY's out-of-domain response.
    _OOD_REFUSAL_PHRASE = "hanya melayani informasi resmi kampus poltekkes kemenkes yogyakarta"
    _NOT_IN_SOURCES_PHRASE = "tidak tersedia dalam sumber resmi"

    # Canonical out-of-domain response for Gate 1's pre-retrieval domain validation.
    # Must contain _OOD_REFUSAL_PHRASE so _detect_llm_refusal_status and the Evaluation
    # Layer classify both the gate path and the LLM-refusal path the same way.
    OUT_OF_DOMAIN_RESPONSE = (
        "Asisten virtual ini hanya melayani informasi resmi kampus Poltekkes Kemenkes "
        "Yogyakarta, seperti SPMB, layanan akademik, dan layanan administrasi. "
        "Saya tidak dapat menjawab pertanyaan di luar cakupan tersebut."
    )

    @staticmethod
    def _detect_llm_refusal_status(answer: str) -> str | None:
        """Detect whether the LLM's answer is itself a policy refusal, mapping it to the
        CLAUDE.md §8.3 status it represents. Returns None for normal answers.

        The out-of-domain template is specific enough to match anywhere; the "not available
        in sources" phrasing can legitimately appear inside a longer partial answer (e.g.
        "X is A; Y is not available in the loaded sources"), so it only counts as a full
        refusal when the answer is short and leads with it."""
        lowered = answer.lower()
        if ChatCoreService._OOD_REFUSAL_PHRASE in lowered:
            return "out_of_domain"
        if (
            ChatCoreService._NOT_IN_SOURCES_PHRASE in lowered[:200]
            and len(answer) < 400
        ):
            return "insufficient_context"
        return None

    @staticmethod
    def _gate1_status(decision: ACIFDecision) -> str:
        """Map Gate 1's ACIFDecision to the acif_trace_logs gate_status vocabulary."""
        if decision == ACIFDecision.REJECT:
            return "block"
        if decision == ACIFDecision.CAUTION:
            return "warn"
        return "pass"

    @staticmethod
    def _gate1_risk_level(score: float) -> str:
        """Descriptive-only risk level bucket for the admin UI — purely categorical, does not
        duplicate or replace the actual accept/caution/reject decision Gate 1 already made."""
        if score >= settings.acif_input_reject_threshold:
            return "critical"
        if score >= settings.acif_input_caution_threshold:
            return "medium"
        return "low"

    @staticmethod
    async def _get_next_turn_index(db: AsyncSession, session_id: UUID) -> int:
        """Get next turn index for a session."""
        from sqlalchemy import select, func
        stmt = (
            select(func.max(ChatHistory.turn_index))
            .where(ChatHistory.session_id == session_id)
        )
        result = await db.execute(stmt)
        max_index = result.scalar()
        return (max_index or -1) + 1

    @staticmethod
    async def _store_message(
        db: AsyncSession,
        session_id: UUID,
        turn_index: int,
        role: str,
        message: str,
        metadata: MessageMetadata | None = None,
    ) -> None:
        """Store a message in chat history."""
        chat_entry = ChatHistory(
            session_id=session_id,
            turn_index=turn_index,
            role=role,
            message=message,
            metadata_json=metadata.model_dump() if metadata else None,
        )
        db.add(chat_entry)
        await db.commit()

    @staticmethod
    async def _log_security_event(
        db: AsyncSession,
        session_id: UUID,
        event_type: str,
        severity: str,
        message: str,
    ) -> None:
        """Log security event."""
        event = SecurityEvent(
            session_id=session_id,
            event_type=event_type,
            severity=severity,
            message=message,
        )
        db.add(event)
        await db.commit()

    @staticmethod
    async def _get_recent_history(
        db: AsyncSession,
        session_id: UUID,
        limit: int = 5,
    ) -> list[dict]:
        """Get recent chat history for context."""
        from sqlalchemy import select, desc

        stmt = (
            select(ChatHistory)
            .where(ChatHistory.session_id == session_id)
            .order_by(desc(ChatHistory.turn_index))
            .limit(limit)
        )

        result = await db.execute(stmt)
        turns = result.scalars().all()

        # Reverse to get chronological order
        history = [
            {
                "role": turn.role,
                "message": turn.message,
                "timestamp": turn.created_at,
            }
            for turn in reversed(turns)
        ]

        return history
