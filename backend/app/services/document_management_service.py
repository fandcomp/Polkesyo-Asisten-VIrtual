"""Document management service for admin operations."""
import logging
import os
from datetime import datetime
from uuid import UUID, uuid4
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import and_, func, select, update

from app.db.models import Document, DocumentVersion, DocumentChunk, ChunkSummary
from app.services.document_classifier import DocumentClassifier
from app.services.chunking_service import ChunkingService
from app.services.chunk_summary_service import ChunkSummaryService
from app.services.acif.text_normalizer import TextNormalizer
from app.services.acif.risk_signals import RiskSignals
from app.services.acif.semantic_injection_detector import SemanticInjectionDetector
from app.services.graph_service import GraphService

logger = logging.getLogger(__name__)


class DocumentManagementService:
    """Manage document lifecycle for admin."""

    # Document workflow status
    STATUS_DISCOVERED = "discovered"
    STATUS_DOWNLOADED = "downloaded"
    STATUS_EXTRACTED = "extracted"
    STATUS_CHUNKED = "chunked"
    STATUS_SUMMARIZED = "summarized"
    STATUS_PENDING_REVIEW = "pending_review"
    STATUS_APPROVED = "approved"
    STATUS_INDEXED = "indexed"
    STATUS_ACTIVE = "active"
    STATUS_REJECTED = "rejected"
    STATUS_NEEDS_REVISION = "needs_revision"
    STATUS_SUPERSEDED = "superseded"
    STATUS_ARCHIVED = "archived"

    CHUNK_STATUS_APPROVED = "approved"
    CHUNK_STATUS_REJECTED = "rejected"
    CHUNK_STATUS_NEEDS_REVISION = "needs_revision"

    @staticmethod
    async def list_documents(
        db: AsyncSession,
        status: Optional[str] = None,
        document_type: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[dict], int]:
        """List documents with filters."""
        stmt = select(Document)

        if status:
            stmt = stmt.where(Document.status == status)
        if document_type:
            stmt = stmt.where(Document.document_type == document_type)

        # Get total count
        count_stmt = select(func.count(Document.id))
        if status:
            count_stmt = count_stmt.where(Document.status == status)
        if document_type:
            count_stmt = count_stmt.where(Document.document_type == document_type)

        count_result = await db.execute(count_stmt)
        total = count_result.scalar() or 0

        # Get paginated results
        stmt = stmt.offset(offset).limit(limit).order_by(Document.created_at.desc())
        result = await db.execute(stmt)
        documents = result.scalars().all()

        return [DocumentManagementService._document_to_dict(doc) for doc in documents], total

    @staticmethod
    async def get_document_detail(
        db: AsyncSession,
        document_id: UUID,
    ) -> Optional[dict]:
        """Get detailed document information."""
        stmt = select(Document).where(Document.id == document_id)
        result = await db.execute(stmt)
        doc = result.scalar_one_or_none()

        if not doc:
            return None

        # Get versions
        version_stmt = select(DocumentVersion).where(
            DocumentVersion.document_id == document_id
        ).order_by(DocumentVersion.version.desc())
        version_result = await db.execute(version_stmt)
        versions = version_result.scalars().all()

        # Get chunk count
        chunk_stmt = select(func.count(DocumentChunk.id)).where(
            DocumentChunk.document_id == document_id
        )
        chunk_result = await db.execute(chunk_stmt)
        chunk_count = chunk_result.scalar() or 0

        doc_dict = DocumentManagementService._document_to_dict(doc)
        doc_dict["versions"] = [
            {
                # UUID — required by POST /admin/ingestion/ingest-document/{version_id}
                "id": str(v.id),
                "version": v.version,
                "checksum": v.checksum,
                "created_at": v.created_at.isoformat() if v.created_at else None,
                "status": v.status,
            }
            for v in versions
        ]
        doc_dict["chunk_count"] = chunk_count

        return doc_dict

    @staticmethod
    async def update_document_status(
        db: AsyncSession,
        document_id: UUID,
        new_status: str,
        notes: Optional[str] = None,
    ) -> bool:
        """Update document status (e.g., approve, reject)."""
        stmt = (
            update(Document)
            .where(Document.id == document_id)
            .values(status=new_status, updated_at=datetime.utcnow())
        )
        await db.execute(stmt)
        await db.commit()

        logger.info(f"Document {document_id} status updated to {new_status}")
        if notes:
            logger.info(f"  Notes: {notes}")

        return True

    @staticmethod
    async def get_chunks_for_review(
        db: AsyncSession,
        document_id: UUID,
    ) -> list[dict]:
        """Get chunks for admin review."""
        stmt = (
            select(DocumentChunk)
            .where(
                DocumentChunk.document_id == document_id,
                DocumentChunk.chunk_type == "text",
            )
            .order_by(DocumentChunk.chunk_index)
        )
        result = await db.execute(stmt)
        chunks = result.scalars().all()

        chunks_data = []
        for chunk in chunks:
            # Get summary
            summary_stmt = select(ChunkSummary).where(
                ChunkSummary.chunk_id == chunk.id
            )
            summary_result = await db.execute(summary_stmt)
            summary = summary_result.scalar_one_or_none()

            risk_flags = DocumentManagementService._detect_risk_flags(chunk.original_text)
            risk_flags.extend(await DocumentManagementService._detect_semantic_risk_flags(chunk.original_text))

            chunks_data.append({
                # UUID primary key — required by the /admin/chunks/{chunk_id}/* endpoints
                "id": str(chunk.id),
                "chunk_id": chunk.chunk_id,
                "chunk_index": chunk.chunk_index,
                "page": chunk.page,
                "section": chunk.section,
                # Full text: admins must review the original chunk, not a preview
                "original_text": chunk.original_text,
                "status": chunk.status,
                "llm_summary": summary.llm_summary_draft if summary else None,
                "admin_summary": summary.admin_edited_summary if summary else None,
                "approved_summary": summary.approved_summary if summary else None,
                "risk_flags": risk_flags,
                "detected_entities": DocumentManagementService._detect_entities(chunk.original_text),
            })

        return chunks_data

    @staticmethod
    async def get_stats_summary(db: AsyncSession) -> dict:
        """Aggregate document/chunk counts for the admin monitoring dashboard.

        Replaces the frontend's previous client-side stat computation, which read a
        `Document.status` transition ("approved"/"active") that nothing in the backend ever
        sets, and a flagged-chunk count that only covered whichever single document was last
        opened in the UI during that session.
        """
        doc_status_stmt = select(Document.status, func.count()).group_by(Document.status)
        documents_by_status = dict((await db.execute(doc_status_stmt)).all())

        chunk_status_stmt = (
            select(DocumentChunk.status, func.count())
            .where(DocumentChunk.chunk_type == "text")
            .group_by(DocumentChunk.status)
        )
        chunks_by_status = dict((await db.execute(chunk_status_stmt)).all())

        # Flagged chunks: reuse the same risk-flag detector the per-document review queue
        # uses, scanning every text chunk across all documents rather than just the one the
        # admin currently has selected.
        text_stmt = select(DocumentChunk.original_text).where(DocumentChunk.chunk_type == "text")
        texts = (await db.execute(text_stmt)).scalars().all()
        flagged_chunks = sum(
            1 for text in texts if DocumentManagementService._detect_risk_flags(text)
        )

        return {
            "documents": {
                "total": sum(documents_by_status.values()),
                "by_status": documents_by_status,
            },
            "chunks": {
                "total": sum(chunks_by_status.values()),
                "by_status": chunks_by_status,
                "flagged": flagged_chunks,
            },
        }

    @staticmethod
    async def approve_chunk(
        db: AsyncSession,
        chunk_id: UUID,
        admin_summary: Optional[str] = None,
    ) -> bool:
        """Approve a chunk for indexing."""
        # Update chunk status
        chunk_stmt = (
            update(DocumentChunk)
            .where(DocumentChunk.id == chunk_id)
            .values(status=DocumentManagementService.CHUNK_STATUS_APPROVED)
        )
        await db.execute(chunk_stmt)

        # Update summary if provided
        if admin_summary:
            summary_stmt = (
                update(ChunkSummary)
                .where(ChunkSummary.chunk_id == chunk_id)
                .values(
                    admin_edited_summary=admin_summary,
                    approved_summary=admin_summary,
                )
            )
            await db.execute(summary_stmt)

        await db.commit()
        logger.info(f"Chunk {chunk_id} approved")
        return True

    @staticmethod
    async def reject_chunk(
        db: AsyncSession,
        chunk_id: UUID,
        reason: Optional[str] = None,
    ) -> bool:
        """Reject a chunk from indexing."""
        stmt = (
            update(DocumentChunk)
            .where(DocumentChunk.id == chunk_id)
            .values(status=DocumentManagementService.CHUNK_STATUS_REJECTED)
        )
        await db.execute(stmt)
        await db.commit()

        logger.info(f"Chunk {chunk_id} rejected")
        if reason:
            logger.info(f"  Reason: {reason}")
        return True

    @staticmethod
    def _detect_risk_flags(original_text: str) -> list[str]:
        """Flag risky chunk content for admin review — reuses ACIF's own
        prompt-injection phrase list and encoded-content detection (Gate 1's
        `RiskSignals`/`TextNormalizer`) instead of a separate detector, so the
        review UI and the input-integrity gate stay consistent with each other."""
        flags: list[str] = []

        normalized = TextNormalizer.normalize(original_text)
        _score, matched_phrases = RiskSignals.get_risk_score(normalized)
        if matched_phrases:
            flags.append("terindikasi prompt injection")

        if TextNormalizer.extract_encoded_patterns(original_text):
            flags.append("berisi pola konten ter-encode (base64/hex)")

        return flags

    @staticmethod
    async def _detect_semantic_risk_flags(original_text: str) -> list[str]:
        """Paraphrase-resistant companion to `_detect_risk_flags` — a malicious source
        document (uploaded or auto-synced) can carry an injection payload worded
        differently from every literal RiskSignals phrase, which `_detect_risk_flags`
        alone cannot see (same gap Gate 1's semantic layer closes for user messages —
        see semantic_injection_detector.py). Flag only, never auto-reject: CLAUDE.md §38's
        established pattern for risky ingested content is "detect, flag, let admin decide".

        Deliberately called only from `get_chunks_for_review` (bounded to one document's
        chunks at a time), NOT from `get_stats_summary`'s whole-corpus scan — embedding
        every chunk in the database on every dashboard poll would be far too costly for
        a stats endpoint; `_detect_risk_flags`'s literal check stays cheap enough for that.
        """
        similarity = await SemanticInjectionDetector.max_similarity_to_known_attacks(original_text)
        bump = SemanticInjectionDetector.score_bump(similarity)
        if bump > 0:
            return [f"terindikasi prompt injection (kemiripan semantik {similarity:.2f})"]
        return []

    @staticmethod
    def _detect_entities(original_text: str) -> list[str]:
        """Surface entities in a chunk for admin review — reuses
        `GraphService.extract_entities`, the same keyword-based extractor
        used when indexing approved chunks into Neo4j, so the review UI shows
        the same entities that will actually reach the knowledge graph."""
        entities = GraphService.extract_entities(original_text)
        # Deduplicate while preserving first-seen order (a chunk can repeat
        # the same keyword, e.g. "ijazah" appearing twice).
        seen: set[str] = set()
        labels: list[str] = []
        for entity_type, entity_name in entities:
            label = f"{entity_type}: {entity_name}"
            if label not in seen:
                seen.add(label)
                labels.append(label)
        return labels

    @staticmethod
    def _document_to_dict(doc: Document) -> dict:
        """Convert document to dict."""
        return {
            "id": str(doc.id),
            "title": doc.title,
            "document_type": doc.document_type,
            "source_type": doc.source_type,
            "status": doc.status,
            "year": doc.year,
            "created_at": doc.created_at.isoformat() if doc.created_at else None,
            "updated_at": doc.updated_at.isoformat() if doc.updated_at else None,
        }
