"""Schemas for document management."""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class DocumentListResponse(BaseModel):
    """Document list response."""
    id: str
    title: str
    document_type: str
    source_type: str
    status: str
    year: Optional[int] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class DocumentDetailResponse(BaseModel):
    """Document detail response."""
    id: str
    title: str
    document_type: str
    source_type: str
    status: str
    year: Optional[int] = None
    versions: list[dict] = []
    chunk_count: int = 0
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class ChunkForReview(BaseModel):
    """Chunk for admin review."""
    chunk_id: str
    chunk_index: int
    page: Optional[int] = None
    section: Optional[str] = None
    original_text: str
    status: str
    llm_summary: Optional[str] = None
    admin_summary: Optional[str] = None
    approved_summary: Optional[str] = None


class DocumentUploadRequest(BaseModel):
    """Document upload request."""
    document_type: str = "other"
    year: Optional[int] = None


class ChunkApprovalRequest(BaseModel):
    """Chunk approval request."""
    admin_summary: Optional[str] = None


class DocumentStatusUpdateRequest(BaseModel):
    """Document status update request."""
    new_status: str
    notes: Optional[str] = None


