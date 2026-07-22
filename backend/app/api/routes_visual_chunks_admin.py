"""Admin routes for visual chunk management."""
import os
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from uuid import UUID
from datetime import datetime
import logging

from app.db.session import get_db
from app.db.models import DocumentChunk
from app.services.ingestion.visual_chunk_indexer import VisualChunkIndexer
from app.services.redis_cache_service import get_cache_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/visual-chunks", tags=["admin-visual-chunks"])


@router.get("/{document_id}/pending")
async def get_pending_visual_chunks(
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get pending visual chunks for review.

    Includes needs_revision chunks alongside pending_review ones — otherwise a chunk
    flagged for revision would disappear from the admin queue entirely with no way to
    fix and resubmit it. Only approved/rejected are excluded as final.
    """
    try:
        stmt = select(DocumentChunk).where(
            DocumentChunk.document_id == document_id,
            DocumentChunk.chunk_type.in_(["image", "scanned_region", "diagram", "table_image"]),
            DocumentChunk.admin_status.in_(["pending_review", "needs_revision"]),
        ).order_by(DocumentChunk.page, DocumentChunk.chunk_index)

        result = await db.execute(stmt)
        chunks = result.scalars().all()

        return {
            "document_id": str(document_id),
            "total": len(chunks),
            "chunks": [
                {
                    "chunk_id": str(chunk.id),
                    "page": chunk.page,
                    "chunk_type": chunk.chunk_type,
                    "image_hash": chunk.image_hash,
                    "raw_visual_description": chunk.raw_visual_description[:200] if chunk.raw_visual_description else None,
                    "visible_text_draft": chunk.visible_text_draft[:200] if chunk.visible_text_draft else None,
                    "uncertainty_notes": chunk.uncertainty_notes,
                    "risk_flags": chunk.risk_flags or [],
                    "confidence_score": chunk.confidence_score,
                    "admin_status": chunk.admin_status,
                }
                for chunk in chunks
            ],
        }
    except Exception as e:
        logger.error(f"Get pending chunks error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{chunk_id}/image")
async def get_visual_chunk_image(
    chunk_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Stream the raw image artifact for admin preview.

    `image_artifact_path` is an internal filesystem path (CLAUDE.md §38:
    "Internal storage only") — this is the only way the frontend can render
    the original image, since the path itself is never exposed to the browser.
    """
    stmt = select(DocumentChunk.image_artifact_path).where(DocumentChunk.id == chunk_id)
    result = await db.execute(stmt)
    path = result.scalar_one_or_none()

    if not path or not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="Image artifact not found")

    media_type = "image/png" if path.lower().endswith(".png") else "image/jpeg"
    return FileResponse(path, media_type=media_type)


@router.get("/{chunk_id}")
async def get_visual_chunk_detail(
    chunk_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get detailed visual chunk information."""
    try:
        stmt = select(DocumentChunk).where(DocumentChunk.id == chunk_id)
        result = await db.execute(stmt)
        chunk = result.scalar_one_or_none()

        if not chunk:
            raise HTTPException(status_code=404, detail="Chunk not found")

        return {
            "chunk_id": str(chunk.id),
            "document_id": str(chunk.document_id),
            "page": chunk.page,
            "chunk_type": chunk.chunk_type,
            "image_artifact_path": chunk.image_artifact_path,
            "image_hash": chunk.image_hash,
            "bounding_box": chunk.bounding_box,
            "extraction_method": chunk.extraction_method,
            "vision_model": chunk.vision_model,
            "raw_visual_description": chunk.raw_visual_description,
            "visible_text_draft": chunk.visible_text_draft,
            "uncertainty_notes": chunk.uncertainty_notes,
            "confidence_score": chunk.confidence_score,
            "risk_flags": chunk.risk_flags or [],
            "admin_status": chunk.admin_status,
            "reviewed_by": chunk.reviewed_by,
            "reviewed_at": chunk.reviewed_at.isoformat() if chunk.reviewed_at else None,
            "admin_notes": chunk.admin_notes,
            "created_at": chunk.created_at.isoformat() if chunk.created_at else None,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get chunk detail error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{chunk_id}/approve")
async def approve_visual_chunk(
    chunk_id: UUID,
    edited_summary: str | None = None,
    admin_notes: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Approve a visual chunk and immediately index it into Chroma.

    Previously only flipped `admin_status` to "approved" in Postgres — nothing ever
    indexed the chunk afterward, so approved images/diagrams/tables silently never became
    retrievable. Now mirrors the text-chunk approve flow in routes_chunk_review.py:
    index right away and invalidate the retrieval cache so it's usable immediately.
    """
    try:
        stmt = select(DocumentChunk).where(DocumentChunk.id == chunk_id)
        result = await db.execute(stmt)
        chunk = result.scalar_one_or_none()
        if not chunk:
            raise HTTPException(status_code=404, detail="Chunk not found")

        chunk.admin_status = "approved"
        chunk.reviewed_at = datetime.utcnow()
        chunk.admin_notes = admin_notes
        if edited_summary:
            chunk.raw_visual_description = edited_summary

        await db.commit()

        index_result = await VisualChunkIndexer.index_approved_visual_chunks(
            db, str(chunk.document_id)
        )
        cache_service = await get_cache_service()
        await cache_service.invalidate_retrieval_cache()

        logger.info(f"Visual chunk {chunk_id} approved")
        return {"status": "approved", "chunk_id": str(chunk_id), "index": index_result}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Approve chunk error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{chunk_id}/reject")
async def reject_visual_chunk(
    chunk_id: UUID,
    reason: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Reject a visual chunk."""
    try:
        stmt = (
            update(DocumentChunk)
            .where(DocumentChunk.id == chunk_id)
            .values(
                admin_status="rejected",
                reviewed_at=datetime.utcnow(),
                admin_notes=reason,
            )
        )

        await db.execute(stmt)
        await db.commit()

        logger.info(f"Visual chunk {chunk_id} rejected")
        return {"status": "rejected", "chunk_id": str(chunk_id)}

    except Exception as e:
        logger.error(f"Reject chunk error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{chunk_id}/needs-revision")
async def mark_needs_revision(
    chunk_id: UUID,
    reason: str | None = None,
    edited_summary: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Mark chunk as needing revision, optionally saving an in-progress description edit
    so the admin's fix isn't lost while the chunk waits for another pass."""
    try:
        values = {
            "admin_status": "needs_revision",
            "reviewed_at": datetime.utcnow(),
            "admin_notes": reason,
        }
        if edited_summary:
            values["raw_visual_description"] = edited_summary

        stmt = update(DocumentChunk).where(DocumentChunk.id == chunk_id).values(**values)

        await db.execute(stmt)
        await db.commit()

        logger.info(f"Visual chunk {chunk_id} marked as needs_revision")
        return {"status": "needs_revision", "chunk_id": str(chunk_id)}

    except Exception as e:
        logger.error(f"Mark revision error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
