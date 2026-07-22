"""RetrievalAgent (CLAUDE.md §11A.1) — wrapper around vector retrieval.

When the orchestrator passes a Query Understanding ``analysis``, retrieval runs through
MultiQueryRetriever (same multi-query merge+rerank path /chat uses — §11A parity);
otherwise it falls back to the original single-query VectorRetrieverService path.
"""
from app.agents.base_agent import BaseAgent
from app.services.vector_retriever import VectorRetrieverService


class RetrievalAgent(BaseAgent):
    name = "RetrievalAgent"

    async def _run(self, input_data: dict) -> dict:
        query: str = input_data["query"]
        top_k = input_data.get("top_k")
        db = input_data.get("db")
        analysis_data = input_data.get("analysis")

        if analysis_data:
            from app.services.multi_query_retriever import MultiQueryRetriever
            from app.services.query_understanding.schemas import QueryAnalysis

            analysis = (
                analysis_data
                if isinstance(analysis_data, QueryAnalysis)
                else QueryAnalysis(**analysis_data)
            )
            results = await MultiQueryRetriever.retrieve(
                analysis,
                db,
                input_data.get("cache_service"),
                graph_results=input_data.get("graph_results") or [],
                top_k_per_query=top_k,
            )
        else:
            results = await VectorRetrieverService.retrieve(query, top_k=top_k, db=db)
        chunks = self._dedup(results)

        return {
            "chunks": [
                {
                    "chunk_id": r.get("chunk_id"),
                    "content": r.get("content"),
                    "original_text": r.get("original_text"),
                    "doc_id": (r.get("metadata") or {}).get("document_id"),
                    "source": (r.get("metadata") or {}).get("document_title"),
                    "page": (r.get("metadata") or {}).get("page"),
                    "similarity_score": r.get("similarity_score"),
                    "metadata": r.get("metadata"),
                }
                for r in chunks
            ],
            "raw_results": chunks,
        }

    @staticmethod
    def _dedup(results: list[dict]) -> list[dict]:
        seen: set[str] = set()
        deduped = []
        for r in results:
            chunk_id = r.get("chunk_id")
            if chunk_id and chunk_id in seen:
                continue
            if chunk_id:
                seen.add(chunk_id)
            deduped.append(r)
        return deduped
