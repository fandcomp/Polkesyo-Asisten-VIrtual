"""Schemas for document form-extract admin review UI (structure-aware document extraction
plan). Mirrors schemas/visual_chunks.py's shape."""
from typing import Optional

from pydantic import BaseModel


class DocumentFormBrief(BaseModel):
    """Brief form-extract info for list views."""
    form_id: str
    zone_type: str
    form_title: str
    source_page_start: int
    source_page_end: int
    extraction_method: str
    status: str


class DocumentFormDetail(BaseModel):
    """Complete form-extract detail for review."""
    form_id: str
    document_id: str
    document_version_id: str
    zone_type: str
    form_title: str
    source_page_start: int
    source_page_end: int
    extraction_method: str
    docx_artifact_path: Optional[str] = None
    status: str
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[str] = None
    admin_notes: Optional[str] = None
    created_at: Optional[str] = None


class DocumentFormApproveRequest(BaseModel):
    """Request to approve a form extract."""
    admin_notes: Optional[str] = None


class DocumentFormRejectRequest(BaseModel):
    """Request to reject a form extract."""
    reason: Optional[str] = None


class DocumentFormRevisionRequest(BaseModel):
    """Request to mark a form extract as needing revision."""
    reason: Optional[str] = None


class DocumentFormListResponse(BaseModel):
    """Response for list of pending form extracts."""
    document_id: str
    total: int
    forms: list[DocumentFormBrief]


class DocumentFormDetailResponse(BaseModel):
    """Response for form extract detail."""
    form: DocumentFormDetail


class DocumentFormActionResponse(BaseModel):
    """Response for form extract actions."""
    status: str
    form_id: str
