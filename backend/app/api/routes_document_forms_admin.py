"""Admin routes for document form-extract review (structure-aware document extraction plan).

Mirrors routes_visual_chunks_admin.py's exact pattern: list pending, detail, download the
internal .docx artifact via FileResponse, and approve/reject/needs-revision. A form extract is
never indexed into Chroma/Neo4j (CLAUDE.md §4.7 — these pages are excluded from retrieval
entirely) — "approve" only flips `status` to "active" so the public download route
(routes_documents_public.py) and answer_composer_agent.py's attachment lookup can serve it.
"""
import logging
import os
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import DocumentFormExtract
from app.db.session import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/document-forms", tags=["admin-document-forms"])

_DOCX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


@router.get("/{document_id}/pending")
async def get_pending_document_forms(
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get pending form extracts for review.

    Includes needs_revision alongside pending_review — otherwise a form flagged for revision
    would disappear from the admin queue with no way to fix and resubmit it. Only
    approved/rejected/active are excluded as final.
    """
    try:
        stmt = (
            select(DocumentFormExtract)
            .where(
                DocumentFormExtract.document_id == document_id,
                DocumentFormExtract.status.in_(["pending_review", "needs_revision"]),
            )
            .order_by(DocumentFormExtract.source_page_start)
        )
        result = await db.execute(stmt)
        forms = result.scalars().all()

        return {
            "document_id": str(document_id),
            "total": len(forms),
            "forms": [
                {
                    "form_id": str(f.id),
                    "zone_type": f.zone_type,
                    "form_title": f.form_title,
                    "source_page_start": f.source_page_start,
                    "source_page_end": f.source_page_end,
                    "extraction_method": f.extraction_method,
                    "status": f.status,
                }
                for f in forms
            ],
        }
    except Exception as e:
        logger.error(f"Get pending document forms error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{form_id}/download")
async def download_document_form_admin(
    form_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Stream the internal .docx artifact for admin preview, regardless of status — unlike
    the public route (routes_documents_public.py) which requires status == 'active'
    (CLAUDE.md §4.7/§21.6)."""
    stmt = select(DocumentFormExtract.docx_artifact_path).where(DocumentFormExtract.id == form_id)
    result = await db.execute(stmt)
    path = result.scalar_one_or_none()

    if not path or not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="Form artifact not found")

    return FileResponse(path, media_type=_DOCX_MEDIA_TYPE)


@router.get("/{form_id}")
async def get_document_form_detail(
    form_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get detailed form-extract information."""
    try:
        stmt = select(DocumentFormExtract).where(DocumentFormExtract.id == form_id)
        result = await db.execute(stmt)
        form = result.scalar_one_or_none()

        if not form:
            raise HTTPException(status_code=404, detail="Form extract not found")

        return {
            "form_id": str(form.id),
            "document_id": str(form.document_id),
            "document_version_id": str(form.document_version_id),
            "zone_type": form.zone_type,
            "form_title": form.form_title,
            "source_page_start": form.source_page_start,
            "source_page_end": form.source_page_end,
            "extraction_method": form.extraction_method,
            "docx_artifact_path": form.docx_artifact_path,
            "status": form.status,
            "reviewed_by": form.reviewed_by,
            "reviewed_at": form.reviewed_at.isoformat() if form.reviewed_at else None,
            "admin_notes": form.admin_notes,
            "created_at": form.created_at.isoformat() if form.created_at else None,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get document form detail error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{form_id}/approve")
async def approve_document_form(
    form_id: UUID,
    admin_notes: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Approve a form extract — flips status to 'active' so it becomes servable via the
    public download route and eligible for answer_composer_agent.py's attachment lookup. No
    Chroma/Neo4j indexing step: form extracts are explicitly excluded from retrieval."""
    try:
        stmt = select(DocumentFormExtract).where(DocumentFormExtract.id == form_id)
        result = await db.execute(stmt)
        form = result.scalar_one_or_none()
        if not form:
            raise HTTPException(status_code=404, detail="Form extract not found")

        form.status = "active"
        form.reviewed_at = datetime.utcnow()
        if admin_notes:
            form.admin_notes = admin_notes

        await db.commit()

        logger.info(f"Document form {form_id} approved")
        return {"status": "active", "form_id": str(form_id)}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Approve document form error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{form_id}/reject")
async def reject_document_form(
    form_id: UUID,
    reason: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Reject a form extract."""
    try:
        stmt = (
            update(DocumentFormExtract)
            .where(DocumentFormExtract.id == form_id)
            .values(
                status="rejected",
                reviewed_at=datetime.utcnow(),
                admin_notes=reason,
            )
        )
        await db.execute(stmt)
        await db.commit()

        logger.info(f"Document form {form_id} rejected")
        return {"status": "rejected", "form_id": str(form_id)}

    except Exception as e:
        logger.error(f"Reject document form error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{form_id}/needs-revision")
async def mark_document_form_needs_revision(
    form_id: UUID,
    reason: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Mark form extract as needing revision."""
    try:
        stmt = (
            update(DocumentFormExtract)
            .where(DocumentFormExtract.id == form_id)
            .values(
                status="needs_revision",
                reviewed_at=datetime.utcnow(),
                admin_notes=reason,
            )
        )
        await db.execute(stmt)
        await db.commit()

        logger.info(f"Document form {form_id} marked as needs_revision")
        return {"status": "needs_revision", "form_id": str(form_id)}

    except Exception as e:
        logger.error(f"Mark document form revision error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
