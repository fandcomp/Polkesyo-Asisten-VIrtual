"""Admin routes for chunk review and approval workflow."""
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.session import get_db
from app.db.models import ChunkEntity, DocumentChunk, ChunkSummary, ChunkReview
from app.services.vector_index_service import VectorIndexService
from app.services.graph_service import ALLOWED_ENTITY_TYPES, GraphService
from app.services.redis_cache_service import get_cache_service
from app.services.chunk_entity_service import (
    ChunkEntityNotFoundError,
    ChunkEntityService,
    ChunkEntityValidationError,
)
from datetime import datetime

router = APIRouter(prefix="/admin", tags=["admin"])


async def _reindex_document(db: AsyncSession, document_id: str) -> dict:
    """Push newly-approved chunks into Chroma + Neo4j and clear stale retrieval cache.

    Approval alone used to leave a chunk stuck in Postgres until an admin separately hit
    `POST /admin/indexing/run` / `POST /admin/graph/index-document` — this makes approval
    immediately reflect in chat, reusing the same indexing methods those endpoints call.
    """
    vector_result = await VectorIndexService.index_approved_chunks(db, document_id)
    graph_result = await GraphService.index_document_by_id(db, document_id)
    cache_service = await get_cache_service()
    await cache_service.invalidate_retrieval_cache()
    return {"vector_index": vector_result, "graph_index": graph_result}


class ChunkSummaryUpdate(BaseModel):
    """Update chunk summary."""
    approved_summary: str


class ChunkApproval(BaseModel):
    """Approve or reject chunk."""
    decision: str  # approve, reject, needs_revision
    notes: str = ""


@router.get("/chunks/pending-review")
async def list_pending_chunks(
    db: AsyncSession = Depends(get_db),
    limit: int = 50,
):
    """List chunks pending admin review."""
    stmt = (
        select(DocumentChunk, ChunkSummary)
        .join(ChunkSummary)
        .where(DocumentChunk.status == "created")
        .limit(limit)
    )
    result = await db.execute(stmt)
    rows = result.all()
    
    return [
        {
            "chunk_id": str(chunk.id),
            "document_id": str(chunk.document_id),
            "chunk_index": chunk.chunk_index,
            "original_text": chunk.original_text[:200],  # Preview
            "token_count": chunk.token_count,
            "llm_summary_draft": summary.llm_summary_draft,
            "admin_summary": summary.admin_edited_summary,
        }
        for chunk, summary in rows
    ]


