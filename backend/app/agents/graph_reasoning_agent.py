"""GraphReasoningAgent (CLAUDE.md §11A.1) — wraps GraphRetrieverService/GraphService.

Adds a confidence score and a simple matched-entity reasoning-path string on top of the existing
flat, keyword-triggered Cypher lookups, plus the ProgramStudi->JalurPendaftaran->{Jadwal,Biaya,
Persyaratan} 2-hop chain (2026-07-23) — both relation legs already exist in the graph, this just
chains them so an answer can attribute a schedule/fee/requirement to the program studi it applies
to. Full cross-document multi-hop reasoning is intentionally still out of scope for this pass —
documented as deferred work in campus-va/IMPLEMENTATION.md §5.
"""
from app.agents.base_agent import BaseAgent
from app.services.graph_retriever import GraphRetrieverService

# Number of distinct entity types retrieve_by_intent can match (ProgramStudi/JalurPendaftaran/
# Persyaratan) — used as the denominator for a simple match-breadth confidence score.
_MAX_ENTITY_TYPES = 3


class GraphReasoningAgent(BaseAgent):
    name = "GraphReasoningAgent"

    async def _run(self, input_data: dict) -> dict:
        intent: str = input_data["intent"]

        try:
            graph_results = await GraphRetrieverService.retrieve_by_intent(intent)
        except Exception:
            # Neo4j unavailable — degrade gracefully, matching CLAUDE.md §22.5's failure handling
            # ("continue with Vector RAG if possible, mark GraphRAG as unavailable in logs").
            return {
                "graph_results": [],
                "nodes": [],
                "relations": [],
                "path_reasoning": "Knowledge graph unavailable for this request.",
                "confidence_score": 0.0,
                "graph_available": False,
            }

        distinct_types = {r["entity_type"] for r in graph_results}
        confidence = min(1.0, len(distinct_types) / _MAX_ENTITY_TYPES) if graph_results else 0.0

        relations = [
            {
                "from": r["related_to"],
                "relation": r["relation"],
                "to": r["entity_name"],
                "program_studi": r.get("program_studi"),
            }
            for r in graph_results
            if r.get("relation")
        ]

        reasoning_parts = [
            f"{r['entity_type']}={r['entity_name']}" for r in graph_results if not r.get("relation")
        ]
        reasoning_parts.extend(
            (
                f"{rel['program_studi']} -TERSEDIA_PADA-> {rel['from']} -{rel['relation']}-> {rel['to']}"
                if rel.get("program_studi")
                else f"{rel['from']} -{rel['relation']}-> {rel['to']}"
            )
            for rel in relations
        )
        path_reasoning = "; ".join(reasoning_parts) or "No matching graph entities for this query."

        return {
            "graph_results": graph_results,
            "nodes": graph_results,
            "relations": relations,
            "path_reasoning": path_reasoning,
            "confidence_score": confidence,
            "graph_available": True,
        }
