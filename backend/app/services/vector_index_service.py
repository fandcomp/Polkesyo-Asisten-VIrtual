"""Index approved chunks into Chroma vector store."""
import asyncio
import logging
import threading

import chromadb
from app.core.config import settings
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.models import Document, DocumentChunk, ChunkSummary
from app.services.text_extractor import TextExtractor

logger = logging.getLogger(__name__)

# Loaded once per process — the sentence-transformers model is ~100MB+ in memory and
# thread-safe for encode(); reloading it per call would add seconds to every request.
_embedding_function = None
_embedding_function_loaded = False
# Guards the warm-up race below: without it, concurrent asyncio.to_thread callers (e.g.
# the evaluation runner firing several gold-QA questions at once on a cold process) each
# see _embedding_function_loaded=False and start their own SentenceTransformerEmbeddingFunction
# load simultaneously. Every racing caller then blocks inside search()'s CHROMA_CALL_TIMEOUT_SECONDS
# wait_for; if the concurrent loads push past that timeout, the TimeoutError is silently
# swallowed by search()'s bare except (see below), and retrieval degrades to zero results —
# indistinguishable from "no relevant documents" until you check the logs.
_embedding_function_lock = threading.Lock()

# One HttpClient per process. chromadb's HttpClient is never closed by callers, and
# creating a fresh one per call (every /health heartbeat, every chat search) leaked its
# TCP connections until the worker hit the 1024-fd ulimit ("Too many open files" in
# production, surfacing to users as bogus session-expired chat errors).
_chroma_client = None

# chromadb's HttpClient is sync-only with no built-in timeout. Calling it directly
# from an async def blocks the *entire event loop* of the worker (not just this
# request) if Chroma is slow or wedged — a known-flaky dependency in this project
# (see IMPLEMENTATION.md Chroma ONNX-download notes). Every chroma call in this
# service must go through asyncio.to_thread + asyncio.wait_for so a stuck Chroma
# degrades one request instead of freezing the whole worker (and, transitively,
# every other in-flight chat/admin request on it).
CHROMA_CALL_TIMEOUT_SECONDS = 8


