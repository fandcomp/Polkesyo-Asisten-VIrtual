"""Chat request handling — delegates to chat_core service."""
import logging
from uuid import UUID, uuid4

from fastapi import APIRouter, Cookie, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import SessionNotFoundError
from app.db.session import get_db
from app.schemas.chat import ChatRequest, ChatResponse, ErrorResponse
from app.services.chat_core import ChatCoreService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    chat_session_id: UUID | None = Cookie(None),
    db: AsyncSession = Depends(get_db),
):
    """Process user message and return response."""
    if not chat_session_id:
        return JSONResponse(
            status_code=400,
            content=ErrorResponse(
                trace_id=str(uuid4()),
                error_type="session_not_found",
                message=(
                    "Sesi Anda belum dimulai. Muat ulang halaman untuk memulai sesi baru."
                ),
            ).model_dump(),
        )

    try:
        response = await ChatCoreService.process_message(
            db=db,
            session_id=chat_session_id,
            message=request.message,
            metadata=request.metadata,
            evaluation_mode=request.evaluation_mode,
            participant_code=request.participant_code,
            scenario_code=request.scenario_code,
        )
    except SessionNotFoundError:
        # Only the explicit session-verification failure maps to this 404 — catching bare
        # ValueError here used to mislabel unrelated pipeline failures as an expired session.
        return JSONResponse(
            status_code=404,
            content=ErrorResponse(
                trace_id=str(uuid4()),
                error_type="session_not_found",
                message=(
                    "Sesi Anda tidak ditemukan atau sudah berakhir. "
                    "Muat ulang halaman untuk memulai sesi baru."
                ),
            ).model_dump(),
        )

    return response
