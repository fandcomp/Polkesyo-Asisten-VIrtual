"""Durable, per-chunk, admin-editable entity records (`chunk_entities` table).

Replaces the previous behavior where the admin chunk-review panel showed entities detected
live, on every request, with `GraphService.extract_entities(chunk.original_text)` — never
persisted, no id, no way to correct terminology (see `DocumentManagementService._detect_entities`,
still used unchanged by the pre-existing `GET /admin/documents/{id}/chunks` response for
backward compatibility). This service materializes that list once per chunk into a durable,
admin-curatable record: draft (`detected_text`/`entity_type`, immutable) -> admin correction
(`corrected_text`/`corrected_type`) -> confirmed/edited/rejected, mirroring `ChunkSummary`'s
draft -> edited -> approved shape.

Safety property (see `ChunkEntity` model docstring and `graph_service.py`): nothing here ever
renames or mutates an existing Neo4j entity node. Corrections only change which (type, name)
pair a chunk resolves to when `GraphService` re-derives the document's entity list on the next
reindex (`GraphService._resolve_chunk_entity_overrides`), which still only ever `MERGE`s
(create-if-missing / reuse-if-present).
"""
import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ChunkEntity, DocumentChunk
from app.services.graph_service import ALLOWED_ENTITY_TYPES, GraphService

logger = logging.getLogger(__name__)


class ChunkEntityError(Exception):
    """Base error for invalid chunk-entity operations."""


class ChunkEntityNotFoundError(ChunkEntityError):
    """Raised when the referenced chunk or entity row does not exist."""


class ChunkEntityValidationError(ChunkEntityError):
    """Raised when a requested entity_type is not in ALLOWED_ENTITY_TYPES."""