class VectorIndexService:
    """Manage Chroma indexing for approved chunks."""

    @staticmethod
    def get_chroma_client():
        """Get the process-wide Chroma client (see _chroma_client note above).

        The client is a thread-safe stateless HTTP wrapper, so sharing one instance
        across the asyncio.to_thread offloads in this service is fine."""
        global _chroma_client
        if _chroma_client is None:
            _chroma_client = chromadb.HttpClient(
                host=settings.chroma_host,
                port=settings.chroma_port,
            )
        return _chroma_client

    ACTIVE_COLLECTION_NAME = "campus_documents_active"

    @staticmethod
    def get_embedding_function():
        """Sentence-transformers embedding function per EMBEDDING_MODEL_NAME, or None for
        Chroma's default. Cached per process; a load failure logs CRITICAL and falls back
        to the default embedder so retrieval degrades instead of crashing — but note the
        fallback is only correct if the collection was also built with the default."""
        global _embedding_function, _embedding_function_loaded
        if _embedding_function_loaded:
            return _embedding_function
        with _embedding_function_lock:
            # Re-check inside the lock: another thread may have finished loading while
            # this one was waiting to acquire it.
            if _embedding_function_loaded:
                return _embedding_function
            model_name = settings.embedding_model_name.strip()
            if model_name:
                try:
                    from chromadb.utils.embedding_functions import (
                        SentenceTransformerEmbeddingFunction,
                    )

                    _embedding_function = SentenceTransformerEmbeddingFunction(model_name=model_name)
                except Exception as exc:
                    logger.critical(
                        "Failed to load embedding model %s — falling back to Chroma default "
                        "embedder. Retrieval quality is degraded until this is fixed: %s",
                        model_name, exc,
                    )
                    _embedding_function = None
            _embedding_function_loaded = True
        return _embedding_function

    @staticmethod
    def get_active_collection(client=None):
        """Get or create active documents collection (with the configured embedder)."""
        if client is None:
            client = VectorIndexService.get_chroma_client()

        collection_name = VectorIndexService.ACTIVE_COLLECTION_NAME
        embedding_function = VectorIndexService.get_embedding_function()
        # The embedding function must be attached on get_collection too — it embeds
        # queries and new documents client-side; omitting it silently reverts to the
        # default (English) embedder.
        kwargs = {"embedding_function": embedding_function} if embedding_function else {}
        try:
            collection = client.get_collection(name=collection_name, **kwargs)
        except Exception:
            collection = client.create_collection(
                name=collection_name,
                metadata={"hnsw:space": "cosine"},
                **kwargs,
            )

        return collection

    @staticmethod
    def _rebuild_collection_sync() -> None:
        """Blocking: drop and recreate the active collection (thread-offloaded by caller).

        Required when EMBEDDING_MODEL_NAME changes — vectors from the old embedder are
        not comparable with new-query embeddings even at equal dimensionality.
        """
        client = VectorIndexService.get_chroma_client()
        try:
            client.delete_collection(VectorIndexService.ACTIVE_COLLECTION_NAME)
        except Exception:
            pass  # collection didn't exist yet
        VectorIndexService.get_active_collection(client)

    @staticmethod
    async def rebuild_active_collection(db: AsyncSession) -> dict:
        """Drop the active collection and re-index every approved chunk with the current
        embedder. Approved-only guarantees are inherited from index_approved_chunks —
        this changes vector representations, never the knowledge-approval state."""
        await asyncio.wait_for(
            asyncio.to_thread(VectorIndexService._rebuild_collection_sync),
            timeout=CHROMA_CALL_TIMEOUT_SECONDS * 4,
        )
        result = await VectorIndexService.index_approved_chunks(db)

        # Visual chunks index per document — re-index every document that has
        # approved/active visual chunks ("active" rows were flipped by a previous index
        # run and must also be re-embedded into the fresh collection).
        try:
            from app.services.ingestion.visual_chunk_indexer import VisualChunkIndexer

            from sqlalchemy import update

            visual_types = ["image", "scanned_region", "diagram", "table_image"]
            # The indexer only selects admin_status='approved' (and flips to 'active'
            # after indexing) — reset previously-active rows so they get re-embedded
            # into the fresh collection instead of silently vanishing from retrieval.
            await db.execute(
                update(DocumentChunk)
                .where(
                    DocumentChunk.chunk_type.in_(visual_types),
                    DocumentChunk.admin_status == "active",
                )
                .values(admin_status="approved")
            )
            await db.commit()

            visual_doc_ids = (
                await db.execute(
                    select(DocumentChunk.document_id)
                    .where(
                        DocumentChunk.chunk_type.in_(visual_types),
                        DocumentChunk.admin_status == "approved",
                    )
                    .distinct()
                )
            ).scalars().all()
            visual_results = []
            for doc_id in visual_doc_ids:
                visual_results.append(
                    await VisualChunkIndexer.index_approved_visual_chunks(db, str(doc_id))
                )
            result["visual"] = {"documents": len(visual_doc_ids), "results": visual_results}
        except Exception as exc:
            result["visual"] = {"status": "error", "error": str(exc)}

        return result

    @staticmethod
    def _upsert_items_sync(items: list[tuple[str, str, dict]]) -> list[tuple[str, str | None]]:
        """Blocking Chroma writes — must run in a thread (see class docstring note).

        Returns (chunk_id, error_message_or_None) per item so the caller can update
        DB state without touching Chroma from the event loop again.
        """
        client = VectorIndexService.get_chroma_client()
        collection = VectorIndexService.get_active_collection(client)
        outcomes: list[tuple[str, str | None]] = []
        for chunk_id, content, metadata in items:
            try:
                collection.upsert(ids=[chunk_id], documents=[content], metadatas=[metadata])
                outcomes.append((chunk_id, None))
            except Exception as e:
                outcomes.append((chunk_id, str(e)))
        return outcomes

    @staticmethod
    async def upsert_items(items: list[tuple[str, str, dict]]) -> list[tuple[str, str | None]]:
        """Bounded Chroma upsert for pre-built (id, content, metadata) items (see class
        docstring note). Shared by `index_approved_chunks` (text) and
        `VisualChunkIndexer.index_approved_visual_chunks` (image/diagram/table chunks) so
        both indexing paths get the same to_thread + wait_for protection."""
        timeout = CHROMA_CALL_TIMEOUT_SECONDS * max(len(items), 1)
        return await asyncio.wait_for(
            asyncio.to_thread(VectorIndexService._upsert_items_sync, items),
            timeout=timeout,
        )

    @staticmethod
    def _delete_ids_sync(chunk_ids: list[str]) -> list[tuple[str, str | None]]:
        """Blocking Chroma delete — must run in a thread (see class docstring note).

        Chroma's `delete()` is idempotent for missing ids (no error), so callers don't need
        to check existence first."""
        client = VectorIndexService.get_chroma_client()
        collection = VectorIndexService.get_active_collection(client)
        try:
            collection.delete(ids=chunk_ids)
            return [(cid, None) for cid in chunk_ids]
        except Exception as e:
            return [(cid, str(e)) for cid in chunk_ids]

    @staticmethod
    async def remove_chunks_from_index(chunk_ids: list[str]) -> dict:
        """Delete chunk vectors from the active Chroma collection.

        MUST be called whenever a chunk transitions away from `status='approved'` (e.g.
        superseded by document reingestion). Chroma's copy of a chunk's metadata (including
        the `"status": "approved"` field `index_approved_chunks` writes at index time) is a
        point-in-time snapshot — nothing re-syncs it when the Postgres row later changes, so
        a chunk that becomes `superseded` in Postgres stays indefinitely retrievable and
        scored as "approved" by `MultiQueryRetriever` until it's explicitly deleted here.
        Without this, superseded/stale content can be selected into live answer context.
        """
        result = {"deleted_count": 0, "errors": []}
        if not chunk_ids:
            return result
        timeout = CHROMA_CALL_TIMEOUT_SECONDS * max(len(chunk_ids), 1)
        try:
            outcomes = await asyncio.wait_for(
                asyncio.to_thread(VectorIndexService._delete_ids_sync, chunk_ids),
                timeout=timeout,
            )
            result["deleted_count"] = sum(1 for _, err in outcomes if err is None)
            result["errors"] = [f"{cid}: {err}" for cid, err in outcomes if err]
        except Exception as e:
            result["errors"].append(str(e))
        return result

    @staticmethod
    async def index_approved_chunks(
        db: AsyncSession,
        document_id: str | None = None,
    ) -> dict:
        """Index approved chunks into active Chroma collection."""
        result = {
            "indexed_count": 0,
            "skipped_count": 0,
            "errors": [],
        }

        try:
            # Query: approved chunks with approved summaries + parent document
            stmt = (
                select(DocumentChunk, ChunkSummary, Document)
                .join(ChunkSummary)
                .join(Document, DocumentChunk.document_id == Document.id)
                .where(
                    (DocumentChunk.status == "approved") &
                    (ChunkSummary.approved_summary.isnot(None))
                )
            )

            if document_id:
                stmt = stmt.where(DocumentChunk.document_id == document_id)

            query_result = await db.execute(stmt)
            rows = query_result.all()

            chunks_by_id = {str(chunk.id): chunk for chunk, _summary, _document in rows}
            items = [
                (
                    str(chunk.id),
                    # Admin-approved summaries already exclude the e-signature boilerplate
                    # naturally (verified live — LLM summarization drops it on its own), but
                    # the raw original_text fallback (chunks with no approved summary yet)
                    # does not, so it's cleaned here at embed time only — the DB's
                    # `original_text` column itself is never touched (immutable citation
                    # evidence, CLAUDE.md).
                    summary.approved_summary or TextExtractor._clean_boilerplate(chunk.original_text or ""),
                    {
                        # Citation metadata — Chroma rejects None values, so fall
                        # back to sentinel values for optional fields.
                        "chunk_id": str(chunk.id),
                        "document_id": str(chunk.document_id),
                        "document_title": document.title or "",
                        "document_type": document.document_type or "",
                        "page": chunk.page if chunk.page is not None else -1,
                        "section": chunk.section or "",
                        "chunk_index": chunk.chunk_index,
                        "token_count": chunk.token_count or 0,
                        "status": "approved",
                    },
                )
                for chunk, summary, document in rows
            ]

            # Chroma writes are bounded and offloaded to a thread (see class docstring
            # note) so a slow/wedged Chroma can't freeze this worker's event loop.
            outcomes = await VectorIndexService.upsert_items(items)

            for chunk_id, error in outcomes:
                if error is None:
                    chunks_by_id[chunk_id].active = 1
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

    @staticmethod
    def _query_sync(query: str, top_k: int) -> dict:
        """Blocking Chroma read — must run in a thread (see class docstring note)."""
        client = VectorIndexService.get_chroma_client()
        collection = VectorIndexService.get_active_collection(client)
        return collection.query(query_texts=[query], n_results=top_k)

    @staticmethod
    def _count_sync() -> int:
        """Blocking Chroma read — must run in a thread (see class docstring note)."""
        collection = VectorIndexService.get_active_collection()
        return collection.count()

    @staticmethod
    async def get_active_count() -> dict:
        """Count vectors in the active collection for the admin monitoring dashboard.

        Was previously called as a raw `chromadb.HttpClient`/`collection.count()` directly
        inside `routes_admin.py`'s async endpoint — the exact sync-call-in-event-loop pattern
        that froze the whole worker in the 2026-07-06 incident (see class docstring note).
        Routed through the same to_thread + wait_for bound used by `search()`/indexing so a
        slow/wedged Chroma degrades this one dashboard field instead of the whole backend.
        """
        try:
            count = await asyncio.wait_for(
                asyncio.to_thread(VectorIndexService._count_sync),
                timeout=CHROMA_CALL_TIMEOUT_SECONDS,
            )
            return {"reachable": True, "count": count}
        except Exception as e:
            return {"reachable": False, "count": None, "error": str(e)}

    @staticmethod
    async def search(
        query: str,
        top_k: int = 3,
    ) -> list[dict]:
        """Search active collection for similar chunks."""
        try:
            # Offloaded and bounded (see class docstring note) — this runs on every
            # chat message, so a slow/wedged Chroma must degrade to "no context"
            # instead of freezing this worker's event loop for every other request.
            results = await asyncio.wait_for(
                asyncio.to_thread(VectorIndexService._query_sync, query, top_k),
                timeout=CHROMA_CALL_TIMEOUT_SECONDS,
            )

            # Convert to list of documents with metadata
            documents = []
            for i in range(len(results["ids"][0]) if results["ids"] else 0):
                documents.append({
                    "chunk_id": results["ids"][0][i],
                    "content": results["documents"][0][i],
                    "metadata": results["metadatas"][0][i],
                    "distance": results["distances"][0][i] if results["distances"] else None,
                })

            return documents

        except Exception as exc:
            # Never swallow this silently — a timed-out/wedged Chroma call and "genuinely
            # no relevant documents" both return [] to the caller, but only one of them is
            # an infra problem. Without this log, retrieval failures are indistinguishable
            # from correct empty results in the evaluation metrics and in production traces.
            logger.error("VectorIndexService.search failed for query %r (top_k=%d): %s", query, top_k, exc)
            return []
