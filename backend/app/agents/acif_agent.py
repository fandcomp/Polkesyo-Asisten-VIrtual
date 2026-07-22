"""ACIFAgent (CLAUDE.md §11A.1/§11A.2) — runs ACIF Gates 1-5 and returns one structured decision.

This agent does not reimplement ACIF — it calls the same Gate 1-3 classes chat_core.py already
uses (Gates 4/5 are run by AnswerComposerAgent, since they need the LLM call in between). ACIF
still runs before every OpenRouter call, exactly as CLAUDE.md §4.4/§11 requires.
"""
import logging

from app.agents.base_agent import BaseAgent
from app.agents.query_understanding_agent import STRICT_TOPICS
from app.db.models import AcifDecisionLog
from app.services.acif.context_integrity_scorer import ContextIntegrityScorer
from app.services.acif.graph_document_consistency import GraphDocumentConsistency
from app.services.acif.input_integrity_checker import InputIntegrityChecker
from app.services.acif.schemas import ACIFDecision

logger = logging.getLogger(__name__)

_MAX_VALID_CHUNKS = 3


class ACIFAgent(BaseAgent):
    name = "ACIFAgent"

    async def _run(self, input_data: dict) -> dict:
        message: str = input_data["message"]
        vector_results: list[dict] = input_data.get("vector_results") or []
        graph_results: list[dict] = input_data.get("graph_results") or []
        topic: str | None = input_data.get("topic")

        # Gate 1: Input Intent Integrity Check
        gate1 = await InputIntegrityChecker.check(message)
        if gate1.decision == ACIFDecision.REJECT:
            decision = self._build_decision(
                risk_level="high",
                filtering_mode="fallback",
                valid_chunks=[],
                blocked_chunks=[],
                context_integrity_score=0.0,
                source_integrity_score=0.0,
                graph_integrity_score=0.0,
                fallback_required=True,
                reason=f"Gate 1 rejected input: {gate1.reasoning}",
            )
            decision["gate1_rejected"] = True
            decision["risk_signals"] = gate1.risk_signals
            await self._persist_decision(input_data.get("db"), decision)
            return decision

        # CLAUDE.md §12 domain validation — same short-circuit as ChatCoreService so both
        # /chat and /api/chat/agentic keep identical out-of-domain guarantees.
        if gate1.domain_violation:
            decision = self._build_decision(
                risk_level="medium",
                filtering_mode="fallback",
                valid_chunks=[],
                blocked_chunks=[],
                context_integrity_score=0.0,
                source_integrity_score=0.0,
                graph_integrity_score=0.0,
                fallback_required=True,
                reason="Gate 1 domain validation: out-of-domain topic detected",
            )
            decision["domain_violation"] = True
            await self._persist_decision(input_data.get("db"), decision)
            return decision

        # Gate 2: Retrieval Context Integrity Scoring — same query_context /chat passes
        # (§11A parity): resolved question + term expansions from the Query Understanding
        # Layer, graph evidence for the no_contradiction dimension.
        analysis_data: dict = input_data.get("analysis") or {}
        gate2_query = analysis_data.get("resolved_question") or message
        query_context = {
            "term_expansions": analysis_data.get("term_expansions") or {},
            "detected_terms": analysis_data.get("detected_terms") or [],
            "exact_term_matched": bool(analysis_data.get("exact_term_matched")),
            "graph_results_present": bool(graph_results),
            "graph_entities": [g.get("entity_name") for g in graph_results],
        }
        scored = []
        blocked_chunks = []
        for chunk in vector_results:
            score_result = await ContextIntegrityScorer.score_context(
                chunk, gate2_query, query_context=query_context
            )
            if score_result["decision"] != "reject":
                scored.append((chunk, score_result))
            else:
                blocked_chunks.append({**chunk, "block_reason": "context_integrity_rejected"})

        # Gate 3: Graph-Document Consistency Check
        consistent = []
        for chunk, score in scored:
            consistency = await GraphDocumentConsistency.check_consistency(chunk, graph_results)
            if consistency["decision"] != "inconsistent_flag":
                consistent.append((chunk, score, consistency))
            else:
                blocked_chunks.append({**chunk, "block_reason": "graph_inconsistent"})

        valid = consistent[:_MAX_VALID_CHUNKS]
        valid_chunks = [
            {**chunk, "context_score": score["score"], "graph_consistency": consistency["consistency_score"]}
            for chunk, score, consistency in valid
        ]

        filtering_mode = "fallback" if not valid_chunks else ("strict" if topic in STRICT_TOPICS else "normal")
        context_integrity_score = self._avg([v["context_score"] for v in valid_chunks])
        graph_integrity_score = self._avg([v["graph_consistency"] for v in valid_chunks])
        source_integrity_score = self._avg([
            1.0 if (v.get("metadata") or {}).get("status") == "approved" else 0.0
            for v in valid_chunks
        ])

        decision = self._build_decision(
            risk_level=input_data.get("risk_level", "low"),
            filtering_mode=filtering_mode,
            valid_chunks=valid_chunks,
            blocked_chunks=blocked_chunks,
            context_integrity_score=context_integrity_score,
            source_integrity_score=source_integrity_score,
            graph_integrity_score=graph_integrity_score,
            fallback_required=not valid_chunks,
            reason="No valid official context after ACIF filtering." if not valid_chunks else "Context passed ACIF Gates 1-3.",
        )
        decision["valid_graph_paths"] = graph_results
        decision["blocked_graph_paths"] = []
        await self._persist_decision(input_data.get("db"), decision)
        return decision

    @staticmethod
    def _build_decision(
        *,
        risk_level: str,
        filtering_mode: str,
        valid_chunks: list[dict],
        blocked_chunks: list[dict],
        context_integrity_score: float,
        source_integrity_score: float,
        graph_integrity_score: float,
        fallback_required: bool,
        reason: str,
    ) -> dict:
        return {
            "risk_level": risk_level,
            "filtering_mode": filtering_mode,
            "context_integrity_score": context_integrity_score,
            "source_integrity_score": source_integrity_score,
            "graph_integrity_score": graph_integrity_score,
            "valid_chunks": valid_chunks,
            "blocked_chunks": blocked_chunks,
            "valid_graph_paths": [],
            "blocked_graph_paths": [],
            "citations_required": True,
            "fallback_required": fallback_required,
            "reason": reason,
            "gate1_rejected": False,
        }

    @staticmethod
    def _avg(values: list[float]) -> float:
        return sum(values) / len(values) if values else 0.0

    @staticmethod
    async def _persist_decision(db, decision: dict) -> None:
        """Writes one row to acif_decision_logs (CLAUDE.md §11A.2) — distinct from the generic
        agent_run_logs row BaseAgent.execute() already writes."""
        if db is None:
            return
        try:
            entry = AcifDecisionLog(
                risk_level=decision["risk_level"],
                filtering_mode=decision["filtering_mode"],
                context_integrity_score=decision["context_integrity_score"],
                source_integrity_score=decision["source_integrity_score"],
                graph_integrity_score=decision["graph_integrity_score"],
                decision="rejected" if decision.get("gate1_rejected") else (
                    "fallback" if decision["fallback_required"] else "accepted"
                ),
                rejection_reason=decision["reason"],
                fallback_required=decision["fallback_required"],
            )
            db.add(entry)
            await db.commit()
        except Exception as exc:  # noqa: BLE001 - logging must never break the chat pipeline
            logger.error(f"Failed to persist acif_decision_logs: {exc}")