class ChunkEntityService:
    """Materialize, edit, confirm, reject, and add admin-curated chunk entities."""

    STATUS_DETECTED = "detected"
    STATUS_CONFIRMED = "confirmed"
    STATUS_EDITED = "edited"
    STATUS_REJECTED = "rejected"

    SOURCE_LLM_DETECTED = "llm_detected"
    SOURCE_ADMIN_ADDED = "admin_added"

    @staticmethod
    async def list_for_chunk(db: AsyncSession, chunk_id: UUID) -> list[ChunkEntity]:
        """Return the current entity list for a chunk, materializing it first if empty.

        Idempotent: extraction only ever runs the first time a chunk has zero `chunk_entities`
        rows. A chunk that already has rows is never re-extracted, even if `extract_entities`
        would now produce a different result — the point is a stable, admin-correctable list,
        not one that resets on every page load.
        """
        chunk = await ChunkEntityService._get_chunk_or_raise(db, chunk_id)

        existing = await ChunkEntityService._fetch_rows(db, chunk_id)
        if existing:
            return existing

        return await ChunkEntityService._materialize(db, chunk)

    @staticmethod
    async def _materialize(db: AsyncSession, chunk: DocumentChunk) -> list[ChunkEntity]:
        """Run the existing keyword extractor once and persist the results as `detected` rows."""
        detected = GraphService.extract_entities(chunk.original_text)

        rows: list[ChunkEntity] = []
        seen: set[tuple[str, str]] = set()
        for entity_type, entity_name in detected:
            if entity_type not in ALLOWED_ENTITY_TYPES:
                continue
            key = (entity_type, entity_name)
            if key in seen:
                continue
            seen.add(key)
            rows.append(
                ChunkEntity(
                    chunk_id=chunk.id,
                    document_id=chunk.document_id,
                    entity_type=entity_type,
                    detected_text=entity_name,
                    source=ChunkEntityService.SOURCE_LLM_DETECTED,
                    status=ChunkEntityService.STATUS_DETECTED,
                )
            )

        for row in rows:
            db.add(row)
        await db.commit()
        for row in rows:
            await db.refresh(row)
        return rows

    @staticmethod
    async def edit_entity(
        db: AsyncSession,
        entity_id: UUID,
        corrected_text: Optional[str],
        corrected_type: Optional[str],
        reviewed_by: Optional[str] = None,
    ) -> ChunkEntity:
        """Set an admin correction. Never touches `detected_text`/`entity_type` (immutable
        original detection) — only the parallel `corrected_*` override fields, matching
        `ChunkSummary.admin_edited_summary` never overwriting `llm_summary_draft`."""
        if corrected_type is not None and corrected_type not in ALLOWED_ENTITY_TYPES:
            raise ChunkEntityValidationError(f"Invalid entity_type: {corrected_type}")

        entity = await ChunkEntityService._get_entity_or_raise(db, entity_id)
        if corrected_text is not None:
            entity.corrected_text = corrected_text
        if corrected_type is not None:
            entity.corrected_type = corrected_type
        entity.status = ChunkEntityService.STATUS_EDITED
        entity.reviewed_by = reviewed_by
        entity.reviewed_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(entity)
        return entity

    @staticmethod
    async def confirm_entity(
        db: AsyncSession, entity_id: UUID, reviewed_by: Optional[str] = None
    ) -> ChunkEntity:
        """Confirm a detected entity as-is (no text/type change)."""
        entity = await ChunkEntityService._get_entity_or_raise(db, entity_id)
        entity.status = ChunkEntityService.STATUS_CONFIRMED
        entity.reviewed_by = reviewed_by
        entity.reviewed_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(entity)
        return entity

    @staticmethod
    async def reject_entity(
        db: AsyncSession, entity_id: UUID, reviewed_by: Optional[str] = None
    ) -> ChunkEntity:
        """The only "delete" mechanism — never hard-deleted, audit trail preserved (mirrors
        `ChunkReview`'s append-only pattern). Rejected rows are excluded from reindexing by
        `GraphService._resolve_chunk_entity_overrides`."""
        entity = await ChunkEntityService._get_entity_or_raise(db, entity_id)
        entity.status = ChunkEntityService.STATUS_REJECTED
        entity.reviewed_by = reviewed_by
        entity.reviewed_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(entity)
        return entity

    @staticmethod
    async def add_entity(
        db: AsyncSession,
        chunk_id: UUID,
        entity_type: str,
        text: str,
        reviewed_by: Optional[str] = None,
    ) -> ChunkEntity:
        """Admin-added entity that wasn't in the detected list. Created already `confirmed` —
        an admin typing in a new entity doesn't need a separate confirm step."""
        if entity_type not in ALLOWED_ENTITY_TYPES:
            raise ChunkEntityValidationError(f"Invalid entity_type: {entity_type}")

        chunk = await ChunkEntityService._get_chunk_or_raise(db, chunk_id)
        entity = ChunkEntity(
            chunk_id=chunk.id,
            document_id=chunk.document_id,
            entity_type=entity_type,
            detected_text=text,
            source=ChunkEntityService.SOURCE_ADMIN_ADDED,
            status=ChunkEntityService.STATUS_CONFIRMED,
            reviewed_by=reviewed_by,
            reviewed_at=datetime.now(timezone.utc),
        )
        db.add(entity)
        await db.commit()
        await db.refresh(entity)
        return entity

    @staticmethod
    async def _fetch_rows(db: AsyncSession, chunk_id: UUID) -> list[ChunkEntity]:
        stmt = (
            select(ChunkEntity)
            .where(ChunkEntity.chunk_id == chunk_id)
            .order_by(ChunkEntity.created_at)
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def _get_chunk_or_raise(db: AsyncSession, chunk_id: UUID) -> DocumentChunk:
        stmt = select(DocumentChunk).where(DocumentChunk.id == chunk_id)
        result = await db.execute(stmt)
        chunk = result.scalars().first()
        if not chunk:
            raise ChunkEntityNotFoundError(f"Chunk not found: {chunk_id}")
        return chunk

    @staticmethod
    async def _get_entity_or_raise(db: AsyncSession, entity_id: UUID) -> ChunkEntity:
        stmt = select(ChunkEntity).where(ChunkEntity.id == entity_id)
        result = await db.execute(stmt)
        entity = result.scalars().first()
        if not entity:
            raise ChunkEntityNotFoundError(f"Entity not found: {entity_id}")
        return entity
