"""OrchestratorAgent (CLAUDE.md §11A.1) — entry point for POST /api/chat/agentic.

Runs the same session/consent/rate-limit checks ChatCoreService.process_message already does
(reused, not duplicated), then dispatches QueryUnderstandingAgent -> RetrievalAgent +
GraphReasoningAgent -> ACIFAgent -> AnswerComposerAgent. POST /chat (chat_core.py) is untouched —
this is an additive parallel path with identical ACIF/grounding/citation guarantees.
"""
import logging
from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.acif_agent import ACIFAgent
from app.agents.answer_composer_agent import AnswerComposerAgent
from app.agents.graph_reasoning_agent import GraphReasoningAgent
from app.agents.query_understanding_agent import QueryUnderstandingAgent
from app.agents.retrieval_agent import RetrievalAgent
from app.core.errors import SessionNotFoundError
from app.schemas.chat import AttachmentReference, ChatResponse, MessageMetadata, SourceReference
from app.services.acif.output_claim_verifier import FallbackResponse
from app.services.chat_core import ChatCoreService
from app.services.rate_limiter_service import get_rate_limiter
from app.services.redis_cache_service import get_cache_service
from app.services.session_service import ConsentService, SessionService

logger = logging.getLogger(__name__)


class OrchestratorAgent:
    """Dispatches the chat-time agent sequence and merges their results."""

    name = "OrchestratorAgent"

    @staticmethod
    async def handle_chat_request(
        db: AsyncSession,
        session_id: UUID,
        message: str,
        metadata: MessageMetadata | None = None,
    ) -> ChatResponse:
        session = await SessionService.get_session(db, session_id)
        if not session:
            raise SessionNotFoundError("Session not found")
        await SessionService.update_last_active(db, session_id)

        if not await ConsentService.has_consent(db, session_id):
            return OrchestratorAgent._response(
                "Mohon berikan persetujuan (consent) terlebih dahulu sebelum melanjutkan.",
                "no_consent", session_id,
            )

        rate_limiter = await get_rate_limiter()
        try:
            if not await rate_limiter.check_session_limit(str(session_id)):
                return OrchestratorAgent._response(
                    "Anda mengirim permintaan terlalu cepat. Mohon tunggu sebentar sebelum mencoba lagi.",
                    "rate_limited", session_id,
                )
            if not await rate_limiter.check_global_limit():
                return OrchestratorAgent._response(
                    "Layanan sedang mengalami lonjakan permintaan yang tinggi. Silakan coba lagi sesaat lagi.",
                    "service_busy", session_id,
                )
        except Exception as exc:
            logger.error(f"Rate limiter check failed: {exc}")

        # History for follow-up resolution only under history_and_analytics consent
        # (same rule as chat_core).
        latest_consent = await ConsentService.get_latest_consent(db, session_id)
        history_allowed = bool(
            latest_consent and latest_consent.consent_value == "history_and_analytics"
        )
        qu_history = None
        if history_allowed:
            qu_history = await ChatCoreService._get_recent_history(db, session_id, limit=5)

        user_turn_index = await ChatCoreService._get_next_turn_index(db, session_id)
        await ChatCoreService._store_message(db, session_id, user_turn_index, "user", message, metadata)

        # 1. QueryUnderstandingAgent (wraps the shared Query Understanding Layer)
        qu_result = await QueryUnderstandingAgent().execute(
            {"message": message, "history": qu_history, "history_allowed": history_allowed},
            db=db, task_type="chat",
        )
        query_info = qu_result.output or {}

        if query_info.get("risk_level") == "high":
            await ChatCoreService._log_security_event(
                db, session_id, "input_injection_detected", "critical",
                f"Blocked: {', '.join(query_info.get('risk_signals', []))}",
            )

        normalized_query = query_info.get("normalized_query", message)
        analysis_data = query_info.get("analysis") or {}

        # Elliptical question without a resolvable topic — clarification, same as /chat.
        # Only when risk is low: a risky input must still reach ACIFAgent's Gate 1 below.
        if (
            query_info.get("needs_clarification")
            and query_info.get("clarification_question")
            and query_info.get("risk_level") == "low"
        ):
            clarification = query_info["clarification_question"]
            await ChatCoreService._store_message(
                db, session_id, user_turn_index + 1, "assistant", clarification
            )
            return OrchestratorAgent._response(
                clarification, "needs_clarification", session_id,
                clarification_question=clarification,
            )

        try:
            cache_service = await get_cache_service()
        except Exception as exc:
            logger.warning(f"Cache service unavailable: {exc}")
            cache_service = None

        # 2. GraphReasoningAgent first (multi-query reranker uses graph support),
        # queried with the resolved question + expansions so acronyms trigger it.
        resolved_query = analysis_data.get("resolved_question") or normalized_query
        expanded_terms = analysis_data.get("expanded_terms") or []
        graph_query = " ".join([resolved_query, *expanded_terms]).strip() or normalized_query
        graph_result = await GraphReasoningAgent().execute({"intent": graph_query}, db=db, task_type="chat")
        graph_info = graph_result.output or {}
        graph_results = graph_info.get("graph_results", [])

        # 3. RetrievalAgent — multi-query merge+rerank (per-query caching inside).
        retrieval_result = await RetrievalAgent().execute(
            {
                "query": resolved_query,
                "db": db,
                "analysis": analysis_data or None,
                "cache_service": cache_service,
                "graph_results": graph_results,
            },
            db=db, task_type="chat",
        )
        vector_results = (retrieval_result.output or {}).get("raw_results", [])

        # 3. ACIFAgent (Gates 1-3; Gate 1 already ran conceptually via QueryUnderstandingAgent's
        # risk detection, but ACIFAgent re-runs the authoritative InputIntegrityChecker.check()
        # itself so both /chat and /api/chat/agentic share one enforcement point.)
        acif_result = await ACIFAgent().execute(
            {
                "message": message,
                "vector_results": vector_results,
                "graph_results": graph_results,
                "topic": query_info.get("topik"),
                "risk_level": query_info.get("risk_level", "low"),
                "analysis": analysis_data,
                "db": db,
            },
            db=db,
            task_type="chat",
        )
        acif = acif_result.output or {}

        if acif.get("gate1_rejected"):
            return OrchestratorAgent._response(
                "Permintaan Anda tidak dapat diproses. Silakan coba ajukan pertanyaan dengan kalimat yang berbeda.",
                "rejected_by_input_filter", session_id,
            )

        if acif.get("domain_violation"):
            return OrchestratorAgent._response(
                ChatCoreService.OUT_OF_DOMAIN_RESPONSE,
                "out_of_domain", session_id,
            )

        if acif.get("fallback_required"):
            fallback_answer = FallbackResponse.FALLBACK_MESSAGE
            await ChatCoreService._store_message(db, session_id, user_turn_index + 1, "assistant", fallback_answer)
            return OrchestratorAgent._response(fallback_answer, "insufficient_context", session_id)

        # 4. AnswerComposerAgent (Gates 4-5 + LLM call + citations)
        history = await ChatCoreService._get_recent_history(db, session_id, limit=5)
        composer_result = await AnswerComposerAgent().execute(
            {
                "db": db,
                "message": message,
                "valid_chunks": acif.get("valid_chunks", []),
                "graph_results": graph_results,
                "conversation_history": history,
            },
            db=db,
            task_type="chat",
        )
        composed = composer_result.output or {}
        answer = composed.get("answer", "Permintaan Anda tidak dapat diproses saat ini.")
        status = composed.get("status", "error")

        await ChatCoreService._store_message(db, session_id, user_turn_index + 1, "assistant", answer)

        sources = [SourceReference(**s) for s in composed.get("sources", [])]
        attachments = [AttachmentReference(**a) for a in composed.get("attachments", [])]
        return ChatResponse(
            answer=answer,
            status=status,
            session_id=session_id,
            sources=sources,
            attachments=attachments,
            created_at=datetime.utcnow(),
        )

    @staticmethod
    def _response(
        answer: str,
        status: str,
        session_id: UUID,
        clarification_question: str | None = None,
    ) -> ChatResponse:
        return ChatResponse(
            answer=answer, status=status, session_id=session_id, sources=[],
            created_at=datetime.utcnow(), clarification_question=clarification_question,
        )