@router.patch("/chunks/{chunk_id}/summary")
async def update_chunk_summary(
    chunk_id: UUID,
    update: ChunkSummaryUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update chunk summary (admin edit)."""
    stmt = select(ChunkSummary).join(DocumentChunk).where(DocumentChunk.id == chunk_id)
    result = await db.execute(stmt)
    summary = result.scalars().first()
    
    if not summary:
        raise HTTPException(status_code=404, detail="Chunk not found")
    
    summary.admin_edited_summary = update.approved_summary
    await db.commit()
    
    return {"status": "updated", "chunk_id": str(chunk_id)}


@router.post("/chunks/{chunk_id}/approve")
async def approve_chunk(
    chunk_id: UUID,
    approval: ChunkApproval,
    db: AsyncSession = Depends(get_db),
):
    """Approve or reject chunk."""
    stmt = select(DocumentChunk).where(DocumentChunk.id == chunk_id)
    result = await db.execute(stmt)
    chunk = result.scalars().first()
    
    if not chunk:
        raise HTTPException(status_code=404, detail="Chunk not found")
    
    # Update chunk status
    if approval.decision == "approve":
        chunk.status = "approved"
        # Promote the admin-edited summary (or LLM draft) to approved_summary —
        # vector indexing only picks up chunks whose approved_summary is set.
        summary_stmt = select(ChunkSummary).where(ChunkSummary.chunk_id == chunk.id)
        summary_result = await db.execute(summary_stmt)
        summary = summary_result.scalars().first()
        if summary and not summary.approved_summary:
            summary.approved_summary = (
                summary.admin_edited_summary or summary.llm_summary_draft
            )
    elif approval.decision == "reject":
        chunk.status = "rejected"
    elif approval.decision == "needs_revision":
        chunk.status = "needs_revision"
    
    # Log review decision
    review = ChunkReview(
        chunk_id=chunk.id,
        decision=approval.decision,
        admin_notes=approval.notes,
        approved_at=datetime.utcnow() if approval.decision == "approve" else None,
    )
    db.add(review)

    await db.commit()

    reindex_result = None
    if approval.decision == "approve":
        reindex_result = await _reindex_document(db, str(chunk.document_id))

    return {
        "status": "ok",
        "chunk_id": str(chunk_id),
        "decision": approval.decision,
        "reindex": reindex_result,
    }


@router.post("/chunks/bulk-approve")
async def bulk_approve_ready_chunks(
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Approve all chunks for a document that are ready."""
    stmt = (
        select(DocumentChunk)
        .where(
            (DocumentChunk.document_id == document_id) &
            (DocumentChunk.status == "created") &
            (DocumentChunk.chunk_type == "text")
        )
    )
    result = await db.execute(stmt)
    chunks = result.scalars().all()

    approved_count = 0
    for chunk in chunks:
        chunk.status = "approved"
        approved_count += 1

        # Promote the LLM draft (or admin edit, if present) to approved_summary — mirrors
        # the per-chunk /approve endpoint. Without this, VectorIndexService.index_approved_chunks
        # (which requires both status=="approved" AND approved_summary IS NOT NULL) silently
        # skips every bulk-approved chunk.
        summary_stmt = select(ChunkSummary).where(ChunkSummary.chunk_id == chunk.id)
        summary_result = await db.execute(summary_stmt)
        summary = summary_result.scalars().first()
        if summary and not summary.approved_summary:
            summary.approved_summary = summary.admin_edited_summary or summary.llm_summary_draft

        review = ChunkReview(
            chunk_id=chunk.id,
            decision="approve",
            admin_notes="Bulk approved",
            approved_at=datetime.utcnow(),
        )
        db.add(review)

    await db.commit()

    reindex_result = await _reindex_document(db, str(document_id)) if approved_count else None

    return {
        "status": "bulk_approved",
        "document_id": str(document_id),
        "chunks_approved": approved_count,
        "reindex": reindex_result,
    }


def _entity_to_dict(entity: ChunkEntity) -> dict:
    """Shared response shape for every chunk-entity route below."""
    return {
        "id": str(entity.id),
        "chunk_id": str(entity.chunk_id),
        "document_id": str(entity.document_id),
        "entity_type": entity.entity_type,
        "detected_text": entity.detected_text,
        "corrected_text": entity.corrected_text,
        "corrected_type": entity.corrected_type,
        "source": entity.source,
        "status": entity.status,
        "reviewed_by": entity.reviewed_by,
        "reviewed_at": entity.reviewed_at.isoformat() if entity.reviewed_at else None,
        "created_at": entity.created_at.isoformat() if entity.created_at else None,
        "updated_at": entity.updated_at.isoformat() if entity.updated_at else None,
    }


def _require_entity_belongs_to_chunk(entity: ChunkEntity, chunk_id: UUID) -> None:
    if str(entity.chunk_id) != str(chunk_id):
        raise HTTPException(status_code=404, detail="Entity not found for this chunk")


class ChunkEntityEditRequest(BaseModel):
    """Admin correction for one detected entity — mirrors ChunkSummaryUpdate's shape."""
    corrected_text: str | None = None
    corrected_type: str | None = None


class ChunkEntityAddRequest(BaseModel):
    """A new entity typed in by the admin, not present in the detected list."""
    entity_type: str
    text: str


@router.get("/entity-types")
async def list_entity_types():
    """Single source of truth for the entity-type vocabulary (CLAUDE.md §14/§21.5), exposed
    so the frontend's type dropdown never drifts from `GraphService.ALLOWED_ENTITY_TYPES`."""
    return {"entity_types": sorted(ALLOWED_ENTITY_TYPES)}


@router.get("/chunks/{chunk_id}/entities")
async def get_chunk_entities(
    chunk_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """List a chunk's entities, materializing the detected list on first access."""
    try:
        entities = await ChunkEntityService.list_for_chunk(db, chunk_id)
    except ChunkEntityNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return {
        "chunk_id": str(chunk_id),
        "entities": [_entity_to_dict(e) for e in entities],
    }


@router.patch("/chunks/{chunk_id}/entities/{entity_id}")
async def edit_chunk_entity(
    chunk_id: UUID,
    entity_id: UUID,
    body: ChunkEntityEditRequest,
    db: AsyncSession = Depends(get_db),
):
    """Admin correction of an entity's text and/or type. Sets status="edited"."""
    try:
        entity = await ChunkEntityService.edit_entity(
            db, entity_id, body.corrected_text, body.corrected_type, reviewed_by=None
        )
    except ChunkEntityValidationError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except ChunkEntityNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

    _require_entity_belongs_to_chunk(entity, chunk_id)
    return _entity_to_dict(entity)


@router.post("/chunks/{chunk_id}/entities/{entity_id}/confirm")
async def confirm_chunk_entity(
    chunk_id: UUID,
    entity_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Confirm a detected entity as-is."""
    try:
        entity = await ChunkEntityService.confirm_entity(db, entity_id, reviewed_by=None)
    except ChunkEntityNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

    _require_entity_belongs_to_chunk(entity, chunk_id)
    return _entity_to_dict(entity)


@router.post("/chunks/{chunk_id}/entities/{entity_id}/reject")
async def reject_chunk_entity(
    chunk_id: UUID,
    entity_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Reject an entity — the only "delete" mechanism, never hard-deleted (audit trail)."""
    try:
        entity = await ChunkEntityService.reject_entity(db, entity_id, reviewed_by=None)
    except ChunkEntityNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

    _require_entity_belongs_to_chunk(entity, chunk_id)
    return _entity_to_dict(entity)


@router.post("/chunks/{chunk_id}/entities")
async def add_chunk_entity(
    chunk_id: UUID,
    body: ChunkEntityAddRequest,
    db: AsyncSession = Depends(get_db),
):
    """Admin-added entity not present in the detected list. Created already confirmed."""
    try:
        entity = await ChunkEntityService.add_entity(
            db, chunk_id, body.entity_type, body.text, reviewed_by=None
        )
    except ChunkEntityValidationError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except ChunkEntityNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return _entity_to_dict(entity)
