"""Public document download route.

Lets end users click a chat citation and download the original source file. The only
gate is "has at least one approved chunk" — matching CLAUDE.md §4.7's approved-only
exposure rule without requiring the caller to be an authenticated admin, since this is
public-facing content already being cited in an answer.
"""
import os
import re
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Document, DocumentChunk, DocumentFormExtract, DocumentVersion
from app.db.session import get_db

router = APIRouter(prefix="/documents", tags=["documents"])

_EXT_MEDIA_TYPES = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "html": "text/html",
    "htm": "text/html",
}


def _sanitize_filename(title: str, ext: str) -> str:
    safe = re.sub(r"[^\w\-. ]", "_", title).strip(" _") or "document"
    return f"{safe}.{ext}"


@router.get("/{document_id}/download")
async def download_document(document_id: UUID, db: AsyncSession = Depends(get_db)):
    """Serve the original source file for a document that has at least one approved chunk."""
    doc_stmt = select(Document).where(Document.id == document_id)
    doc = (await db.execute(doc_stmt)).scalars().first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    has_approved_stmt = select(
        exists().where(
            (DocumentChunk.document_id == document_id) & (DocumentChunk.status == "approved")
        )
    )
    has_approved = (await db.execute(has_approved_stmt)).scalar()
    if not has_approved:
        raise HTTPException(status_code=404, detail="Document not found")

    version_stmt = (
        select(DocumentVersion)
        .where(
            DocumentVersion.document_id == document_id,
            DocumentVersion.raw_file_path.isnot(None),
        )
        .order_by(DocumentVersion.version.desc())
    )
    version = (await db.execute(version_stmt)).scalars().first()
    if not version or not version.raw_file_path or not os.path.isfile(version.raw_file_path):
        raise HTTPException(status_code=404, detail="Source file not available")

    ext = version.raw_file_path.rsplit(".", 1)[-1].lower() if "." in version.raw_file_path else "pdf"
    media_type = _EXT_MEDIA_TYPES.get(ext, "application/octet-stream")
    filename = _sanitize_filename(doc.title, ext)

    return FileResponse(version.raw_file_path, media_type=media_type, filename=filename)


@router.get("/{document_id}/forms/{form_id}/download")
async def download_document_form(
    document_id: UUID,
    form_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Serve an admin-approved form/attachment .docx (structure-aware document extraction
    plan) for public download — the link AnswerComposerAgent/ChatCoreService attach to a chat
    answer. Only `status == "active"` is servable (CLAUDE.md §4.7/§21.6: a generated artifact
    is never exposed before explicit admin approval)."""
    stmt = select(DocumentFormExtract).where(
        DocumentFormExtract.id == form_id,
        DocumentFormExtract.document_id == document_id,
        DocumentFormExtract.status == "active",
    )
    form = (await db.execute(stmt)).scalars().first()
    if not form or not form.docx_artifact_path or not os.path.isfile(form.docx_artifact_path):
        raise HTTPException(status_code=404, detail="Form not found")

    filename = _sanitize_filename(form.form_title, "docx")
    return FileResponse(form.docx_artifact_path, media_type=_EXT_MEDIA_TYPES["docx"], filename=filename)
