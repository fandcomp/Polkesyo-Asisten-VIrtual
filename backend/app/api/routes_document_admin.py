"""Admin routes for document management and review.

Note: document listing, sync, and upload live in routes_admin.py
(prefix /admin) to avoid duplicating those endpoints under
/admin/documents — see that module for the canonical implementations.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
import logging

from app.db.session import get_db
from app.services.document_management_service import DocumentManagementService
from app.api.routes_chunk_review import _reindex_document

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/documents", tags=["admin-documents"])


@router.get("/{document_id}")
async def get_document(
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get document details."""
    try:
        doc = await DocumentManagementService.get_document_detail(db, document_id)
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")
        return doc
    except Exception as e:
        logger.error(f"Get document error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{document_id}/chunks")
async def get_document_chunks(
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get chunks for review."""
    try:
        chunks = await DocumentManagementService.get_chunks_for_review(db, document_id)
        return {
            "document_id": str(document_id),
            "chunks": chunks,
            "total": len(chunks),
        }
    except Exception as e:
        logger.error(f"Get chunks error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{document_id}/approve-chunk/{chunk_id}")
async def approve_chunk(
    document_id: UUID,
    chunk_id: UUID,
    admin_summary: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Approve a chunk for indexing."""
    try:
        success = await DocumentManagementService.approve_chunk(
            db, chunk_id, admin_summary
        )
        if success:
            reindex_result = await _reindex_document(db, str(document_id))
            return {"status": "approved", "chunk_id": str(chunk_id), "reindex": reindex_result}
        raise HTTPException(status_code=400, detail="Approval failed")
    except Exception as e:
        logger.error(f"Approve chunk error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{document_id}/reject-chunk/{chunk_id}")
async def reject_chunk(
    document_id: UUID,
    chunk_id: UUID,
    reason: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Reject a chunk."""
    try:
        success = await DocumentManagementService.reject_chunk(db, chunk_id, reason)
        if success:
            return {"status": "rejected", "chunk_id": str(chunk_id)}
        raise HTTPException(status_code=400, detail="Rejection failed")
    except Exception as e:
        logger.error(f"Reject chunk error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/{document_id}/status")
async def update_document_status(
    document_id: UUID,
    new_status: str,
    notes: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Update document status."""
    try:
        success = await DocumentManagementService.update_document_status(
            db, document_id, new_status, notes
        )
        if success:
            return {"status": "updated", "document_id": str(document_id), "new_status": new_status}
        raise HTTPException(status_code=400, detail="Status update failed")
    except Exception as e:
        logger.error(f"Update status error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
