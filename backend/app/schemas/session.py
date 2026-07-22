"""Pydantic schemas for sessions and consent."""
from datetime import datetime
from uuid import UUID
from typing import Optional, Literal
from pydantic import BaseModel, Field


class SessionCreate(BaseModel):
    """Session creation request."""
    user_agent_hash: Optional[str] = None


class SessionResponse(BaseModel):
    """Session response."""
    id: UUID
    created_at: datetime
    last_active_at: datetime
    status: str

    class Config:
        from_attributes = True


class ConsentCreate(BaseModel):
    """Consent creation/update request."""
    consent_value: Literal["essential_only", "history_and_analytics"]
    source: Optional[str] = None


class ConsentResponse(BaseModel):
    """Consent response."""
    id: UUID
    session_id: UUID
    consent_value: str
    created_at: datetime

    class Config:
        from_attributes = True


class SessionInitResponse(BaseModel):
    """Response for /sessions/init endpoint."""
    session_id: UUID
    created_at: datetime
    cookie_name: str
    cookie_value: str