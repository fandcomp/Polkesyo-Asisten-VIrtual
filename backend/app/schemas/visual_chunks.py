"""Schemas for visual chunk management UI."""
from typing import Optional
from pydantic import BaseModel, Field


class VisualChunkBrief(BaseModel):
    """Brief visual chunk info for list views."""
    chunk_id: str
    page: Optional[int] = None
    chunk_type: str
    image_hash: Optional[str] = None
    raw_visual_description: Optional[str] = None
    visible_text_draft: Optional[str] = None
    uncertainty_notes: Optional[str] = None
    risk_flags: list[str] = Field(default_factory=list)
    confidence_score: Optional[float] = None


class VisualChunkDetail(BaseModel):
    """Complete visual chunk detail for review."""
    chunk_id: str
    document_id: str
    page: Optional[int] = None
    chunk_type: str
    image_artifact_path: Optional[str] = None
    image_hash: Optional[str] = None
    bounding_box: Optional[dict] = None
    extraction_method: Optional[str] = None
    vision_model: Optional[str] = None
    raw_visual_description: Optional[str] = None
    visible_text_draft: Optional[str] = None
    uncertainty_notes: Optional[str] = None
    confidence_score: Optional[float] = None
    risk_flags: list[str] = Field(default_factory=list)
    admin_status: str
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[str] = None
    admin_notes: Optional[str] = None
    created_at: Optional[str] = None


class VisualChunkApproveRequest(BaseModel):
    """Request to approve a visual chunk."""
    edited_summary: Optional[str] = None
    admin_notes: Optional[str] = None


class VisualChunkRejectRequest(BaseModel):
    """Request to reject a visual chunk."""
    reason: Optional[str] = None


class VisualChunkRevisionRequest(BaseModel):
    """Request to mark chunk as needs revision."""
    reason: Optional[str] = None


class VisualChunkListResponse(BaseModel):
    """Response for list of visual chunks."""
    document_id: str
    total: int
    chunks: list[VisualChunkBrief]


class VisualChunkDetailResponse(BaseModel):
    """Response for visual chunk detail."""
    chunk: VisualChunkDetail


class VisualChunkActionResponse(BaseModel):
    """Response for chunk actions."""
    status: str
    chunk_id: str
