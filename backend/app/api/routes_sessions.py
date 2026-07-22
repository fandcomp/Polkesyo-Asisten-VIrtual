"""Session and consent management endpoints."""
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import APIRouter, Depends, Response, Cookie
from fastapi.responses import JSONResponse

from app.db.session import get_db
from app.core.config import settings
from app.schemas.session import SessionInitResponse, ConsentCreate, ConsentResponse
from app.services.session_service import SessionService, ConsentService

router = APIRouter(prefix="/sessions", tags=["sessions"])
consent_router = APIRouter(prefix="/consent", tags=["consent"])


def _get_cookie_params() -> dict:
    """Get secure cookie parameters."""
    return {
        "key": settings.session_cookie_name,
        "value": None,
        "max_age": 30 * 24 * 60 * 60,  # 30 days
        "secure": settings.app_env == "production",
        "httponly": True,
        "samesite": "lax",
        "path": "/",
    }


@router.post("/init", response_model=SessionInitResponse)
async def init_session(
    response: Response,
    chat_session_id: UUID | None = Cookie(None),
    db: AsyncSession = Depends(get_db),
):
    """Initialize or get existing session.

    Reuses the session named by the incoming cookie if it still exists, instead of always
    minting a new one — the session cookie is HttpOnly, so the frontend can never read it via
    document.cookie to skip calling this endpoint, and previously this endpoint ignored the
    cookie it was sent, silently issuing (and requiring consent for) a fresh session on every
    single page load.
    """
    session = await SessionService.get_or_create_session(db, chat_session_id)

    # Set secure cookie
    cookie_params = _get_cookie_params()
    cookie_params["value"] = str(session.id)
    response.set_cookie(**cookie_params)

    return SessionInitResponse(
        session_id=session.id,
        created_at=session.created_at,
        cookie_name=settings.session_cookie_name,
        cookie_value=str(session.id),
    )


# Registered on both "" and "/" so `POST /consent` works without a trailing slash —
# otherwise FastAPI 307-redirects and non-browser clients that don't re-POST the body
# silently degrade to a no_consent chat response (hit during the 2026-07-08 deploy check).
@consent_router.post("", response_model=ConsentResponse, include_in_schema=False)
@consent_router.post("/", response_model=ConsentResponse)
async def set_consent(
    consent_data: ConsentCreate,
    chat_session_id: UUID | None = Cookie(None),
    db: AsyncSession = Depends(get_db),
):
    """Record user consent choice."""
    if not chat_session_id:
        return JSONResponse(
            status_code=400,
            content={"error": "session not initialized"},
        )

    consent_log = await ConsentService.set_consent(
        db,
        chat_session_id,
        consent_data.consent_value,
        consent_data.source,
    )

    return ConsentResponse(
        id=consent_log.id,
        session_id=consent_log.session_id,
        consent_value=consent_log.consent_value,
        created_at=consent_log.created_at,
    )


@consent_router.get("/{session_id}", response_model=ConsentResponse | None)
async def get_consent(
    session_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get latest consent for a session."""
    consent_log = await ConsentService.get_latest_consent(db, session_id)
    if not consent_log:
        return None

    return ConsentResponse(
        id=consent_log.id,
        session_id=consent_log.session_id,
        consent_value=consent_log.consent_value,
        created_at=consent_log.created_at,
    )