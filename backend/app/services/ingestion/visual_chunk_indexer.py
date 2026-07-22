"""Index approved visual chunks (image/diagram/table_image/scanned_region) into Chroma."""
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.models import Document, DocumentChunk
from app.services.vector_index_service import VectorIndexService

logger = logging.getLogger(__name__)


class VisualChunkIndexer:
    """Index admin-approved visual chunks into the active Chroma collection.

    Previously took `chroma_client`/`neo4j_client` parameters that nothing in the codebase
    ever supplied — `routes_visual_chunks_admin.py`'s approve endpoint only flipped
    `admin_status` in Postgres and never called this class, so approved visual chunks were
    never actually searchable. Rewritten to use `VectorIndexService`'s own thread+timeout
    bounded Chroma access (same pattern as text chunks) instead of a raw client.
    """

    @staticmethod
    async def index_approved_visual_chunks(
        db: AsyncSession,
        document_id: str,
    ) -> dict:
        """Index all admin_status='approved' visual chunks for a document into Chroma."""
        result = {"indexed_count": 0, "skipped_count": 0, "errors": []}

        try:
            stmt = (
                select(DocumentChunk, Document)
                .join(Document, DocumentChunk.document_id == Document.id)
                .where(
                    DocumentChunk.document_id == document_id,
                    DocumentChunk.chunk_type.in_(["image", "scanned_region", "diagram", "table_image"]),
                    DocumentChunk.admin_status == "approved",
                )
            )
            query_result = await db.execute(stmt)
            rows = query_result.all()

            chunks_by_id = {str(chunk.id): chunk for chunk, _document in rows}
            items = [
                (
                    str(chunk.id),
                    chunk.visible_text_draft or chunk.raw_visual_description or "",
                    {
                        # Citation metadata — Chroma rejects None values, so fall back to
                        # sentinel values for optional fields (mirrors text-chunk indexing).
                        "chunk_id": str(chunk.id),
                        "document_id": str(chunk.document_id),
                        "document_title": document.title or "",
                        "document_type": document.document_type or "",
                        "page": chunk.page if chunk.page is not None else -1,
                        "chunk_type": chunk.chunk_type,
                        "chunk_index": chunk.chunk_index,
                        "source": "visual_chunk",
                        "status": "approved",
                    },
                )
                for chunk, document in rows
            ]

            outcomes = await VectorIndexService.upsert_items(items)

            for chunk_id, error in outcomes:
                if error is None:
                    chunks_by_id[chunk_id].active = 1
                    chunks_by_id[chunk_id].admin_status = "active"
                    result["indexed_count"] += 1
                else:
                    result["errors"].append(f"Chunk {chunk_id}: {error}")
                    result["skipped_count"] += 1

            await db.commit()
            result["status"] = "completed"

        except Exception as e:
            result["status"] = "error"
            result["error"] = str(e)

        return result
