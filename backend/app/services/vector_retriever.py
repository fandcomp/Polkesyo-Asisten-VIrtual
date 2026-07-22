"""Retrieve approved chunks from Chroma vector store."""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.vector_index_service import VectorIndexService
from app.core.config import settings


class VectorRetrieverService:
    """Retrieve chunks from active Chroma collection."""

    @staticmethod
    async def retrieve(
        query: str,
        top_k: int | None = None,
        db: AsyncSession | None = None,
    ) -> list[dict]:
        """Retrieve relevant chunks for a query.

        When `db` is given, each result is enriched with the chunk's immutable
        `original_text` alongside the (LLM-summarized) embedded `content` — the summary
        stays what's searched/matched against, but the answer-generation prompt gets the
        verbatim source text too, so specific facts (article numbers, dates, fees,
        locations) don't depend on the summary having preserved them exactly.
        """
        k = top_k or (settings.rag_top_k or 3)

        results = await VectorIndexService.search(query, top_k=k)

        # Enrich results with source info
        enriched = []
        for result in results:
            enriched.append({
                "chunk_id": result["chunk_id"],
                "content": result["content"],
                "similarity_score": 1 - (result["distance"] or 0),  # Convert distance to similarity
                "metadata": result["metadata"],
            })

        if db is not None and enriched:
            original_texts = await VectorRetrieverService._fetch_original_texts(
                db, [e["chunk_id"] for e in enriched if e["chunk_id"]]
            )
            for e in enriched:
                e["original_text"] = original_texts.get(e["chunk_id"])

        return enriched

    @staticmethod
    async def _fetch_original_texts(db: AsyncSession, chunk_ids: list[str]) -> dict[str, str]:
        """Batch-fetch immutable original chunk text for a set of chunk UUIDs."""
        from app.db.models import DocumentChunk

        if not chunk_ids:
            return {}

        stmt = select(DocumentChunk.id, DocumentChunk.original_text).where(
            DocumentChunk.id.in_(chunk_ids)
        )
        rows = (await db.execute(stmt)).all()
        return {str(chunk_id): text for chunk_id, text in rows}
