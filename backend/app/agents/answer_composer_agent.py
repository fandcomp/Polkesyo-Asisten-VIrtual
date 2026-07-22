"""AnswerComposerAgent (CLAUDE.md §11A.1) — Gate 4 prompt build, LLM call, Gate 5 verification.

Wraps PromptBoundaryBuilder + OpenRouterClient + OutputClaimVerifier + citation assembly. Runs
Gates 4/5 (rather than ACIFAgent) because they need the LLM call sandwiched between them.
"""
from sqlalchemy import select

from app.agents.base_agent import BaseAgent
from app.core.config import settings
from app.db.models import DocumentFormExtract
from app.schemas.chat import AttachmentReference, SourceReference
from app.services.acif.output_claim_verifier import FallbackResponse, OutputClaimVerifier
from app.services.acif.prompt_boundary_builder import GraphEvidence, PromptBoundaryBuilder, VectorChunk
from app.services.openrouter_client import OpenRouterClient, OpenRouterError, check_openrouter_budget


class AnswerComposerAgent(BaseAgent):
    name = "AnswerComposerAgent"

    async def _run(self, input_data: dict) -> dict:
        db = input_data.get("db")
        message: str = input_data["message"]
        valid_chunks: list[dict] = input_data.get("valid_chunks") or []
        graph_results: list[dict] = input_data.get("graph_results") or []
        conversation_history: list[dict] | None = input_data.get("conversation_history")

        if not valid_chunks:
            fallback_answer = FallbackResponse.get_fallback("No valid official context.")
            return {
                "answer": fallback_answer,
                "status": "insufficient_context",
                "sources": [],
            }

        sources, vector_chunks = self._build_sources_and_chunks(valid_chunks)
        graph_evidence = [
            GraphEvidence(entity_type=g.get("entity_type", "Unknown"), entity_name=g.get("entity_name", ""))
            for g in graph_results
        ]

        try:
            prompt_result = PromptBoundaryBuilder.build(
                user_message=message,
                vector_chunks=vector_chunks,
                graph_evidence=graph_evidence,
                conversation_history=conversation_history,
                max_tokens=settings.acif_max_prompt_input_tokens,
                max_context_chunks=settings.max_context_chunks,
            )
        except ValueError as exc:
            return {
                "answer": "Permintaan Anda tidak dapat diproses saat ini.",
                "status": "error",
                "sources": [],
                "error": str(exc),
            }

        if db is not None:
            budget_ok = await check_openrouter_budget(db)
            if not budget_ok:
                return {
                    "answer": "Layanan sementara tidak tersedia karena keterbatasan sumber daya.",
                    "status": "service_unavailable",
                    "sources": [],
                }

        try:
            generation = await OpenRouterClient.generate_with_fallback(
                prompt=prompt_result.final_prompt,
                db=db,
                max_tokens=settings.llm_max_tokens,
                temperature=settings.llm_temperature,
            )
            answer = generation.text
        except OpenRouterError as exc:
            return {
                "answer": "Asisten virtual sementara tidak tersedia. Silakan coba lagi sesaat lagi.",
                "status": "service_unavailable",
                "sources": [],
                "error": str(exc),
            }

        # Gate 5: Output Claim Verification
        chunk_dicts = [
            {"content": c.content, "original_text": c.original_text, "approval_status": c.approval_status}
            for c in vector_chunks
        ]
        verification = await OutputClaimVerifier.verify(
            answer=answer,
            approved_chunks=chunk_dicts,
            graph_evidence=graph_results,
            strict_mode=True,
            db=db,
            use_llm=True,
        )

        # CLAUDE.md §11.6 corrective regeneration — mirrors chat_core.py so both endpoints
        # keep identical Gate 5 behavior (§11A parity requirement). One attempt only; a
        # regeneration that still fails verification falls back exactly as before.
        if OutputClaimVerifier.should_attempt_regeneration(verification):
            try:
                regen = await OpenRouterClient.generate_with_fallback(
                    prompt=OutputClaimVerifier.build_regeneration_prompt(
                        prompt_result.final_prompt,
                        OutputClaimVerifier.unsupported_critical_texts(verification),
                    ),
                    db=db,
                    max_tokens=settings.llm_max_tokens,
                    temperature=settings.llm_temperature,
                )
                reverification = await OutputClaimVerifier.verify(
                    answer=regen.text,
                    approved_chunks=chunk_dicts,
                    graph_evidence=graph_results,
                    strict_mode=True,
                    db=db,
                    use_llm=True,
                )
                if not reverification.should_enforce_fallback:
                    answer = regen.text
                    verification = reverification
            except Exception:
                # Best-effort: keep the original (fallback-enforcing) verification.
                pass

        if verification.should_enforce_fallback:
            answer = FallbackResponse.get_fallback(verification.fallback_reason)
            status = "fallback_enforced"
        else:
            status = "verified"

        # Only cite sources the final answer actually drew on -- a chunk surviving upstream
        # filtering doesn't mean the LLM's answer ended up relying on it, and if verification
        # replaced the answer with a fallback message, none of them did.
        relevant_sources = [
            source
            for source, chunk in zip(sources, vector_chunks)
            if OutputClaimVerifier.is_source_cited_in_answer(answer, source.document_title)
            or OutputClaimVerifier.is_content_relevant_to_answer(answer, chunk.content)
        ]

        attachments = await self.lookup_attachments(
            db, [s.document_id for s in relevant_sources if s.document_id]
        )

        return {
            "answer": answer,
            "status": status,
            "sources": [s.model_dump() for s in relevant_sources],
            "attachments": [a.model_dump() for a in attachments],
            "verification": {
                "total_claims": verification.total_claims,
                "supported_claims": verification.supported_claims,
                "overall_confidence": verification.overall_confidence,
            },
        }

    @staticmethod
    async def lookup_attachments(db, document_ids: list[str]) -> list[AttachmentReference]:
        """Look up admin-approved (`status == "active"`) form/attachment extracts for the
        same document_ids already being cited in `sources`, so the chat response can offer a
        downloadable form alongside its text citations (structure-aware document extraction
        plan). Shared with ChatCoreService (chat_core.py) so both `/chat` and
        `/api/chat/agentic` offer identical attachment behavior (CLAUDE.md §8's parity
        requirement). Never raises: a lookup failure must not break an otherwise-successful
        answer."""
        ids = {d for d in document_ids if d}
        if db is None or not ids:
            return []
        try:
            stmt = select(DocumentFormExtract).where(
                DocumentFormExtract.document_id.in_(ids),
                DocumentFormExtract.status == "active",
            )
            result = await db.execute(stmt)
            forms = result.scalars().all()
        except Exception:
            return []

        return [
            AttachmentReference(
                form_title=f.form_title,
                document_id=str(f.document_id),
                download_url=f"/documents/{f.document_id}/forms/{f.id}/download",
            )
            for f in forms
        ]

    @staticmethod
    def _build_sources_and_chunks(valid_chunks: list[dict]) -> tuple[list[SourceReference], list[VectorChunk]]:
        sources: list[SourceReference] = []
        vector_chunks: list[VectorChunk] = []

        for result in valid_chunks:
            metadata = result.get("metadata", {}) or {}
            title = metadata.get("document_title") or metadata.get("document_id")
            page = metadata.get("page")
            if page is not None and page < 0:
                page = None
            section = metadata.get("section") or None

            sources.append(SourceReference(
                document_title=title,
                document_id=metadata.get("document_id"),
                section=section,
                page=page,
                chunk_id=result.get("chunk_id"),
            ))
            vector_chunks.append(VectorChunk(
                content=result.get("content", ""),
                original_text=result.get("original_text"),
                source_document=title or "Unknown",
                page=page,
                chunk_id=result.get("chunk_id"),
                approval_status="approved",
            ))

        return sources, vector_chunks
